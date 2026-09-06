"""Predictors: each takes a list of messages and returns P(true) per message."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nano.contract import LABEL_FALSE, LABEL_TRUE, build_messages, render_prompt


def keyword(messages: list[str]) -> list[float]:
    from app.agents.emergency import detect_emergency
    return [1.0 if detect_emergency(m).detected else 0.0 for m in messages]


class QwenPredictor:
    """Base or fine-tuned Qwen3 via transformers. P(true) = softmax over the
    logits of the first token of "true" vs "false" at the answer position."""

    def __init__(self, model_path: str = "Qwen/Qwen3-0.6B", fewshot: bool = False, batch_size: int = 16):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
        self.tok = AutoTokenizer.from_pretrained(model_path, padding_side="left")
        self.model = AutoModelForCausalLM.from_pretrained(model_path, dtype=torch.float32).to(self.device).eval()
        self.fewshot = fewshot
        self.batch_size = batch_size
        self.true_id = self.tok.encode(LABEL_TRUE, add_special_tokens=False)[0]
        self.false_id = self.tok.encode(LABEL_FALSE, add_special_tokens=False)[0]

    def prompt(self, message: str) -> str:
        return self.tok.apply_chat_template(
            build_messages(message, self.fewshot),
            tokenize=False, add_generation_prompt=True, enable_thinking=False,
        )

    def __call__(self, messages: list[str]) -> list[float]:
        out: list[float] = []
        for i in range(0, len(messages), self.batch_size):
            prompts = [self.prompt(m) for m in messages[i:i + self.batch_size]]
            enc = self.tok(prompts, return_tensors="pt", padding=True).to(self.device)
            with self.torch.no_grad():
                logits = self.model(**enc).logits[:, -1, :]
            pair = logits[:, [self.true_id, self.false_id]].float()
            out.extend(self.torch.softmax(pair, dim=-1)[:, 0].tolist())
            print(f"  {min(i + self.batch_size, len(messages))}/{len(messages)}", end="\r", file=sys.stderr)
        print(file=sys.stderr)
        return out


class LlamaPredictor:
    """Quantized GGUF via a running llama-server (what production will use).
    One request per message, n_predict=1, read the top-k logprobs of the first
    generated token and softmax over the "true" / "false" entries."""

    def __init__(self, url: str = "http://127.0.0.1:8081", timeout: float = 10.0):
        import httpx
        self.client = httpx.Client(base_url=url, timeout=timeout)
        self.latencies_ms: list[float] = []

    def p_true(self, message: str) -> float:
        import math, time
        t0 = time.perf_counter()
        r = self.client.post("/completion", json={
            "prompt": render_prompt(message), "n_predict": 1, "temperature": 0,
            "n_probs": 20, "cache_prompt": True,
        })
        self.latencies_ms.append((time.perf_counter() - t0) * 1000)
        r.raise_for_status()
        first = r.json()["completion_probabilities"][0]
        # llama-server has shipped two shapes for this field over time
        cands = first.get("top_logprobs") or first.get("probs") or []
        lp = {}
        for c in cands:
            tok = c.get("token", c.get("tok_str"))
            lp[tok] = c["logprob"] if "logprob" in c else math.log(max(c["prob"], 1e-12))
        lt, lf = lp.get(LABEL_TRUE, -1e9), lp.get(LABEL_FALSE, -1e9)
        return 1.0 / (1.0 + math.exp(max(-700.0, min(700.0, lf - lt))))

    def __call__(self, messages: list[str]) -> list[float]:
        out = []
        for i, m in enumerate(messages, 1):
            out.append(self.p_true(m))
            if i % 50 == 0 or i == len(messages):
                print(f"  {i}/{len(messages)}", end="\r", file=sys.stderr)
        print(file=sys.stderr)
        return out
