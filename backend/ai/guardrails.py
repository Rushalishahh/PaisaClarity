"""Security guardrails, prompt injection detection, and financial disclaimers."""

import re
from typing import Optional, Tuple

DISCLAIMER_TEXT = (
    "Disclaimer: PaisaClarity Copilot provides informational insights based on your "
    "recorded transactions and accounts. It does not provide certified financial advice, "
    "investment recommendations, or legal tax counsel."
)

# Common injection and jailbreak patterns
INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?(previous|above|prior)\s+instructions?",
    r"(?i)disregard\s+(all\s+)?(previous|above|system)\s+rules?",
    r"(?i)you\s+are\s+now\s+(in\s+)?(dan|developer|god)\s+mode",
    r"(?i)system\s*prompt\s*override",
    r"(?i)show\s+(me\s+)?(all\s+)?users?\s+in\s+the\s+database",
    r"(?i)dump\s+(the\s+)?database",
    r"(?i)drop\s+table",
    r"(?i)select\s+\*\s+from\s+users",
    r"(?i)bypass\s+user(_|\s*)id",
    r"(?i)delete\s+all\s+(data|transactions|accounts)",
]

_COMPILED_INJECTION_PATTERNS = [re.compile(p) for p in INJECTION_PATTERNS]


def check_prompt_safety(prompt: str) -> Tuple[bool, Optional[str]]:
    """Inspect user prompt for injection, jailbreak attempts, or unauthorized commands.
    
    Returns (is_safe: bool, reason_or_warning: Optional[str]).
    """
    if not prompt or not prompt.strip():
        return False, "Prompt is empty."

    # Max prompt length check (e.g. 2000 chars)
    if len(prompt) > 2500:
        return False, "Prompt exceeds maximum allowed length of 2500 characters."

    for pattern in _COMPILED_INJECTION_PATTERNS:
        if pattern.search(prompt):
            return False, (
                "I cannot process this request. It appears to contain prompt injection "
                "or instructions to override security policies."
            )

    return True, None


def attach_disclaimer(content: str) -> str:
    """Ensure the standard informational financial disclaimer is appended if appropriate."""
    if not content:
        return DISCLAIMER_TEXT
    if DISCLAIMER_TEXT in content:
        return content
    return f"{content.strip()}\n\n---\n*{DISCLAIMER_TEXT}*"

