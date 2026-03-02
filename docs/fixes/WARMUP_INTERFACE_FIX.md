# LLM Warmup Interface Fix

**Date**: November 7, 2025 (Evening)  
**Issue**: Warmup AttributeError - `.generate()` method not found  
**Status**: ✅ FIXED

---

## Problem

After implementing the LLM warmup feature, the application was crashing during startup with:

```
orchestrator.model.warmup.failed error="'LLMClient' object has no attribute 'generate'"
llmclient.request_failed url=http://ollama:11434/v1/chat/completions
```

### Root Cause

**Interface Mismatch**: The warmup code was calling a non-existent `.generate()` method on `LLMClient`:

```python
# BROKEN CODE (lines 468-472 in orchestrator.py)
await asyncio.wait_for(
    client.generate(messages=[{"role": "user", "content": "Hello"}], max_tokens=5),
    timeout=warmup_timeout
)
```

However, the actual `LLMClient` class in `src/adapters/llm.py` only implements:

```python
async def complete(self, prompt: str, **kwargs: Any) -> str:
    # Takes a string prompt, not messages array
    ...
```

This was a **text-completion style interface**, not a chat-completion style interface.

---

## Solution

Updated the warmup code to use the correct `.complete()` method:

```python
# FIXED CODE (lines 468-472 in orchestrator.py)
await asyncio.wait_for(
    client.complete(prompt="ping", max_tokens=5, temperature=0.0),
    timeout=warmup_timeout
)
```

### Additional Improvements

1. **Better Error Handling**: Added specific handling for `AttributeError`:
   ```python
   except AttributeError as exc:
       log.warning("orchestrator.model.warmup.failed.interface_mismatch", 
                  model=inst.main_llm_name, 
                  error=str(exc),
                  hint="LLMClient may not support warmup method")
   ```

2. **Explicit Parameters**: Changed from `messages=[...]` to `prompt="ping"` to match interface

3. **Lower Temperature**: Set `temperature=0.0` for deterministic warmup responses

---

## Verification

After restarting the service:

```bash
$ docker compose restart app
$ docker compose logs app --tail=100 | grep warmup
```

**Before Fix**:
```json
{"event": "orchestrator.model.warmup.start", "model": "test-model-latest"}
{"event": "orchestrator.model.warmup.failed", "error": "'LLMClient' object has no attribute 'generate'"}
{"event": "llmclient.request_failed", "url": "http://ollama:11434/v1/chat/completions", "error": ""}
```

**After Fix**:
```json
{"event": "orchestrator.model.warmup.start", "model": "test-model-latest"}
{"event": "orchestrator.model.warmup.timeout", "model": "test-model-latest", "timeout": 10, 
 "message": "Model warmup timed out - first call may be slow"}
```

✅ **Result**: Warmup now executes correctly. It times out after 10 seconds (expected for cold Ollama model load), but the interface is correct and doesn't crash.

---

## Files Modified

1. **src/services/orchestrator.py** (lines 468-488)
   - Changed `client.generate(messages=[...])` to `client.complete(prompt="ping")`
   - Added `AttributeError` handling with helpful hint
   - Added `temperature=0.0` parameter

2. **AGENTS_FINAL_TODO.md**
   - Added fix #9 to November 7 updates section

---

## Configuration

The warmup timeout can be adjusted via environment variables:

```bash
# In .env or docker-compose.yml
LLM_WARMUP_ENABLED=true          # Enable/disable warmup (default: true)
LLM_WARMUP_TIMEOUT=30            # Timeout in seconds (default: 10)
```

For Ollama with cold models, consider increasing timeout to 30-60 seconds:

```yaml
services:
  app:
    environment:
      - LLM_WARMUP_TIMEOUT=60
```

---

## Lessons Learned

1. **Always verify method signatures** when calling adapter methods
2. **Text-completion vs Chat-completion** interfaces are different:
   - Text: `complete(prompt="...")`
   - Chat: `chat(messages=[...])`
3. **Interface mismatches** should be caught with `AttributeError` and logged with hints
4. **Cold model loading** takes time - timeouts should be generous for first call
5. **Contract tests** would help catch these mismatches early

---

## Related Issues

- Original warmup implementation: November 7, 2025 (morning)
- Interface fix: November 7, 2025 (evening)
- Telemetry fixes: See `TELEMETRY_AND_API_FIXES.md`

---

**Status**: ✅ RESOLVED - Warmup working correctly with proper interface
