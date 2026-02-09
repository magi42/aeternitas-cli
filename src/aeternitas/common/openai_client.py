from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class OpenAIError(RuntimeError):
    pass


def call_openai_responses(
    api_key: str,
    model: str,
    input_text: str,
    temperature: float = 0.2,
    max_output_tokens: Optional[int] = None,
    max_retries: int = 5,
    base_delay: float = 1.0,
) -> str:
    url = "https://api.openai.com/v1/responses"
    payload: Dict[str, Any] = {
        "model": model,
        "input": input_text,
        "temperature": temperature,
    }
    if max_output_tokens is not None:
        payload["max_output_tokens"] = max_output_tokens

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8")
            last_err = None
            break
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                print(f"[openai] HTTP {e.code}, retrying in {delay:.1f}s...", file=sys.stderr, flush=True)
                time.sleep(delay)
                continue
            try:
                body = e.read().decode("utf-8")
            except Exception:
                body = ""
            msg = f"OpenAI request failed: HTTP {e.code}"
            if body:
                msg += f" | {body}"
            raise OpenAIError(msg) from e
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                print(f"[openai] Error, retrying in {delay:.1f}s...", file=sys.stderr, flush=True)
                time.sleep(delay)
                continue
            raise OpenAIError(f"OpenAI request failed: {e}") from e

    if last_err is not None:
        raise OpenAIError(f"OpenAI request failed: {last_err}")

    try:
        obj = json.loads(body)
    except Exception as e:
        raise OpenAIError("OpenAI response was not valid JSON") from e

    if obj.get("error"):
        err = obj.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("code") or err.get("type") or "Unknown OpenAI error"
            details = []
            for k in ("type", "code", "param"):
                if err.get(k):
                    details.append(f"{k}={err.get(k)}")
            if details:
                msg = f"{msg} ({', '.join(details)})"
            raise OpenAIError(str(msg))
        if err is None:
            raise OpenAIError(f"Unknown OpenAI error (empty): {obj}")
        raise OpenAIError(str(err) or f"Unknown OpenAI error: {obj}")

    # Responses API returns output_text via output[0].content or output_text field
    if isinstance(obj, dict):
        if isinstance(obj.get("output_text"), str):
            return obj["output_text"]
        output = obj.get("output")
        if isinstance(output, list) and output:
            for item in output:
                content = item.get("content") if isinstance(item, dict) else None
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "output_text":
                            text = c.get("text")
                            if isinstance(text, str):
                                return text

    raise OpenAIError("OpenAI response did not contain text output")
