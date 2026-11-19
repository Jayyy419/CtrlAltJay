"""Checks a code excerpt for anything that looks like a secret before it can
be published on a Source Map tour.

It reports the line and the kind of thing found, never the value itself, so
a finding can be shown and logged without repeating the secret.
"""
import math
import re

# (kind, pattern). Ordered so the most specific name wins on a line.
PATTERNS = [
    ("Private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("Slack webhook", re.compile(r"hooks\.slack\.com/services/[A-Za-z0-9/]+")),
    ("Stripe key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Anthropic or OpenAI key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{20,}")),
    ("JSON web token", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("Link with a password", re.compile(r"[a-z][a-z0-9+.\-]*://[^\s/:@'\"]+:[^\s/@'\"]+@", re.I)),
    ("Password or secret in the code", re.compile(
        r"(?i)\b[\w.\-]*(?:password|passwd|pwd|secret|token|api[_\-]?key|access[_\-]?key|private[_\-]?key|client[_\-]?secret|auth)[\w.\-]*"
        r"\s*[:=]\s*(?:[rbuf]?['\"])([^'\"\s]{6,})['\"]")),
    (".env line", re.compile(r"^\s*(?:export\s+)?[A-Z][A-Z0-9_]{2,}\s*=\s*['\"]?[^\s'\"#]{6,}")),
    ("Private address", re.compile(
        r"(?i)(?:\blocalhost(?::\d+)?\b|\b127\.0\.0\.1\b|\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|\b192\.168\.\d{1,3}\.\d{1,3}\b"
        r"|\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b|\b[\w\-]+(?:\.[\w\-]+)*\.(?:internal|local|corp|lan|intranet)\b)")),
    ("Email address", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
]

# Values in .env-style lines that are plainly not secrets.
ENV_HARMLESS = re.compile(r"^(?:true|false|none|null|yes|no|\d+(?:\.\d+)?|https?://(?:www\.)?example\.(?:com|org)\S*)$", re.I)
PLACEHOLDER = re.compile(r"(?i)(?:x{4,}|\*{4,}|changeme|your[_\-]|example|placeholder|dummy|<[^>]+>|\$\{|\{\{|os\.environ|getenv|process\.env)")
EMAIL_HARMLESS = re.compile(r"(?i)@(?:example\.(?:com|org|net)|users\.noreply\.github\.com)$")
TOKEN = re.compile(r"[A-Za-z0-9+/=_\-]{24,}")


def _entropy(text):
    counts = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum(n / len(text) * math.log2(n / len(text)) for n in counts.values())


def _random_looking(token):
    # Long runs of mixed characters with high entropy, the shape most keys
    # have. Plain words, paths and repeated characters score low.
    if len(token) < 24 or token.isalpha() or token.isdigit():
        return False
    kinds = sum(bool(re.search(p, token)) for p in (r"[a-z]", r"[A-Z]", r"\d"))
    if kinds < 2:
        return False
    hexish = re.fullmatch(r"[0-9a-fA-F]+", token) is not None
    return _entropy(token) >= (3.4 if hexish else 4.2)


def scan_lines(lines, start=1):
    """Return [{"line": n, "kind": str}] for every suspicious line."""
    findings = []
    for offset, line in enumerate(lines):
        number = start + offset
        found = None
        for kind, pattern in PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            text = match.group(0)
            if kind == "Email address" and EMAIL_HARMLESS.search(text):
                continue
            if kind in (".env line", "Password or secret in the code"):
                value = (match.group(1) if match.groups() else text.split("=", 1)[-1]).strip().strip("'\"")
                if PLACEHOLDER.search(line) or ENV_HARMLESS.match(value):
                    continue
            found = kind
            break
        if not found:
            for token in TOKEN.findall(line):
                if _random_looking(token) and not PLACEHOLDER.search(token):
                    found = "Random-looking string"
                    break
        if found:
            findings.append({"line": number, "kind": found})
    return findings
