"""Emergency classifier client — the fine-tuned Qwen3-0.6B sidecar (see backend/nano/).

Replaces the keyword regex in `emergency.detect_emergency` for MODEL SELECTION only.
`emergency_router.classify_emergency` (hotline card short-circuit) is untouched.

Rollout is controlled by the `emergency_clf_mode` feature flag:
    off     keyword regex decides; classifier not called
    shadow  classifier called and logged, keyword regex still decides   (default when URL is set)
    union   emergency = keyword OR classifier                           (only ever raises recall)
    clf     classifier decides; keyword regex only if it timed out / errored

The sidecar is a llama-server on localhost; one request, one generated token, and we read the
logprobs of "true" vs "false" — identical to how the model was evaluated (nano/predictors.py).
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass

import httpx

from app.agents.emergency import EmergencyCheckResult
from app.config import settings
from nano.contract import LABEL_FALSE, LABEL_TRUE, render_prompt  # single source of the prompt bytes

logger = logging.getLogger(__name__)

MODES = ("off", "shadow", "union", "clf")


@dataclass
class ClfResult:
    p_true: float
    decided: bool
    latency_ms: int


def get_mode() -> str:
    """Effective mode: `off` unless a sidecar URL is configured; then the flag, default `shadow`."""
    if not settings.emergency_clf_url:
        return "off"
    from app.flags import get_flag
    mode = str(get_flag("emergency_clf_mode", "shadow")).lower()
    return mode if mode in MODES else "shadow"


def _p_true_from_response(body: dict) -> float:
    first = body["completion_probabilities"][0]
    lp = {c["token"]: c["logprob"] for c in first.get("top_logprobs", [])}
    lt, lf = lp.get(LABEL_TRUE, -1e9), lp.get(LABEL_FALSE, -1e9)
    # softmax over the pair; clamp so a missing token (−1e9) can't overflow exp()
    return 1.0 / (1.0 + math.exp(max(-700.0, min(700.0, lf - lt))))


async def classify(message: str, *, timeout_ms: int | None = None) -> ClfResult | None:
    """P(true) for one message, or None if the sidecar is off, slow, or broken."""
    if not settings.emergency_clf_url or not message.strip():
        return None
    timeout = (timeout_ms or settings.emergency_clf_timeout_ms) / 1000
    t0 = time.perf_counter()
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(base_url=settings.emergency_clf_url, timeout=timeout) as client:
                r = await client.post("/completion", json={
                    "prompt": render_prompt(message), "n_predict": 1, "temperature": 0,
                    "n_probs": 20, "cache_prompt": True,
                })
                r.raise_for_status()
                p = _p_true_from_response(r.json())
    except TimeoutError:
        logger.info("emergency_clf_timeout", extra={"timeout_ms": int(timeout * 1000)})
        return None
    except Exception as exc:
        logger.warning("emergency_clf_error", extra={"error": str(exc)[:200]})
        return None
    return ClfResult(
        p_true=p,
        decided=p >= settings.emergency_clf_threshold,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )


def resolve(keyword: EmergencyCheckResult, clf: ClfResult | None, mode: str) -> EmergencyCheckResult:
    """Merge keyword and classifier verdicts according to the rollout mode."""
    if mode == "union":
        detected = keyword.detected or (clf is not None and clf.decided)
    elif mode == "clf":
        detected = clf.decided if clf is not None else keyword.detected
    else:  # off / shadow
        detected = keyword.detected
    return EmergencyCheckResult(detected=detected, keywords=keyword.keywords if detected else [])
