"""Pydantic schemas for loan application packets and ground-truth labels."""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------
# Raw Packet Schemas (Saved in data/packets/<packet_id>.json)
# Contains ZERO label/ground-truth leakage
# ---------------------------------------------------------

class RawDocument(BaseModel):
    """Raw document representation containing simulated OCR dump."""
    doc_id: str = Field(..., description="Document identifier, e.g. doc_01")
    filename: str = Field(..., description="Filename, e.g. scan_0042.txt or salary_feb.txt")
    text: str = Field(..., description="Simulated raw OCR / text dump with noise")


class Packet(BaseModel):
    """Loan application packet containing free text application and raw documents."""
    packet_id: str = Field(..., description="Unique packet identifier, e.g. pkt_001")
    as_of: str = Field(..., description="Fixed baseline date (YYYY-MM-DD), e.g. 2026-03-15")
    application_form: str = Field(..., description="Free text application form content")
    documents: List[RawDocument] = Field(..., description="List of raw text documents")


# ---------------------------------------------------------
# Ground Truth Label Schemas (Saved in data/labels.jsonl)
# ---------------------------------------------------------

RequirementId = Literal[
    "ID_PROOF",
    "ADDRESS_PROOF",
    "SALARY_SLIPS_3M",
    "BANK_STMT_6M",
    "ITR_2Y",
    "BANK_STMT_12M",
    "BUSINESS_PROOF",
    "PROPERTY_DOC",
]

ReasonCode = Literal[
    "MISSING",
    "INCOMPLETE_COVERAGE",
    "STALE",
    "EXPIRED",
]

DecisionType = Literal[
    "COMPLETE",
    "REQUEST_DOCUMENTS",
    "HUMAN_REVIEW",
]


class ExpectedRequest(BaseModel):
    """Specific missing or deficient requirement with reason code."""
    requirement_id: RequirementId
    reason_code: ReasonCode


class FormFields(BaseModel):
    """Normalized true values for the application form."""
    applicant_name: Optional[str] = None
    product: Optional[Literal["personal_loan", "home_loan"]] = None
    employment_type: Optional[Literal["salaried", "self_employed"]] = None
    loan_amount: Optional[int] = None
    tenure_months: Optional[int] = None
    application_date: Optional[str] = None


class DocumentLabel(BaseModel):
    """Ground truth classification and extracted periods for a single document."""
    doc_id: str
    doc_type: str = Field(..., description="ID_PROOF, ADDRESS_PROOF, SALARY_SLIP, BANK_STATEMENT, ITR, BUSINESS_PROOF, PROPERTY_DOC, UNREADABLE")
    pay_month: Optional[str] = None        # YYYY-MM
    period_start: Optional[str] = None     # YYYY-MM-DD
    period_end: Optional[str] = None       # YYYY-MM-DD
    assessment_year: Optional[str] = None  # e.g. 2025-26
    issue_date: Optional[str] = None       # YYYY-MM-DD
    expiry_date: Optional[str] = None      # YYYY-MM-DD


class PacketLabel(BaseModel):
    """Complete ground truth record for one packet in labels.jsonl."""
    packet_id: str
    expected_decision: DecisionType
    expected_requests: List[ExpectedRequest] = Field(default_factory=list)
    form_fields: FormFields
    documents: List[DocumentLabel]

