"""Secrets out of trace text: keys, tokens, private keys, passwords, bearer headers, .env
values, credentialed URLs, emails, hosts and IP addresses, each replaced by a bracketed tag.

    from scrub import scrub; scrub("export OPENAI_API_KEY=sk-...")  # 'export OPENAI_API_KEY=[SECRET]'

Rules run in order; an earlier rule's tag is never matched by a later one. Over-scrubbing is
the safe side: a git sha or a version string may be tagged too.
"""
import re

TAG = r"\[(?:SECRET|KEY|EMAIL|IP|HOST|URL)\]"

RULES = [
    # PEM private keys, whole block.
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|$)", re.S), "[KEY]"),
    # Credentials inside URLs: scheme://user:pass@host.
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@"), r"\1[SECRET]@"),
    # Authorization headers and bearer/basic tokens.
    (re.compile(r"(?i)\b(authorization\s*[:=]\s*)(?:bearer|basic|token)?\s*[^\s\"',]+"), r"\1[SECRET]"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 [SECRET]"),
    # Vendor key shapes.
    (re.compile(r"\bsk-(?:ant-|proj-|or-)?[A-Za-z0-9_-]{16,}"), "[SECRET]"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "[SECRET]"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[SECRET]"),
    (re.compile(r"\bhf_[A-Za-z0-9]{20,}"), "[SECRET]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "[SECRET]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}"), "[SECRET]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[SECRET]"),
    # name = value where the name says secret.
    (re.compile(r"(?i)((?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key|credentials?)[\"']?\s*[:=]\s*[\"']?)(?!" + TAG + r")[^\s\"',;]{3,}"), r"\1[SECRET]"),
    # .env lines: an upper-case name assigned a value.
    (re.compile(r"(?m)^(\s*(?:export\s+)?[A-Z][A-Z0-9_]{2,}=)(?!" + TAG + r")[\"']?[^\s\"']+[\"']?"), r"\1[SECRET]"),
    # Emails, then hosts and addresses.
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"), "[IP]"),
    (re.compile(r"(?i)\b(?:[0-9a-f]{1,4}:){4,7}[0-9a-f]{1,4}\b"), "[IP]"),
    (re.compile(r"(?i)\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:local|internal|lan|svc|cluster\.local|ts\.net)\b"), "[HOST]"),
    # Long mixed-case alphanumeric runs: unlabelled tokens.
    (re.compile(r"\b(?=[A-Za-z0-9+/_-]*[a-z])(?=[A-Za-z0-9+/_-]*[A-Z])(?=[A-Za-z0-9+/_-]*[0-9])[A-Za-z0-9+/_-]{32,}"), "[SECRET]"),
]


def scrub(text):
    if not isinstance(text, str):
        return text
    for rule, tag in RULES:
        text = rule.sub(tag, text)
    return text


def deep(v):
    """scrub over every string leaf of a JSON value."""
    if isinstance(v, str):
        return scrub(v)
    if isinstance(v, list):
        return [deep(x) for x in v]
    if isinstance(v, dict):
        return {k: deep(x) for k, x in v.items()}
    return v
