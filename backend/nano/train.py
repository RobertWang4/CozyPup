"""LoRA 微调 Qwen3-0.6B 做 true/false 紧急分类器 —— 教程版注释

================================================================================
先建立整体图景
================================================================================

一个语言模型只会做一件事：给一段文字，算出"下一个 token"在整个词表上的概率分布。
我们把分类任务也伪装成这件事：

    <system 提示> <用户消息> <assistant 开始>  →  下一个 token 是 "true" 还是 "false"？

微调就是让模型在这个位置给正确答案的概率变高。整个循环（Trainer 内部替我们做了）：

    1. 前向：把一批题喂进模型，得到答案位置的 logits（词表里每个词的打分）
    2. 算 loss：loss = -log P(正确答案)。正确答案概率越低，loss 越大
    3. 反向传播：loss.backward()，算出每个可训练参数往哪个方向挪能让 loss 变小
    4. 更新：optimizer.step()，沿那个方向挪一小步（步长 = learning rate）
    5. 下一批，重复。所有题过一遍 = 1 个 epoch

LoRA 的意思是：6 亿个原始参数全部冻结，只在每个注意力/MLP 矩阵旁边挂一对小矩阵 A、B，
只训这 500 万个参数（0.84%）。训完把 A×B 加回原矩阵，得到一个和原模型一样大的新模型。

本文件流程：
    读数据 → 编码成 token（encode）→ 拼 batch（Collator）→ 挂 LoRA → Trainer 跑循环
    → 每 100 步在验证集上算召回/精确率 → 保存 adapter 和合并后的完整模型

用法:
  python -m nano.train --run r1                 # 默认: r=8, lr=1e-4, 3 epochs
  python -m nano.train --run r2 --rank 16 --epochs 2
输出: nano/models/<run>/{adapter,merged,log.jsonl}
"""
from __future__ import annotations

import json, sys
from pathlib import Path

import click
import torch

# 让 `python -m nano.train` 能 import 到 nano.contract
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# contract.py 是训练 / 评估 / 线上三处唯一的 prompt 来源。
# 模型看到的是字节，训练时的 prompt 和线上差一个空格效果就会掉，所以绝不在这里手写 prompt。
from nano.contract import LABEL_FALSE, LABEL_TRUE, build_messages  # noqa: E402


def pick_device() -> str:
    """选计算设备。同一份脚本在 Mac (mps) 和 GPU 服务器 (cuda) 上都能跑，什么都没有就用 cpu。"""
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def load_jsonl(path: str) -> list[dict]:
    """每行一个 {"msg": "...", "label": true/false}，由 build_dataset.py 生成。"""
    return [json.loads(l) for l in open(path) if l.strip()]


# ------------------------------------------------------------------------------
# 第 1 步：把一道题变成模型能吃的数字
# ------------------------------------------------------------------------------
def encode(tok, rows: list[dict], max_len: int) -> list[dict]:
    """把每条 {msg, label} 变成 {input_ids, labels}。

    input_ids：整段文字的 token id 序列 = [提示词的 token..., 答案 token]
    labels   ：和 input_ids 等长。提示词位置全部填 -100，只有最后一个位置是答案 token 的 id。

    -100 是 PyTorch 交叉熵的约定：这个位置不算 loss。
    这就是"只对答案那一个 token 算 loss"的实现方式：模型不需要学怎么把题目复述一遍，
    它只对最后那个 true/false 负责。

    这个函数决定了模型学的是什么。读懂它就读懂了微调的本质。
    """
    # "true" / "false" 在 Qwen 词表里各是一个 token，这里拿到它们的 id
    true_id = tok.encode(LABEL_TRUE, add_special_tokens=False)[0]
    false_id = tok.encode(LABEL_FALSE, add_special_tokens=False)[0]
    out = []
    for r in rows:
        # 用 Qwen 的对话模板把 system + user 拼成一段带特殊标记的文本，
        # add_generation_prompt=True 会在末尾加上 "<|im_start|>assistant\n"，
        # 也就是"轮到模型说话了"的位置。enable_thinking=False 关掉 Qwen3 的思考模式，
        # 否则模板会插入 <think> 段，答案就不在下一个 token 了。
        # 线上推理 (predictors.QwenPredictor) 用完全相同的参数拼 prompt。
        prompt = tok.apply_chat_template(
            build_messages(r["msg"]), tokenize=False, add_generation_prompt=True, enable_thinking=False,
        )
        # 文本 → token id。超过 max_len-1 就截断（留一个位置给答案）。我们的题最长 83，不会触发。
        ids = tok.encode(prompt, add_special_tokens=False)[: max_len - 1]
        ans = true_id if r["label"] else false_id
        out.append({"input_ids": ids + [ans], "labels": [-100] * len(ids) + [ans]})
    return out


# ------------------------------------------------------------------------------
# 第 2 步：把 16 道长短不一的题拼成一个矩阵
# ------------------------------------------------------------------------------
class Collator:
    """GPU 一次算一个 batch，batch 必须是规整的矩阵 (batch, 长度)。
    题目长短不一，所以要在右边补 pad token 补齐。

    三个输出：
      input_ids      (B, n)  token id，短的题右边补 pad_id
      labels         (B, n)  补的位置填 -100，同样不算 loss
      attention_mask (B, n)  1 = 真内容，0 = 补的。模型靠它知道补上去的不是内容，不去"看"它们

    为什么补到固定长度 pad_to 而不是每批取最长：
    Mac 的 MPS 显存分配器会给每一种张量形状留一块缓存不还。
    如果每批长度都不同，几百步之后每种长度都留了一份，内存无限涨
    （r1 第一次跑在 24GB 的 Mac 上涨到 27GB，开始用硬盘当内存，一步 433 秒）。
    形状固定，缓存就能复用。CUDA 上这个问题轻得多，但固定长度也没坏处。
    """

    def __init__(self, pad_id: int, pad_to: int):
        self.pad_id = pad_id
        self.pad_to = pad_to

    def __call__(self, batch):
        n = self.pad_to
        ids = torch.full((len(batch), n), self.pad_id, dtype=torch.long)
        labels = torch.full((len(batch), n), -100, dtype=torch.long)
        attn = torch.zeros((len(batch), n), dtype=torch.long)
        for i, b in enumerate(batch):  # 右补齐
            L = len(b["input_ids"])
            ids[i, :L] = torch.tensor(b["input_ids"])
            labels[i, :L] = torch.tensor(b["labels"])
            attn[i, :L] = 1
        return {"input_ids": ids, "labels": labels, "attention_mask": attn}


@click.command()
@click.option("--run", required=True, help="本次训练的名字 → nano/models/<run>")
@click.option("--base", default="Qwen/Qwen3-0.6B", help="底座模型，HF Hub 名字或本地目录")
@click.option("--train-file", default="nano/data/train.jsonl")
@click.option("--val-file", default="nano/data/val.jsonl")
# ---- 超参数。含义见 README 第三节步骤 4 ----
@click.option("--rank", default=8, type=int, help="LoRA 小矩阵的宽度 r。越大能学越多，也越容易背题")
@click.option("--alpha", default=16, type=int, help="LoRA 缩放系数，实际叠加量 = alpha/r × (A×B)。惯例 alpha = 2r")
@click.option("--lr", default=1e-4, type=float, help="学习率：每步参数挪多大。LoRA 常用 1e-4 到 3e-4，比全量微调大 10 倍")
@click.option("--epochs", default=3, type=float, help="全部数据过几遍")
@click.option("--batch", default=16, type=int, help="每步同时看几道题。大 = 梯度更稳、更吃内存")
@click.option("--max-len", default=256, type=int, help="超长截断，我们的题最长 83")
@click.option("--limit", default=0, type=int, help="只用前 N 条训练（冒烟测试用）")
def main(run, base, train_file, val_file, rank, alpha, lr, epochs, batch, max_len, limit):
    # 重的库放函数里 import，`--help` 就不用等 torch 加载
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainerCallback, TrainingArguments

    device = pick_device()
    out_dir = Path("nano/models") / run
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"device={device}  base={base}  rank={rank} alpha={alpha} lr={lr} epochs={epochs} batch={batch}")

    class FreeMpsCache(TrainerCallback):
        """每步结束把 MPS 缓存的显存还给系统。配合 Collator 的固定长度一起治内存涨。
        TrainerCallback 是 Trainer 留的钩子，on_step_end / on_evaluate / on_save 等时机都能挂代码。"""
        def on_step_end(self, args, state, control, **kw):
            if device == "mps":
                torch.mps.empty_cache()

    # --------------------------------------------------------------------------
    # 第 3 步：加载 tokenizer，准备数据
    # --------------------------------------------------------------------------
    # tokenizer 负责 文本 ↔ token id。from_pretrained 会从 HF 缓存 (~/.cache/huggingface/hub) 读，
    # 没有就自动下载。它读的是模型目录里的 tokenizer.json / tokenizer_config.json。
    tok = AutoTokenizer.from_pretrained(base)
    true_id = tok.encode(LABEL_TRUE, add_special_tokens=False)[0]
    false_id = tok.encode(LABEL_FALSE, add_special_tokens=False)[0]

    train_rows = load_jsonl(train_file)
    val_rows = load_jsonl(val_file)
    if limit:
        train_rows, val_rows = train_rows[:limit], val_rows[: max(limit // 10, 16)]
    train_ds = encode(tok, train_rows, max_len)
    val_ds = encode(tok, val_rows, max_len)
    pad_to = max(len(x["input_ids"]) for x in train_ds + val_ds)
    print(f"train {len(train_ds)}  val {len(val_ds)}  pad every batch to {pad_to} tokens")

    # --------------------------------------------------------------------------
    # 第 4 步：加载底座模型，挂上 LoRA
    # --------------------------------------------------------------------------
    # dtype 是参数的数值精度。bf16 省一半内存、快一倍，CUDA 支持得好；
    # MPS 的 bf16 有些算子还没实现，所以 Mac 上用 fp32（每个参数 4 字节，0.6B → 2.4GB）。
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    # 读 config.json 建网络结构，再把 model.safetensors 里的权重填进去
    model = AutoModelForCausalLM.from_pretrained(base, dtype=dtype)
    # KV cache 是生成时用来加速的，训练用不上，关掉省内存
    model.config.use_cache = False

    # LoRA 配置：
    #   r / lora_alpha  见上面的 --rank / --alpha
    #   lora_dropout    训练时随机丢 5% 的 LoRA 输出，防止背题
    #   target_modules  往哪些矩阵旁边挂 A、B。这七个是 Qwen 每一层的全部线性层：
    #                   q/k/v/o_proj 是注意力的四个矩阵，gate/up/down_proj 是 MLP 的三个。
    #                   全挂效果最好，只挂 q、v 参数更少但学得少。
    #   task_type       告诉 peft 这是因果语言模型（预测下一个 token）
    lora = LoraConfig(
        r=rank, lora_alpha=alpha, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    # get_peft_model 做两件事：把原参数全部 requires_grad=False（冻住），
    # 然后在每个 target 矩阵旁边插入 A (d×r) 和 B (r×d)，只有它们参与训练。
    model = get_peft_model(model, lora)
    # 打印 "trainable params: 5,046,272 || all params: 601,096,192 || trainable%: 0.84"
    model.print_trainable_parameters()

    # --------------------------------------------------------------------------
    # 第 5 步：验证集上怎么算召回 / 精确率
    # --------------------------------------------------------------------------
    def keep_answer_logits(logits, labels):
        """Trainer 评估时会把每个 batch 的 logits 攒起来，形状是 (B, T, 词表 151936)，
        552 条攒下来要好几个 GB。这个钩子在攒之前把它缩成 (B, 2)：只留答案位置上
        true / false 两个词的分数。

        pos 为什么要 -1：语言模型在位置 t 输出的 logits 是"预测位置 t+1 的 token"。
        答案 token 在位置 p（labels 里唯一不是 -100 的位置），那么预测它的 logits 在 p-1。
        """
        pos = (labels != -100).int().argmax(dim=-1) - 1
        rows = torch.arange(logits.size(0), device=logits.device)
        return logits[rows, pos][:, [true_id, false_id]]

    def compute_metrics(ev):
        """拿到全部验证集的 (N, 2) 分数和标签，算召回和精确率。
        softmax 把两个分数变成加起来等于 1 的概率，[:, 0] 是 P(true)。
        阈值 0.5 只是训练时看趋势用；线上阈值由 evaluate.py 的阈值扫描决定。
        """
        pair, labels = ev
        gold = labels[labels != -100] == true_id  # 每行只有一个答案 token
        p_true = torch.softmax(torch.tensor(pair), dim=-1)[:, 0].numpy()
        pred = p_true >= 0.5
        tp = int((pred & gold).sum()); fp = int((pred & ~gold).sum()); fn = int((~pred & gold).sum())
        return {"recall": tp / (tp + fn) if tp + fn else 0.0,        # 真危急里抓到多少
                "precision": tp / (tp + fp) if tp + fp else 0.0}     # 报警里多少是真的

    # --------------------------------------------------------------------------
    # 第 6 步：训练参数
    # --------------------------------------------------------------------------
    # 一步 (step) = 一个 batch 的 前向 → loss → 反向 → 更新。
    # 总步数 = 训练条数 / batch × epochs = 4972 / 16 × 3 ≈ 933
    args = TrainingArguments(
        output_dir=str(out_dir / "ckpt"),               # checkpoint 存哪
        per_device_train_batch_size=batch,
        per_device_eval_batch_size=batch * 2,           # 评估不用存梯度，内存省一半，可以开大
        learning_rate=lr,
        num_train_epochs=epochs,
        # 学习率不是一直不变的：
        #   warmup：前 5% 的步数从 0 线性升到 lr。一开始 LoRA 矩阵是随机的，大步会把模型打歪
        #   cosine：之后按余弦曲线慢慢降到 0，后期小步精修。日志里 learning_rate 一栏能看到这条曲线
        lr_scheduler_type="cosine",
        warmup_steps=max(1, int(0.05 * len(train_ds) / batch * epochs)),
        weight_decay=0.0,                               # 权重衰减（把参数往 0 拉的正则），LoRA 一般不用
        logging_steps=20,                               # 每 20 步打一行 loss（是这 20 步的平均）
        # 每 100 步在验证集上评估一次并存 checkpoint。
        # 看 eval_loss：和训练 loss 一起降 = 正常；训练 loss 降但 eval_loss 升 = 过拟合（背题）
        eval_strategy="steps",
        eval_steps=100,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=3,                             # 磁盘上最多留 3 个 checkpoint
        # 训完自动回滚到 eval_loss 最低的那个 checkpoint，而不是最后一个。
        # 这就是"过拟合了也没关系，取 val 最低点"的自动版
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        report_to=[],                                   # 不上报 wandb 之类
        bf16=(device == "cuda"),                        # 混合精度，只在 CUDA 上开
        dataloader_pin_memory=False,                    # 锁页内存是 CUDA 的优化，MPS 用不上
        remove_unused_columns=False,                    # 我们的数据是自己拼的 dict，别让 Trainer 删列
    )

    # --------------------------------------------------------------------------
    # 第 7 步：跑
    # --------------------------------------------------------------------------
    # Trainer 把训练循环封装了。trainer.train() 内部大致是：
    #     for epoch in range(epochs):
    #         for batch in dataloader:                 # 用 Collator 拼 batch
    #             out = model(**batch)                 # 前向，内部按 labels 算交叉熵 loss（-100 位置跳过）
    #             out.loss.backward()                  # 反向传播，算 LoRA 参数的梯度
    #             optimizer.step(); scheduler.step()   # AdamW 更新参数；学习率按 warmup/cosine 走
    #             optimizer.zero_grad()                # 清梯度，准备下一步
    #             每 20 步打日志、每 100 步 evaluate() + save()
    trainer = Trainer(
        model=model, args=args,
        train_dataset=train_ds, eval_dataset=val_ds,
        data_collator=Collator(tok.pad_token_id, pad_to),
        preprocess_logits_for_metrics=keep_answer_logits,
        compute_metrics=compute_metrics,
        callbacks=[FreeMpsCache()],
    )
    trainer.train()

    # --------------------------------------------------------------------------
    # 第 8 步：保存
    # --------------------------------------------------------------------------
    # log.jsonl：所有 loss / eval 记录，画曲线用
    (out_dir / "log.jsonl").write_text("\n".join(json.dumps(x) for x in trainer.state.log_history))
    # adapter/：只有 LoRA 的 A、B 矩阵，20MB。要配合底座一起用
    model.save_pretrained(out_dir / "adapter")
    # merged/：把 A×B 加回原矩阵，得到一个独立的完整模型（和底座一样 2.4GB）。
    # 推理零额外开销，evaluate 和后面转 GGUF 都用这个
    merged = model.merge_and_unload()
    merged.save_pretrained(out_dir / "merged")
    tok.save_pretrained(out_dir / "merged")             # tokenizer 也要一起存，模型目录才完整
    print(f"\nsaved adapter → {out_dir/'adapter'}\nsaved merged  → {out_dir/'merged'}")
    print(f"next: python -m nano.cli eval --predictor qwen --model {out_dir/'merged'}")


if __name__ == "__main__":
    main()
