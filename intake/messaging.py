"""Borrower Messaging & Validation for Loan Application Packets.

Produces clear, empathetic customer messages requesting missing or defective documents,
with strict validation against checklist borrower_labels and a deterministic fallback template.
"""

from typing import Any, Dict, List, Optional
from intake.checklist import load_checklist


REASON_DESCRIPTIONS = {
    "MISSING": "This document was not found in your application packet. Please upload a clear, legible copy.",
    "EXPIRED": "The document submitted has expired. Please provide a currently valid, active document.",
    "STALE": "The document submitted is older than the permissible 90-day validity window. Please provide a recent document.",
    "INCOMPLETE_COVERAGE": "The document provided does not cover the required full period. Please submit statements covering the entire missing window.",
}


def build_template_message(
    document_requests: List[Any],
    applicant_name: str = "Valued Customer",
    language: str = "en"
) -> str:
    """Generate deterministic template borrower message containing exact borrower labels."""
    checklist = load_checklist()
    lines = [
        f"Dear {applicant_name or 'Valued Customer'},",
        "",
        "Thank you for submitting your retail loan application. During our initial verification, our credit-operations team identified that additional documentation is required to complete your underwriting assessment:",
        ""
    ]

    for req in document_requests:
        req_id = req.requirement_id if hasattr(req, "requirement_id") else req.get("requirement_id", "")
        reason_code = req.reason_code if hasattr(req, "reason_code") else req.get("reason_code", "MISSING")

        label = checklist.requirements.get(req_id, {}).borrower_label if req_id in checklist.requirements else req_id
        reason_desc = REASON_DESCRIPTIONS.get(reason_code, "Please provide an updated document.")

        lines.append(f"• {label}")
        lines.append(f"  Reason: {reason_desc}")

    lines.extend([
        "",
        "Please upload the requested documents through your online portal within 7 business days to proceed with loan sanctioning.",
        "",
        "Warm regards,",
        "Retail Credit Operations Team",
        "Azentio Bank"
    ])

    return "\n".join(lines)


def validate_borrower_message(
    message: str,
    requested_requirement_ids: List[str]
) -> bool:
    """Validate message against checklist borrower_labels.
    
    Rules (from PDF Page 4):
    1. Every requested requirement's label MUST appear in the message.
    2. NO label of an unrequested requirement may appear in the message.
    """
    if not message or not isinstance(message, str):
        return False

    checklist = load_checklist()
    req_set = set(requested_requirement_ids)

    # Rule 1: Every requested requirement's label must appear
    for req_id in req_set:
        req_cfg = checklist.requirements.get(req_id)
        if not req_cfg:
            continue
        label = req_cfg.borrower_label
        if label not in message:
            return False

    # Rule 2: No label of an unrequested requirement may appear
    for req_id, req_cfg in checklist.requirements.items():
        if req_id not in req_set:
            label = req_cfg.borrower_label
            if label in message:
                return False

    return True


def draft_borrower_request(
    document_requests: List[Any],
    applicant_name: str = "Valued Customer",
    language: str = "en",
    candidate_draft: Optional[str] = None
) -> str:
    """Produce validated borrower request message with template fallback."""
    if not document_requests:
        return ""

    req_ids = [
        r.requirement_id if hasattr(r, "requirement_id") else r.get("requirement_id", "")
        for r in document_requests
    ]

    # If candidate draft is provided, validate it
    if candidate_draft:
        if validate_borrower_message(candidate_draft, req_ids):
            return candidate_draft

    # Otherwise fall back to deterministic template
    return build_template_message(document_requests, applicant_name, language)

