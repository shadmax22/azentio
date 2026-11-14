"""Tool to classify document text into banking document types."""

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class SingleClassification(BaseModel):
    """Classification for a single document."""
    doc_id: str
    doc_type: str = Field(..., description="ID_PROOF, ADDRESS_PROOF, SALARY_SLIP, BANK_STATEMENT, ITR, BUSINESS_PROOF, PROPERTY_DOC, UNREADABLE, or UNKNOWN")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    matched_keywords: List[str] = Field(default_factory=list)


class ClassifyDocumentInput(BaseModel):
    """Input arguments for classify_document."""
    doc_id: Optional[str] = None
    text: Optional[str] = None
    filename: Optional[str] = None
    documents: Optional[List[Dict[str, Any]]] = None
    packet: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_inputs(self) -> "ClassifyDocumentInput":
        if not self.packet and not self.documents:
            if not self.doc_id or self.text is None:
                raise ValueError("classify_document requires either ('doc_id' and 'text'), or 'documents'/'packet'")
        return self


class ClassifyDocumentOutput(BaseModel):
    """Classification result for a document or batch of documents."""
    doc_id: Optional[str] = None
    doc_type: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    matched_keywords: List[str] = Field(default_factory=list)
    classifications: List[SingleClassification] = Field(default_factory=list)


UNREADABLE_PATTERNS = [
    r"error\s+code\s+0x[0-9a-f]+",
    r"optical\s+ocr\s+recognition\s+failed",
    r"low\s+scan\s+resolution",
    r"cannot\s+decipher\s+characters",
    r"image\s+corruption\s+detected",
    r"excessive\s+glare\s+detected",
    r"photocopy\s+blacked\s+out",
    r"illegible\s+handwritten\s+smudge",
    r"cannot\s+determine\s+whether\s+document",
    r"[#%@$^~?|\[\]]{6,}",
]

DOCUMENT_KEYWORD_RULES = {
    "ID_PROOF": [
        "PASSPORT", "VOTER ID", "VOTER", "DRIVING LICENCE", "DRIVING LICENSE",
        "NATIONAL ID", "NATIONAL_ID", "PERMANENT ACCOUNT NUMBER", "PAN CARD",
        "OFFICIAL IDENTIFICATION DOCUMENT", "REPUBLIC OF INDIA - PASSPORT",
    ],
    "ADDRESS_PROOF": [
        "UTILITY SERVICE", "CONSUMPTION INVOICE", "ELECTRICITY", "WATER BILL",
        "PIPED GAS", "RENT AGREEMENT", "CONSUMER BILL", "TATA POWER", "BESCOM",
        "MSEDCL", "ADANI ELECTRICITY", "INDRAPRASTHA GAS", "UTILITY",
    ],
    "SALARY_SLIP": [
        "SALARY STATEMENT", "PAYSLIP", "PAY PERIOD", "BASIC SALARY",
        "HOUSE RENT ALLOWANCE", "NET DISBURSED", "EMPLOYEE SALARY",
        "PAY VOUCHER", "SALARY VOUCHER", "NET SALARY",
    ],
    "BANK_STATEMENT": [
        "ACCOUNT TRANSACTION REPORT", "ACCOUNT STATEMENT", "SAVINGS ACCOUNT",
        "STATEMENT COVERAGE WINDOW", "OPENING BALANCE", "CLOSING BALANCE",
        "TOTAL CREDITS", "TOTAL DEBITS", "CORE BANKING DATABASE", "PASSBOOK",
    ],
    "ITR": [
        "INCOME TAX RETURN", "ITR-V", "ITR-3", "ITR-4", "ASSESSMENT YEAR",
        "E-FILING ACKNOWLEDGEMENT", "INCOME TAX DEPARTMENT",
    ],
    "BUSINESS_PROOF": [
        "GOODS AND SERVICES TAX", "FORM GST REG-06", "REGISTRATION NUMBER (GSTIN)",
        "CERTIFICATE OF REGISTRATION", "TRADE NAME", "CONSTITUTION OF BUSINESS",
        "SOLE PROPRIETORSHIP", "GST CERTIFICATE",
    ],
    "PROPERTY_DOC": [
        "DEED OF SALE", "TITLE CONVEYANCE", "SUB-REGISTRAR OFFICE",
        "REGISTRATION AND STAMP DEPARTMENT", "SALE CONSIDERATION",
        "TITLE STATUS", "PROPERTY DESCRIPTION", "TITLE DEED", "SALE AGREEMENT",
    ],
}


def _classify_single(doc_id: str, text: str) -> SingleClassification:
    """Classify a single document text."""
    text_upper = text.upper() if text else ""

    # Check for unreadable / corrupted scan patterns
    for pat in UNREADABLE_PATTERNS:
        if re.search(pat, text_upper, re.IGNORECASE):
            return SingleClassification(
                doc_id=doc_id,
                doc_type="UNREADABLE",
                confidence=0.95,
                matched_keywords=["CORRUPT_OR_UNREADABLE_PATTERN"]
            )

    # Score candidate categories by keyword matches
    scores = {}
    matches_by_type = {}
    for doc_type, keywords in DOCUMENT_KEYWORD_RULES.items():
        matched = [kw for kw in keywords if kw in text_upper]
        if matched:
            scores[doc_type] = len(matched)
            matches_by_type[doc_type] = matched

    if not scores:
        return SingleClassification(
            doc_id=doc_id,
            doc_type="UNKNOWN",
            confidence=0.10,
            matched_keywords=[]
        )

    best_type = max(scores, key=lambda k: scores[k])
    match_count = scores[best_type]
    matched_kws = matches_by_type[best_type]

    if match_count >= 3:
        confidence = 0.98
    elif match_count == 2:
        confidence = 0.92
    else:
        confidence = 0.82

    return SingleClassification(
        doc_id=doc_id,
        doc_type=best_type,
        confidence=confidence,
        matched_keywords=matched_kws
    )


def classify_document(args: ClassifyDocumentInput) -> ClassifyDocumentOutput:
    """Classify document type using keyword signals and corruption heuristics."""
    docs_to_classify = []
    if args.packet:
        docs_to_classify = args.packet.get("documents", [])
    elif args.documents:
        docs_to_classify = args.documents
    elif args.doc_id is not None and args.text is not None:
        docs_to_classify = [{"doc_id": args.doc_id, "text": args.text}]
    else:
        # Invalid call: missing required fields
        raise ValueError("classify_document requires either ('doc_id' and 'text'), or 'documents' list")

    results = []
    for d in docs_to_classify:
        did = d.get("doc_id", "unknown")
        txt = d.get("text", "")
        results.append(_classify_single(did, txt))

    if len(results) == 1 and args.doc_id is not None:
        first = results[0]
        return ClassifyDocumentOutput(
            doc_id=first.doc_id,
            doc_type=first.doc_type,
            confidence=first.confidence,
            matched_keywords=first.matched_keywords,
            classifications=results
        )

    return ClassifyDocumentOutput(
        doc_id="batch",
        doc_type="BATCH",
        confidence=min((r.confidence for r in results), default=1.0),
        classifications=results
    )
