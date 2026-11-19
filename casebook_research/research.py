"""Casebook research worker.

Invoked asynchronously by the app so long runs never sit in a web request.
This first version only confirms it can reach its own API key; research
itself comes in a later step.
"""
import os

import boto3

_ssm = boto3.client("ssm")


def _api_key_configured():
    try:
        value = _ssm.get_parameter(
            Name=os.environ["CASEBOOK_API_KEY_SSM_PARAM"], WithDecryption=True
        )["Parameter"]["Value"]
    except _ssm.exceptions.ParameterNotFound:
        return False
    return bool(value.strip())


def handler(event, context):
    if (event or {}).get("action") == "check":
        return {"key_configured": _api_key_configured()}
    return {"error": "unknown action"}
