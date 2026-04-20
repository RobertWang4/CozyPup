"""LLM-driven query expansion for RAG retrieval.

Problem this solves: a Chinese colloquial query like "狗拉肚子" or "猫甲亢"
lives in a different embedding region than the English article content it
should match. Instead of (or in addition to) article-side aliases, we
expand the query into 2-3 canonical variants and retrieve the union.

Expansion runs against a cheap model and is best-effort — any failure falls
back to the original query. Results are cached in-process so repeat queries
don't pay the LLM cost twice.

This module NEVER generates medical content. It only rephrases the user's
question into alternate wordings. The retrieved context still comes from
the authored, source-attributed knowledge base.
"""

from __future__ import annotations

import json
import logging
from collections import OrderedDict

import litellm

from app.config import settings

logger = logging.getLogger(__name__)

_CACHE: "OrderedDict[str, list[str]]" = OrderedDict()

_EXPAND_PROMPT = (
    "You rewrite pet-health search queries into alternate phrasings for a "
    "bilingual (zh/en) vector-search index. Given ONE user query, return a "
    "JSON array of 1-2 alternate phrasings that preserve the exact meaning "
    "but use different vocabulary — colloquial ↔ clinical, zh ↔ en. "
    "Do NOT invent symptoms, do NOT add facts, do NOT broaden the question.\n\n"
    "Rules:\n"
    "- Output ONLY a JSON array of strings, no prose.\n"
    "- 1-2 items. Empty array [] if no useful alternate exists.\n"
    "- Keep each variant short (< 80 chars).\n"
    "- If the query is Chinese, include at least one English variant.\n"
    "- If the query is English, you MAY include a Chinese variant.\n"
    '- Examples:\n'
    '  "狗拉肚子" → ["dog diarrhea loose stool", "狗腹泻"]\n'
    '  "猫甲亢" → ["feline hyperthyroidism", "老猫甲状腺亢进"]\n'
    '  "dog ate chocolate" → ["狗误食巧克力中毒", "chocolate toxicity in dogs"]\n'
    '  "dog vaccine" → ["犬疫苗接种"]\n'
)


async def expand_query(query: str) -> list[str]:
    """Return [original, ...variants]. Variants are LLM-generated alternate phrasings.

    Always includes the original query as the first element. Extra variants
    are appended up to `settings.rag_query_expansion_variants`. On any LLM
    failure, returns just [query].
    """
    query = query.strip()
    if not query:
        return [query]

    if not settings.rag_enable_query_expansion:
        return [query]

    max_variants = max(0, settings.rag_query_expansion_variants)
    if max_variants == 0:
        return [query]

    cache_size = settings.rag_embed_cache_size  # reuse the same cap policy
    if cache_size > 0 and query in _CACHE:
        _CACHE.move_to_end(query)
        return _CACHE[query]

    variants: list[str] = []
    try:
        from app.agents import llm_extra_kwargs  # lazy: avoid circular import
        response = await litellm.acompletion(
            model=settings.model,
            messages=[
                {"role": "system", "content": _EXPAND_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.0,
            max_tokens=120,
            **llm_extra_kwargs(),  # noqa: F821 — lazy-imported above
        )
        raw = response.choices[0].message.content or ""
        # Strip common code-fence wrappers the model adds despite instructions.
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, str):
                    s = item.strip()
                    if s and s != query and s not in variants and len(s) < 200:
                        variants.append(s)
                if len(variants) >= max_variants:
                    break
    except Exception as exc:
        logger.info("query_expansion_failed", extra={
            "query_preview": query[:60],
            "error": str(exc)[:200],
        })
        variants = []

    result = [query] + variants

    if cache_size > 0:
        _CACHE[query] = result
        while len(_CACHE) > cache_size:
            _CACHE.popitem(last=False)

    return result
