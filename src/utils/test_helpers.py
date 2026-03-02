"""
Test endpoint helper utilities.

Provides prompt normalization, response extraction, and model-specific quirk handling
to ensure consistent, high-quality test responses across different LLM providers.
"""
import hashlib
import json
import re
from typing import Any


def hash_prompt(prompt: str) -> str:
    """
    Generate SHA256 hash of prompt for logging (avoid PII in logs).

    Args:
        prompt: Input prompt text

    Returns:
        Hex digest of SHA256 hash
    """
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def build_system_message(
    model_id: str,
    one_sentence: bool = True,
    format_hint: str | None = None,
) -> str:
    """
    Build system message with model-specific optimizations.

    Args:
        model_id: Model identifier (e.g., "qwen2.5:3b", "phi3:mini")
        one_sentence: If True, enforce single-sentence responses
        format_hint: Optional format guidance ("list", "poem", etc.)

    Returns:
        System message string
    """
    model_lower = model_id.lower()

    # Base message - keep simple and direct
    base = "You are a helpful assistant."

    # One-sentence constraint (skip for creative formats)
    if one_sentence and format_hint not in ("poem", "list", "code"):
        base += " Answer in one short sentence. Do not list options."

    # Model-specific adjustments
    # Qwen: Prevent self-questions and conversation chains
    if "qwen" in model_lower:
        base += " Do not ask follow-up questions."

    # Phi-3: Keep it simple, more instruction makes it worse
    # For Phi-3, simpler system messages work better
    if "phi" in model_lower or "phi3" in model_lower:
        if format_hint == "poem":
            # Simple directive works better than restrictive rules
            base = "You write poetry directly without explanations."
        elif one_sentence:
            base = "You are concise. Answer in one sentence."

    # Format-specific guidance (for non-Phi models or as supplement)
    if format_hint == "list" and "phi" not in model_lower:
        base += " Return a bullet list."
    elif format_hint == "code" and "phi" not in model_lower:
        base += " Return only code without explanations."

    return base


def normalize_request_to_messages(
    prompt: str | None = None,
    messages: list[dict[str, str]] | None = None,
    model_id: str = "",
    one_sentence: bool = True,
    no_system: bool = False,
    format_hint: str | None = None,
    **kwargs,  # Ignore unknown kwargs for forward compatibility
) -> list[dict[str, str]]:
    """
    Normalize prompt/messages to OpenAI-compatible chat format.

    Args:
        prompt: Simple prompt string (converted to user message)
        messages: Pre-formatted messages array
        model_id: Model identifier for model-specific adjustments
        one_sentence: Enforce single-sentence responses
        no_system: Skip system message injection
        format_hint: Optional format guidance ("poem", "list", etc.)
        **kwargs: Additional parameters (ignored for forward compatibility)

    Returns:
        List of message dicts with role/content
    """
    # Log warning if unknown kwargs provided (helps catch bugs)
    if kwargs:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            "normalize_request_to_messages: ignoring unknown kwargs", extra={"unknown_kwargs": list(kwargs.keys())}
        )

    result = []
    model_lower = model_id.lower()
    is_phi3 = "phi" in model_lower or "phi3" in model_lower

    # Add system message (unless explicitly disabled or Phi-3 with format_hint)
    # Phi-3 works better with instructions in user prompt for creative tasks
    if not no_system and not (is_phi3 and format_hint):
        system_msg = build_system_message(model_id, one_sentence=one_sentence, format_hint=format_hint)
        result.append({"role": "system", "content": system_msg})

    # Convert prompt to messages or pass through existing messages
    if messages:
        result.extend(messages)
    elif prompt:
        # For Phi-3 with format hints, append instruction to user prompt
        user_content = prompt
        if is_phi3 and format_hint == "poem":
            user_content = f"{prompt} Just write the haiku, nothing else."
        elif is_phi3 and format_hint == "list":
            user_content = f"{prompt} Return only a bullet list."

        result.append({"role": "user", "content": user_content})

    return result


def get_stop_sequences(
    one_sentence: bool = True,
    model_id: str = "",
    custom_stop: list[str] | None = None,
    **kwargs,  # Ignore unknown kwargs for forward compatibility
) -> list[str]:
    """
    Get appropriate stop sequences for test calls.

    Args:
        one_sentence: If True, add aggressive sentence-ending stops
        model_id: Model identifier for model-specific stops
        custom_stop: User-provided stop sequences (merged with defaults)
        **kwargs: Additional parameters (ignored for forward compatibility)

    Returns:
        List of stop sequences
    """
    # Log warning if unknown kwargs provided (helps catch bugs)
    if kwargs:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning("get_stop_sequences: ignoring unknown kwargs", extra={"unknown_kwargs": list(kwargs.keys())})

    # Base stop sequences (prevent code dumps and excessive verbosity)
    stops = ["\n\n", "```", "---"]

    # One-sentence mode: stop at newline
    if one_sentence:
        stops.append("\n")

    # Model-specific stops
    model_lower = model_id.lower()

    # Qwen: Stop at questions to prevent Q&A chains
    if "qwen" in model_lower and one_sentence:
        stops.extend(["? ", "?\n"])

    # Merge custom stops (deduplicate)
    if custom_stop:
        stops = list(set(stops + custom_stop))

    return stops


def extract_text_from_response(
    response_data: Any,
    model_id: str = "",
) -> tuple[str, dict[str, int] | None]:
    """
    Robust extraction of text and usage from provider response.

    Handles:
    - Normal dict responses with choices[].message.content
    - Stringified JSON responses (Mistral quirk)
    - Missing/null content with fallback to .text
    - Chat template tokens cleanup

    Args:
        response_data: Provider response (dict, string, or other)
        model_id: Model identifier for model-specific cleanup

    Returns:
        Tuple of (extracted_text, usage_dict)
    """
    text = ""
    usage = None

    # Handle stringified JSON (Mistral case)
    if isinstance(response_data, str):
        try:
            response_data = json.loads(response_data)
        except json.JSONDecodeError:
            # Not JSON, treat as raw text
            text = response_data

    # Extract from dict response
    if isinstance(response_data, dict):
        # Extract usage if present
        if "usage" in response_data and isinstance(response_data["usage"], dict):
            u = response_data["usage"]
            usage = {
                "prompt_tokens": int(u.get("prompt_tokens", 0)),
                "completion_tokens": int(u.get("completion_tokens", 0)),
                "total_tokens": int(u.get("total_tokens", 0)),
            }

        # Extract text from choices
        choices = response_data.get("choices", [])
        if choices:
            first = choices[0]
            # Try message.content first
            if isinstance(first, dict):
                msg = first.get("message", {})
                if isinstance(msg, dict):
                    text = msg.get("content") or msg.get("text") or ""
                # Fallback to top-level text
                if not text:
                    text = first.get("text", "")

        # Last resort: stringify the dict
        if not text:
            text = str(response_data)
    else:
        # Non-dict response: stringify
        text = str(response_data)

    # Normalize text
    text = normalize_output_text(text, model_id)

    return text, usage


def normalize_output_text(text: str, model_id: str = "") -> str:
    """
    Clean and normalize LLM output text.

    - Strip whitespace
    - Remove MCQ patterns (A) B) C) D) etc.)
    - Remove chat template tokens
    - Remove code fences
    - Collapse multiple blank lines
    - Trim trailing newlines
    - Handle Phi-3 JSON output quirk

    Args:
        text: Raw output text
        model_id: Model identifier for model-specific cleanup

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    # Strip leading/trailing whitespace
    text = text.strip()

    # Unescape common escape sequences (handle double-escaped text)
    text = text.replace("\\n", "\n")
    text = text.replace("\\t", "\t")
    text = text.replace("\\r", "\r")

    # Phi-3 quirk: Sometimes outputs JSON-like structures
    # Example: "',\n 'output': 'actual text'}"
    model_lower = model_id.lower()
    if "phi" in model_lower or "phi3" in model_lower:
        # Try to extract actual content from JSON-like output
        # Pattern: look for quoted text after 'output': or similar keys
        match = re.search(r"['\"](?:output|content|support|text)['\"]:\s*['\"](.+?)['\"]", text, re.DOTALL)
        if match:
            text = match.group(1)
        else:
            # Remove leading JSON artifacts like "',\n 'support': "
            text = re.sub(r"^[',\s]*['\"](?:output|content|support|text)['\"]:\s*['\"]", "", text)
            text = re.sub(r"['\"]}\s*$", "", text)  # Remove trailing '"}

    # Remove chat template markers (Phi-3, Llama, etc.)
    # More aggressive cleanup for all template tokens
    text = re.sub(r"<\|end\|>", "", text)
    text = re.sub(r"<\|assistant\|>", "", text)
    text = re.sub(r"<\|user\|>", "", text)
    text = re.sub(r"<\|system\|>", "", text)
    text = re.sub(r"<\|.*?\|>", "", text)  # Catch any other template tokens
    text = re.sub(r"rougeactor\|?>", "", text)  # Remove rouge/actor artifacts

    # Remove MCQ patterns at line starts: "A) ", "B.", etc.
    # Match: optional whitespace, letter A-D, optional period or paren, space/tab
    text = re.sub(r"^(?:\s*[A-D][\)\.]\s+)", "", text, flags=re.MULTILINE)

    # Remove "Options:", "Answer choices:", etc. lines
    text = re.sub(r"(?i)^(?:options?|answer\s+choices?|choices?):\s*$", "", text, flags=re.MULTILINE)

    # Remove code fences (```language ... ```)
    text = re.sub(r"```[a-z]*\n?", "", text)

    # Collapse multiple blank lines to single newline
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    # Right-trim trailing newlines/spaces
    text = text.rstrip("\n ")

    return text


def truncate_to_sentence(text: str, one_sentence: bool = True) -> str:
    """
    Truncate text to first sentence if model rambles.

    For one_sentence=True:
    - Finds first sentence terminator (. ! ?)
    - Truncates everything after
    - Replaces internal newlines with spaces
    - Right-trims result

    Args:
        text: Input text
        one_sentence: If True, truncate to first sentence

    Returns:
        Truncated text (or original if one_sentence=False)
    """
    if not one_sentence or not text:
        return text

    # Replace internal newlines with single spaces for one-sentence mode
    text = re.sub(r"\n+", " ", text)

    # Find first sentence-ending punctuation
    match = re.search(r"[.!?](?:\s|$)", text)
    if match:
        # Include the punctuation, exclude trailing whitespace
        return text[: match.end()].rstrip()

    # No sentence end found, return as-is (but trimmed)
    return text.rstrip()


def estimate_usage(
    prompt: str,
    output: str,
    messages: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Estimate token usage when provider doesn't return usage.

    Uses simple heuristic: ~4 chars per token (rough average for English).

    Args:
        prompt: Input prompt (if messages not provided)
        output: Output text
        messages: Message array (if prompt not provided)

    Returns:
        Usage dict with estimated=True flag
    """
    # Estimate prompt tokens
    prompt_text = " ".join(m.get("content", "") for m in messages) if messages else prompt

    prompt_tokens = max(1, len(prompt_text) // 4)
    completion_tokens = max(1, len(output) // 4)

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated": True,
    }


# Cache for warm-up tracking
_WARMUP_CACHE: dict[str, float] = {}


def should_warmup(instance_id: str, ttl_seconds: float = 300) -> bool:
    """
    Check if instance needs warm-up call.

    Args:
        instance_id: Instance identifier
        ttl_seconds: Cache TTL (default 5 minutes)

    Returns:
        True if warm-up needed
    """
    import time

    now = time.time()
    last_warmup = _WARMUP_CACHE.get(instance_id, 0)
    return (now - last_warmup) > ttl_seconds


def mark_warmed(instance_id: str):
    """
    Mark instance as warmed up.

    Args:
        instance_id: Instance identifier
    """
    import time

    _WARMUP_CACHE[instance_id] = time.time()
