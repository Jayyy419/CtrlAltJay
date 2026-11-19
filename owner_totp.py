"""Authenticator app codes for owner sign-in (RFC 6238, 30-second, 6 digits).

The secret lives in SSM as a SecureString. Until it exists, sign-in is the
passcode alone, so deploying this can't lock the owner out; deleting the
parameter turns the code check off again.
"""
import base64
import hashlib
import hmac
import io
import os
import secrets
import struct
import time

import boto3

# Unset (local development) means no code step. The deployed app always has
# it set by the template.
PARAM = os.getenv("ADMIN_TOTP_SSM_PARAM", "")
STEP = 30
DIGITS = 6
# One step either side covers a phone clock that's up to 30 seconds out.
DRIFT = 1
ENROLLED_TTL = 60
RECOVERY_COUNT = 8

_ssm = None
_cache = {"at": 0.0, "secret": None}


def _client():
    global _ssm
    if _ssm is None:
        _ssm = boto3.client("ssm")
    return _ssm


def _read_secret(force=False):
    if not PARAM:
        return None
    if not force and time.time() - _cache["at"] < ENROLLED_TTL:
        return _cache["secret"]
    try:
        value = _client().get_parameter(Name=PARAM, WithDecryption=True)["Parameter"]["Value"].strip()
    except _client().exceptions.ParameterNotFound:
        value = None
    _cache.update(at=time.time(), secret=value or None)
    return _cache["secret"]


def enrolled():
    return _read_secret() is not None


def forget_cache():
    _cache["at"] = 0.0


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code_at(secret, step):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10 ** DIGITS).zfill(DIGITS)


def matching_step(secret, code, last_step=-1, now=None):
    """The time step the code belongs to, or None. Steps at or before
    last_step are refused, so a code can't be used twice."""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != DIGITS or not secret:
        return None
    current = int((now if now is not None else time.time()) // STEP)
    for step in range(current - DRIFT, current + DRIFT + 1):
        if step > last_step and hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def otpauth_uri(secret):
    return f"otpauth://totp/CtrlAltJay:owner?secret={secret}&issuer=CtrlAltJay&digits={DIGITS}&period={STEP}"


def qr_svg(text):
    import segno

    buf = io.BytesIO()
    # omitsize swaps the fixed width and height for a viewBox, so the page
    # can scale the whole code without cropping its corner markers.
    segno.make(text, error="m").save(buf, kind="svg", scale=5, border=4, dark="#000000", light="#ffffff",
                                     xmldecl=False, omitsize=True, title="QR code for your authenticator app")
    return buf.getvalue().decode()


def save_secret(secret):
    if not PARAM:
        raise RuntimeError("ADMIN_TOTP_SSM_PARAM is not set")
    try:
        _client().put_parameter(Name=PARAM, Value=secret, Type="SecureString",
                                Tags=[{"Key": "Project", "Value": "CtrlAltJay"}])
    except _client().exceptions.ParameterAlreadyExists:
        # Tags can only be set when a parameter is created.
        _client().put_parameter(Name=PARAM, Value=secret, Type="SecureString", Overwrite=True)
    _cache.update(at=time.time(), secret=secret)


def current_secret():
    return _read_secret(force=True)


def new_recovery_codes():
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    codes = []
    for _ in range(RECOVERY_COUNT):
        raw = "".join(secrets.choice(alphabet) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def recovery_hash(code):
    # Recovery codes are random and long, so a plain hash is enough; a slow
    # hash would only make each sign-in slower.
    cleaned = "".join(ch for ch in str(code or "").upper() if ch.isalnum())
    return hashlib.sha256(cleaned.encode()).hexdigest()
