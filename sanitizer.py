"""Secret sanitizing: masks tokens, passwords, emails etc. in merged output.

Pure Python, no Qt dependency — runs inside the merge worker thread and is
trivially unit-testable. Detection rules follow the well-known gitleaks /
detect-secrets pattern sets; unlike those tools (which only *detect*), this
module *redacts*: the secret value is replaced with a placeholder while the
surrounding structure (key names, quotes, URLs) is preserved, e.g.::

    API_KEY = "sk-abc..."        ->  API_KEY = "***REDACTED***"
    postgres://bob:hunter2@db/x  ->  postgres://***:***@db/x
    admin@example.org            ->  ***EMAIL***

No automated scanner gives a 100% guarantee — the UI must surface this to the
user (see ``i18n: sanitize_disclaimer``).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

MASK = "***REDACTED***"
EMAIL_MASK = "***EMAIL***"


@dataclass(frozen=True)
class Finding:
    """One masked secret (the secret itself is intentionally NOT stored)."""

    rule: str       # human-readable rule name
    line: int       # 1-based line number in the original text


# Values that are clearly placeholders/examples — never masked.
_PLACEHOLDER_RE = re.compile(
    r"(?i)(?:^(?:x+|\*+|\.+|-+|_+)$"
    r"|example|sample|dummy|placeholder|changeme|change_me|your[_-]?|"
    r"<[^>]*>|\$\{[^}]*\}|%\(?[a-z_]+\)?s?|todo|fixme|^none$|^null$|^true$|^false$|undefined|secret_here|password_here)"
)

# Values that look like code expressions rather than literals.
_CODE_EXPR_RE = re.compile(r"[(){}\[\]]|^\$|^@|->|=>|\bos\.|\bgetenv\b|\benviron\b|\binput\b|\bconfig\b\.")


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    freq: dict[str, int] = {}
    for ch in value:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _is_plausible_secret(value: str) -> bool:
    """Heuristic for the *generic* key=value rule (specific rules skip this)."""
    if len(value) < 6:
        return False
    if _PLACEHOLDER_RE.search(value) or _CODE_EXPR_RE.search(value):
        return False
    # Long mixed strings or anything with decent entropy; short dictionary-like
    # words ("password = admin") still count — better safe in a public doc.
    if len(value) >= 16:
        return _shannon_entropy(value) >= 3.0
    return True


_KEY_WORDS = (
    r"password|passwd|pwd|passphrase|secret|token|api[_-]?key|apikey|"
    r"access[_-]?key|secret[_-]?key|auth[_-]?token|client[_-]?secret|"
    r"private[_-]?key|credentials?|connection[_-]?string|login"
)

# Order matters: multiline blocks first, then specific token formats,
# then structural rules (URL creds, assignments, headers), then e-mails.
_RULES: list[tuple[str, re.Pattern[str], object]] = [
    (
        "Приватный ключ / private key block",
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY( BLOCK)?-----.*?-----END [A-Z0-9 ]*PRIVATE KEY( BLOCK)?-----",
            re.DOTALL,
        ),
        f"-----BEGIN PRIVATE KEY-----\n{MASK}\n-----END PRIVATE KEY-----",
    ),
    ("AWS Access Key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), MASK),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"), MASK),
    ("Slack token", re.compile(r"\bxox[abprse]-[A-Za-z0-9-]{10,}\b"), MASK),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}\b"), MASK),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), MASK),
    ("Stripe key", re.compile(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{20,}\b"), MASK),
    ("Telegram bot token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), MASK),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), MASK),
    (
        "Логин/пароль в URL / credentials in URL",
        re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)(?!\*{3}:)[^/\s:@'\"]+:[^/\s@'\"]+@"),
        lambda m: f"{m.group('scheme')}***:***@",
    ),
    (
        "Bearer-токен / bearer token",
        re.compile(r"(?i)(?P<prefix>\bbearer\s+)(?!\*{3})[A-Za-z0-9._~+/=-]{16,}"),
        lambda m: f"{m.group('prefix')}{MASK}",
    ),
]

# Generic ``key = "value"`` assignments — applied with the plausibility check.
_GENERIC_RE = re.compile(
    rf"(?im)(?P<key>\b(?:{_KEY_WORDS})\b)"
    r"(?P<sep>\s*(?:[:=]|=>|:=)\s*)"
    r"(?P<q>[\"']?)(?P<value>[^\"'\r\n]{4,}?)(?P=q)(?P<tail>\s*[,;]?\s*)$"
)

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_GENERIC_RULE_NAME = "Пароль/секрет в присваивании / secret assignment"
_EMAIL_RULE_NAME = "E-mail адрес / e-mail address"


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def sanitize_text(text: str) -> tuple[str, list[Finding]]:
    """Mask secrets in *text*; returns ``(clean_text, findings)``.

    Findings carry only the rule name and line number — never the secret.
    Running the function on its own output yields no new findings
    (idempotent), so re-merging a sanitized document is safe.
    """
    findings: list[Finding] = []

    def apply(pattern: re.Pattern[str], repl: object, rule: str, guard=None) -> None:
        nonlocal text

        def _sub(m: re.Match[str]) -> str:
            if guard is not None and not guard(m):
                return m.group(0)
            findings.append(Finding(rule=rule, line=_line_of(text, m.start())))
            return repl(m) if callable(repl) else repl  # type: ignore[operator]

        text = pattern.sub(_sub, text)

    for rule_name, pattern, repl in _RULES:
        apply(pattern, repl, rule_name)

    def _generic_repl(m: re.Match[str]) -> str:
        return f"{m.group('key')}{m.group('sep')}{m.group('q')}{MASK}{m.group('q')}{m.group('tail')}"

    def _generic_guard(m: re.Match[str]) -> bool:
        value = m.group("value")
        return MASK not in value and _is_plausible_secret(value)

    apply(_GENERIC_RE, _generic_repl, _GENERIC_RULE_NAME, guard=_generic_guard)

    def _email_guard(m: re.Match[str]) -> bool:
        value = m.group(0)
        return not _PLACEHOLDER_RE.search(value) and EMAIL_MASK not in value

    apply(_EMAIL_RE, EMAIL_MASK, _EMAIL_RULE_NAME, guard=_email_guard)

    return text, findings
