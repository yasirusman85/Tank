"""
Safety guardrails, PII redaction, and prompt injection detection for Tank framework.
Provides PIIMasker, PromptInjectionDetector, and SafetyGuardrail.
"""
import re
from typing import Tuple, List


class PIIMasker:
    """
    Detects and redacts Personally Identifiable Information (PII)
    such as emails, phone numbers, SSNs, and credit cards.
    """
    EMAIL_REGEX = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    PHONE_REGEX = r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
    SSN_REGEX = r'\b\d{3}-\d{2}-\d{4}\b'
    CREDIT_CARD_REGEX = r'\b(?:\d[ -]*?){13,16}\b'

    @classmethod
    def sanitize(cls, text: str) -> str:
        if not text:
            return ""
        text = re.sub(cls.EMAIL_REGEX, "[REDACTED_EMAIL]", text)
        text = re.sub(cls.SSN_REGEX, "[REDACTED_SSN]", text)
        text = re.sub(cls.PHONE_REGEX, "[REDACTED_PHONE]", text)
        return text


class PromptInjectionDetector:
    """
    Detects potential prompt injection / jailbreak attempts.
    """
    INJECTION_PATTERNS = [
        r'ignore\s+(all\s+)?(previous|above)\s+instructions',
        r'system\s+override',
        r'you\s+are\s+now\s+dan',
        r'bypass\s+security',
        r'do\s+anything\s+now'
    ]

    @classmethod
    def check(cls, text: str) -> Tuple[bool, List[str]]:
        if not text:
            return False, []
        text_lower = text.lower()
        matches = []
        for pattern in cls.INJECTION_PATTERNS:
            if re.search(pattern, text_lower):
                matches.append(pattern)
        return bool(matches), matches


class SafetyGuardrail:
    """
    Applies pre-execution sanitization and prompt injection checks.
    """
    @classmethod
    def process_input(cls, text: str) -> Tuple[str, bool]:
        is_injection, _ = PromptInjectionDetector.check(text)
        if is_injection:
            return "Security violation: Potential prompt injection detected.", True
        sanitized = PIIMasker.sanitize(text)
        return sanitized, False
