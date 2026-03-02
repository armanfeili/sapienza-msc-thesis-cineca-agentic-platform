"""
MCP Tool: output.summarize

Portable summarization helpers with safe defaults and deterministic simulate mode.

Supported actions
-----------------
- extract
    Lightweight extractive summary (no model call).
    Payload:
      {
        "text": "...",              # required
        "sentences": 5,             # number of sentences to keep (default 5)
        "ratio": null,              # OR fraction of sentences to keep (0..1)
        "lower": true,              # lowercase for keyword scoring (default true)
      }
    Returns: { ok, action:"extract", summary, sentences, ratio?, stats }

- abstractive
    Abstractive summary using the LLM adapter (simulate=true by default).
    Payload:
      {
        "text": "...",              # required
        "simulate": true,           # default true (no external calls, deterministic)
        "sentences": 5,             # target length (guideline)
        "style": "plain|bullets|keypoints|academic",  # default "plain"
        "temperature": 0.2,         # optional
        "max_tokens": 256           # optional
      }
    Returns: { ok, action:"abstractive", simulate, summary, model?, provider?, stats }

- map_reduce
    Summarize long text by chunking → per-chunk abstractive → final combine.
    Payload:
      {
        "text": "...",              # required
        "simulate": true,           # default true (deterministic)
        "chunk_chars": 3200,        # approx 800 tokens @4 chars/token
        "overlap": 200,             # char overlap between chunks
        "sentences": 5,             # target final length
        "temperature": 0.2,
        "max_tokens": 256
      }
    Returns: { ok, action:"map_reduce", simulate, chunks, summary, stats }

- keywords
    Extract top-N keywords (tf-like, stopwords removed).
    Payload:
      {
        "text": "...",              # required
        "top_k": 15,                # default 15
        "lower": true               # default true
      }
    Returns: { ok, action:"keywords", keywords:[{term, score}], stats }

- tl_dr
    Ultra-compact summary (1–2 sentences). Uses `abstractive` internally.
    Payload:
      { "text": "...", "simulate": true }
    Returns: { ok, action:"tl_dr", simulate, summary }

Notes
-----
- `simulate=true` avoids live model calls and returns deterministic local results.
- All adapter access goes through src.adapters.llm.LLMAdapter.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import Counter
from collections.abc import Iterable
from contextlib import suppress
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.adapters.llm import LLMAdapter

# ── Logging (structlog-aware if configured) ───────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── Adapter (optional for abstractive) ───────────────────────────────────────
with suppress(Exception):
    from src.adapters.llm import LLMAdapter  # type: ignore
HAS_ADAPTER = "LLMAdapter" in globals()

# ── MCP decorator (best-effort) ────────────────────────────────────────────────
with suppress(Exception):
    from src.mcp.core.decorators import mcp_tool  # type: ignore
if "mcp_tool" not in globals():

    def mcp_tool(**_deco_kwargs: Any):  # type: ignore[misc]
        def _identity(fn):  # type: ignore[no-untyped-def]
            return fn

        return _identity


# ── ToolContext (best-effort) ──────────────────────────────────────────────────
with suppress(Exception):
    from src.mcp.core.context import ToolContext  # type: ignore
if "ToolContext" not in globals():

    class ToolContext:  # type: ignore[no-redef]
        def __init__(self, **kw: Any) -> None:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Text utilities
# ─────────────────────────────────────────────────────────────────────────────
_SENT_SPLIT_RE = re.compile(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=[.!?])\s+|\n{2,}")
_WORD_RE = re.compile(r"[A-Za-z0-9_']+")

_STOPWORDS = {
    # Minimal English stopword set; extend as needed
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "if",
    "then",
    "else",
    "when",
    "while",
    "for",
    "of",
    "on",
    "in",
    "to",
    "from",
    "by",
    "with",
    "without",
    "as",
    "at",
    "into",
    "over",
    "under",
    "above",
    "below",
    "it",
    "its",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "this",
    "that",
    "these",
    "those",
    "there",
    "here",
    "not",
    "no",
    "yes",
    "do",
    "does",
    "did",
    "done",
    "can",
    "could",
    "should",
    "would",
    "may",
    "might",
    "will",
    "just",
    "than",
    "too",
    "very",
    "more",
    "most",
    "such",
    "so",
    "some",
    "any",
    "each",
    "many",
    "much",
    "also",
    "we",
    "you",
    "they",
    "he",
    "she",
    "i",
    "me",
    "my",
    "our",
    "your",
    "their",
    "them",
    "his",
    "her",
    "ours",
    "yours",
    "theirs",
}


def _sentences(text: str) -> list[str]:
    # Split by punctuation/newlines; keep basic sentence structure
    parts = [s.strip() for s in _SENT_SPLIT_RE.split(text) if s and s.strip()]
    # If nothing split, treat entire text as one sentence
    return parts or ([text.strip()] if text.strip() else [])


def _words(text: str, lower: bool = True) -> list[str]:
    s = text.lower() if lower else text
    return _WORD_RE.findall(s)


def _keyword_scores(text: str, *, lower: bool = True, stopwords: Iterable[str] | None = None) -> Counter:
    stop = set(stopwords or _STOPWORDS)
    toks = [w for w in _words(text, lower=lower) if w not in stop and len(w) > 2]
    return Counter(toks)


def _extractive_summary(
    text: str, *, sentences: int | None = None, ratio: float | None = None, lower: bool = True
) -> tuple[str, list[int]]:
    sents = _sentences(text)
    if not sents:
        return "", []

    n = len(sents)
    # Determine how many sentences to keep
    if ratio is not None and 0 < ratio < 1:
        k = max(1, round(n * ratio))
    else:
        k = int(sentences or 5)
        k = max(1, min(k, n))

    # Score by keyword weights + small lead bias
    tf = _keyword_scores(text, lower=lower)

    def score_sentence(idx: int, s: str) -> float:
        wsum = sum(tf.get(w, 0) for w in _words(s, lower=lower))
        lead_bonus = max(0.0, (n - idx) / n) * 0.15  # slight preference for earlier sentences
        return float(wsum) + lead_bonus

    ranked = sorted(((idx, score_sentence(idx, s)) for idx, s in enumerate(sents)), key=lambda x: x[1], reverse=True)
    top_idx = sorted([idx for idx, _ in ranked[:k]])  # preserve original order
    summary = " ".join(sents[i] for i in top_idx)
    return summary, top_idx


def _approx_token_count(text: str) -> int:
    if not text:
        return 0
    # crude heuristic: 4 chars ≈ 1 token
    return max(1, round(len(text) / 4.0))


def _chunk_text(text: str, *, chunk_chars: int, overlap: int) -> list[str]:
    if chunk_chars <= 0:
        return [text]
    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        j = min(n, i + chunk_chars)
        chunk = text[i:j]
        chunks.append(chunk)
        if j >= n:
            break
        i = max(j - overlap, i + 1)
    return chunks


def _adapter(**overrides: Any) -> LLMAdapter | None:
    if not HAS_ADAPTER:
        return None
    with suppress(Exception):
        return LLMAdapter(**{k: v for k, v in overrides.items() if v is not None})
    with suppress(Exception):
        return LLMAdapter()  # type: ignore[call-arg]
    return None


def _call_abstractive(
    prompt: str, *, simulate: bool, temperature: float | None, max_tokens: int | None
) -> tuple[str, dict[str, Any]]:
    """
    Best-effort abstractive call via adapter; when simulate=True or adapter missing,
    return a deterministic local result based on hash.
    """
    info: dict[str, Any] = {}
    if simulate or not HAS_ADAPTER:
        # Deterministic local "summary": hash-based sentence selection for consistency
        sents = _sentences(prompt)
        if not sents:
            return "OK", info
        # Use hash to deterministically select sentences
        text_hash = int(hashlib.md5(prompt.encode("utf-8"), usedforsecurity=False).hexdigest(), 16)
        num_sents = min(3, len(sents))
        # Select sentences based on hash modulo
        indices = sorted([(text_hash + i) % len(sents) for i in range(num_sents)])
        text = " ".join(sents[i] for i in indices if i < len(sents))
        return text or "OK", info

    a = _adapter()
    if a is None:
        sents = _sentences(prompt)
        text = " ".join(sents[:3]) if sents else "OK"
        return text, info

    with suppress(Exception):
        meta = getattr(a, "info", None)
        if callable(meta):
            info = meta() or {}
        else:
            for k in ("provider", "model"):
                with suppress(Exception):
                    info[k] = getattr(a, k)  # type: ignore[attr-defined]

    # Try common chat signature
    with suppress(Exception):
        res = a.chat(prompt=prompt, temperature=temperature or 0.2, max_tokens=max_tokens or 256)  # type: ignore[attr-defined]
        if isinstance(res, dict):
            return str(res.get("text") or res.get("content") or res), info
        return str(res), info

    # Positional fallback
    with suppress(Exception):
        res = a.chat(prompt)  # type: ignore[attr-defined]
        if isinstance(res, dict):
            return str(res.get("text") or res.get("content") or res), info
        return str(res), info

    # Last resort
    sents = _sentences(prompt)
    text = " ".join(sents[:3]) if sents else "OK"
    return text, info


# ─────────────────────────────────────────────────────────────────────────────
# Actions
# ─────────────────────────────────────────────────────────────────────────────
def _act_extract(payload: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    """Extractive summary using keyword scoring."""
    text = str(payload.get("text") or "").strip()
    if not text:
        raise ValueError("extract requires 'text'")
    sentences = payload.get("sentences")
    ratio = payload.get("ratio")
    lower = bool(payload.get("lower", True))

    t0 = time.perf_counter()
    summary, idx = _extractive_summary(text, sentences=sentences, ratio=ratio, lower=lower)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "ok": True,
        "action": "extract",
        "summary": summary,
        "sentences": len(idx),
        "ratio": ratio,
        "indices": idx,
        "stats": {
            "elapsed_ms": elapsed_ms,
            "words": len(_words(text)),
            "sentences": len(_sentences(text)),
        },
    }


def _build_prompt(style: str, sentences: int, text: str, brief: bool = False) -> str:
    style = (style or "plain").lower()
    guidelines = {
        "plain": "- Write a concise, neutral summary.\n- No bullet points.\n",
        "bullets": "- Summarize as bullet points.\n- Each bullet must be crisp.\n",
        "keypoints": "- Provide key points only.\n- Use short bullets.\n",
        "academic": "- Use formal academic tone.\n- Define key terms briefly.\n",
    }.get(style, "- Write a concise, neutral summary.\n")

    length = "1–2 sentences" if brief else f"~{max(1, int(sentences))} sentences"
    return (
        "Summarize the following content.\n"
        f"- Target length: {length}\n"
        f"{guidelines}"
        "- Do not introduce information not present in the text.\n\n"
        "=== BEGIN TEXT ===\n"
        f"{text}\n"
        "=== END TEXT ==="
    )


def _act_abstractive(
    payload: dict[str, Any], ctx: ToolContext | None = None, *, brief: bool = False
) -> dict[str, Any]:
    """Abstractive summary using LLM adapter (with deterministic simulate mode)."""
    text = str(payload.get("text") or "").strip()
    if not text:
        raise ValueError("abstractive requires 'text'")
    simulate = bool(payload.get("simulate", True))
    sentences = int(payload.get("sentences", 5))
    style = str(payload.get("style") or "plain")
    temperature = payload.get("temperature")
    max_tokens = payload.get("max_tokens")

    prompt = _build_prompt(style, sentences, text, brief=brief)

    t0 = time.perf_counter()
    summary, info = _call_abstractive(prompt, simulate=simulate, temperature=temperature, max_tokens=max_tokens)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "ok": True,
        "action": "tl_dr" if brief else "abstractive",
        "simulate": simulate,
        "summary": summary.strip(),
        "model": info.get("model"),
        "provider": info.get("provider"),
        "stats": {
            "elapsed_ms": elapsed_ms,
            "input_tokens_approx": _approx_token_count(text),
        },
    }


def _act_map_reduce(payload: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    """Map-reduce summarization: chunk → summarize → recombine."""
    text = str(payload.get("text") or "").strip()
    if not text:
        raise ValueError("map_reduce requires 'text'")
    simulate = bool(payload.get("simulate", True))
    chunk_chars = int(payload.get("chunk_chars", 3200))
    overlap = int(payload.get("overlap", 200))
    sentences = int(payload.get("sentences", 5))
    temperature = payload.get("temperature")
    max_tokens = payload.get("max_tokens")

    chunks = _chunk_text(text, chunk_chars=chunk_chars, overlap=overlap)
    partials: list[str] = []
    t0 = time.perf_counter()

    # Map phase: summarize each chunk briefly
    for ch in chunks:
        p = _build_prompt("plain", max(1, sentences // 2), ch, brief=False)
        s, _info = _call_abstractive(p, simulate=simulate, temperature=temperature, max_tokens=max_tokens)
        partials.append(s.strip())

    # Reduce phase: combine partials into final brief summary
    combined = "\n\n".join(f"- {p}" for p in partials if p)
    reduce_prompt = (
        "You are given partial summaries of a longer document.\n"
        "Synthesize them into a single, cohesive summary.\n"
        f"- Target length: ~{max(1, sentences)} sentences\n"
        "- Avoid redundancy.\n\n"
        "=== PARTIAL SUMMARIES ===\n"
        f"{combined}\n"
        "=== END ==="
    )
    final, info = _call_abstractive(reduce_prompt, simulate=simulate, temperature=temperature, max_tokens=max_tokens)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "ok": True,
        "action": "map_reduce",
        "simulate": simulate,
        "chunks": len(chunks),
        "summary": final.strip(),
        "partials": partials,
        "model": info.get("model"),
        "provider": info.get("provider"),
        "stats": {
            "elapsed_ms": elapsed_ms,
            "input_tokens_approx": _approx_token_count(text),
            "avg_chunk_size": round(sum(len(c) for c in chunks) / max(1, len(chunks))),
        },
    }


def _act_keywords(payload: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    """Extract top-K keywords using TF scoring."""
    text = str(payload.get("text") or "").strip()
    if not text:
        raise ValueError("keywords requires 'text'")
    top_k = int(payload.get("top_k", 15))
    lower = bool(payload.get("lower", True))

    tf = _keyword_scores(text, lower=lower)
    most = tf.most_common(top_k)
    items = [{"term": t, "score": int(s)} for t, s in most]

    return {
        "ok": True,
        "action": "keywords",
        "keywords": items,
        "stats": {"unique": len(tf), "total_terms": sum(tf.values())},
    }


def _act_tldr(payload: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    """Ultra-compact TL;DR summary (1-2 sentences)."""
    # Delegate to abstractive with brief=True
    return _act_abstractive(payload, ctx, brief=True)


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────
@mcp_tool(tool_name="output.summarize", required_scope="output:summarize")
def invoke(payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Entry for output.summarize tool. See module docstring for supported actions.
    """
    payload = payload or {}
    ctx = kwargs.get("ctx") or ToolContext()
    action = str(payload.get("action") or "extract").strip().lower()
    if action not in {"extract", "abstractive", "map_reduce", "keywords", "tl_dr"}:
        raise ValueError("action must be one of: extract, abstractive, map_reduce, keywords, tl_dr")

    if action == "extract":
        result = _act_extract(payload, ctx)
    elif action == "abstractive":
        result = _act_abstractive(payload, ctx, brief=False)
    elif action == "map_reduce":
        result = _act_map_reduce(payload, ctx)
    elif action == "keywords":
        result = _act_keywords(payload, ctx)
    else:
        result = _act_tldr(payload, ctx)

    return result


# Back-compat aliases
run = invoke
handle = invoke
