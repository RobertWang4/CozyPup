"""The single source of truth for the classifier's prompt.

Training, evaluation and production must all build prompts through this
module so the bytes the model sees are identical everywhere.
"""

SYSTEM = "判断这条宠物主人的消息是否描述正在发生的、危及生命的紧急情况。只回答 true 或 false。"

LABEL_TRUE = "true"
LABEL_FALSE = "false"

# Few-shot variant: same task, six examples in the system prompt. Used only
# as a baseline to answer "is prompting enough, or do we need to train?"
FEWSHOT = [
    ("豆豆突然就倒了然后一直抽 嘴里有白沫子 怎么办啊怎么办", True),
    ("我家公猫蹲猫砂盆蹲半天了 一直叫 尿不出来", True),
    ("got hit by a car he's awake but bleeding from the mouth", True),
    ("狗狗今天有点兔 兔的白色的", False),
    ("狗吃葡萄会咋样", False),
    ("上个月抽搐过一次 医生说是癫痫 现在在吃药", False),
]


def build_messages(message: str, fewshot: bool = False) -> list[dict]:
    system = SYSTEM
    if fewshot:
        examples = "\n".join(f"消息：{m}\n回答：{LABEL_TRUE if y else LABEL_FALSE}" for m, y in FEWSHOT)
        system = f"{SYSTEM}\n\n例子：\n{examples}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": message},
    ]


# Qwen3 chat template, rendered by hand (add_generation_prompt=True, enable_thinking=False).
# Production (llama-server) has no HF tokenizer, so it builds the prompt string here.
# tests assert this equals tokenizer.apply_chat_template(...) byte for byte.
_QWEN3_TEMPLATE = (
    "<|im_start|>system\n{system}<|im_end|>\n"
    "<|im_start|>user\n{user}<|im_end|>\n"
    "<|im_start|>assistant\n<think>\n\n</think>\n\n"
)


def render_prompt(message: str, fewshot: bool = False) -> str:
    sys_msg, user_msg = build_messages(message, fewshot)
    return _QWEN3_TEMPLATE.format(system=sys_msg["content"], user=user_msg["content"])
