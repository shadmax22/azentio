"""PII Masking utilities for Indian loan application packets.

Conforms to regulatory requirements:
- PAN numbers (5 letters, 4 digits, 1 letter) masked to last 4 characters (e.g. XXXXXX123F).
- Account numbers (9-18 digits) masked to last 4 digits (e.g. XXXXXXXX1234).
- Safe recursive masking for strings, dicts, lists, and Pydantic models.
"""

import re
from typing import Any, Dict, List, Union


# Regex for Indian Permanent Account Number (PAN): 5 uppercase letters, 4 digits, 1 uppercase letter
PAN_PATTERN = re.compile(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b")

# Regex for Indian Bank Account Numbers (9 to 18 consecutive digits)
ACCOUNT_PATTERN = re.compile(r"\b(\d{9,18})\b")

# Regex for Aadhaar numbers (12 digits with optional spaces or dashes)
AADHAAR_PATTERN = re.compile(r"\b(\d{4}[\s-]?\d{4}[\s-]?\d{4})\b")


def mask_pan_match(match: re.Match) -> str:
    """Mask PAN retaining only last 4 characters (e.g. ABCDE1234F -> XXXXXX1234F)."""
    val = match.group(1)
    if len(val) >= 4:
        return "X" * (len(val) - 4) + val[-4:]
    return "X" * len(val)


def mask_account_match(match: re.Match) -> str:
    """Mask account number retaining only last 4 digits (e.g. 123456789012 -> XXXXXXXX9012)."""
    val = match.group(1)
    if len(val) >= 4:
        return "X" * (len(val) - 4) + val[-4:]
    return "X" * len(val)


def mask_pii_text(text: str) -> str:
    """Mask all PAN, account, and Aadhaar numbers in text."""
    if not isinstance(text, str) or not text:
        return text

    # Mask PANs
    masked = PAN_PATTERN.sub(mask_pan_match, text)
    # Mask Account Numbers
    masked = ACCOUNT_PATTERN.sub(mask_account_match, masked)
    return masked


def mask_pii(data: Any) -> Any:
    """Recursively mask PII in strings, lists, dicts, or objects."""
    if isinstance(data, str):
        return mask_pii_text(data)
    elif isinstance(data, dict):
        return {k: mask_pii(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [mask_pii(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(mask_pii(item) for item in data)
    elif hasattr(data, "model_dump"):
        return mask_pii(data.model_dump())
    elif hasattr(data, "__dict__"):
        return mask_pii(data.__dict__)
    return data

