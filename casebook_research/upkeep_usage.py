"""Token counts from each Claude response, sent to Upkeep for the month's spend.

Upkeep, the owner's portal, prices the counts per project. Only the model name
and token counts leave the app: never prompts, answers or anything about who
asked. Until UPKEEP_USAGE_URL and a usage key are both set this does nothing.

It lives beside the research worker because that function is packaged from
this folder alone; the main app imports it from here, so there's one copy.

A report must never get in the way of the work it describes: every failure is
swallowed, the request gives up after a few seconds and nothing is retried.
It's sent synchronously because Lambda can freeze the process as soon as the
handler returns, which would strand a background send.
"""
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

TIMEOUT_SECONDS = 3
_UNRESOLVED = object()
_key_cache = _UNRESOLVED


def _get(obj, name):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _url():
    base = os.getenv("UPKEEP_USAGE_URL", "").strip().rstrip("/")
    return f"{base}/api/usage/report" if base else ""


def _key():
    """UPKEEP_USAGE_KEY, or the SSM SecureString UPKEEP_USAGE_KEY_SSM_PARAM names.

    Read once per container. A missing parameter counts as no key, so the
    reporter stays off until the owner creates it and the next cold start.
    """
    global _key_cache
    if _key_cache is not _UNRESOLVED:
        return _key_cache
    value = os.getenv("UPKEEP_USAGE_KEY", "").strip()
    param = os.getenv("UPKEEP_USAGE_KEY_SSM_PARAM", "").strip()
    if not value and param:
        try:
            import boto3
            from botocore.config import Config

            ssm = boto3.client("ssm", config=Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 1}))
            value = ssm.get_parameter(Name=param, WithDecryption=True)["Parameter"]["Value"].strip()
        except Exception:  # noqa: BLE001 - no key means no reports, never an error
            value = ""
    _key_cache = value
    return value


def event(message, batch=False):
    """The usage event for one Claude response: a Message, or its JSON as a dict."""
    usage = _get(message, "usage")
    out = {
        "model": str(_get(message, "model") or ""),
        "input_tokens": int(_get(usage, "input_tokens") or 0),
        "output_tokens": int(_get(usage, "output_tokens") or 0),
    }
    for name in ("cache_creation_input_tokens", "cache_read_input_tokens"):
        value = _get(usage, name)
        if value is not None:
            out[name] = int(value)
    one_hour = _get(_get(usage, "cache_creation"), "ephemeral_1h_input_tokens")
    if one_hour is not None:
        out["cache_write_1h_tokens"] = int(one_hour)
    if _get(usage, "speed") == "fast":
        out["speed"] = "fast"
    if batch:
        out["batch"] = True
    geo = _get(usage, "inference_geo")
    if geo:
        out["inference_geo"] = str(geo)
    out["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return out


def request(events, url, key):
    """The POST Upkeep expects: JSON body, the key, and the body's SHA-256.

    The hash header is required because Upkeep sits behind CloudFront origin
    access control, which needs it on any request with a body.
    """
    body = json.dumps({"events": events}, separators=(",", ":")).encode("utf-8")
    return urllib.request.Request(url, data=body, method="POST", headers={
        "content-type": "application/json",
        "X-Upkeep-Key": key,
        "x-amz-content-sha256": hashlib.sha256(body).hexdigest(),
    })


def report(message, batch=False):
    """Send one response's token counts to Upkeep. Never raises."""
    try:
        url = _url()
        if not url or _get(message, "usage") is None:
            return
        key = _key()
        if not key:
            return
        with urllib.request.urlopen(request([event(message, batch)], url, key), timeout=TIMEOUT_SECONDS) as response:
            response.read(256)
    except Exception as exc:  # noqa: BLE001 - Upkeep's answer, or no answer, never matters here
        try:
            status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
            print(json.dumps({"upkeep_usage": "not sent", "error": exc.__class__.__name__, "status": status}), flush=True)
        except Exception:  # noqa: BLE001
            pass
