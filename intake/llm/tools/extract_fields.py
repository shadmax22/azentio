"""Tool to extract normalized form and document fields with confidence metrics."""

import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class FieldResult(BaseModel):
    """Extracted field value with confidence and provenance."""
    value: Any
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_line: Optional[str] = None


class ExtractFieldsInput(BaseModel):
    """Input arguments for extract_fields tool."""
    text: str
    target: Literal["form", "document"]
    doc_type: Optional[str] = None
    doc_id: Optional[str] = None


class ExtractFieldsOutput(BaseModel):
    """Normalized extracted fields with confidence scores."""
    target: str
    fields: Dict[str, FieldResult] = Field(default_factory=dict)


# -------------------------------------------------------------------
# Normalization & Parsing Helpers
# -------------------------------------------------------------------

def _parse_flexible_date(date_str: str) -> Optional[str]:
    """Parse noisy date strings into ISO format YYYY-MM-DD."""
    if not date_str:
        return None
    cleaned = date_str.strip().rstrip(",.").strip()
    
    # Common format list
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d-%b-%y",      # 5-Mar-26
        "%d-%b-%Y",     # 15-Mar-2026
        "%d-%B-%Y",     # 15-March-2026
        "%B %d, %Y",    # March 15, 2026
        "%b %d, %Y",    # Mar 15, 2026
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
            
    # Try month name extraction if day is single digit
    match = re.match(r"^(\d{1,2})[-/ ]([A-Za-z]+)[-/ ](\d{2,4})$", cleaned)
    if match:
        day, mon, year = match.groups()
        if len(year) == 2:
            year = "20" + year
        for mfmt in ["%b", "%B"]:
            try:
                dt = datetime.strptime(f"{int(day):02d}-{mon}-{year}", f"%d-{mfmt}-%Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
    return None


def _parse_indian_currency(text: str) -> Optional[int]:
    """Parse noisy Indian currency representations into integer INR."""
    if not text:
        return None
    cleaned = text.strip()
    
    # Check for Lakh notation, e.g. "Rs. 7.5 Lakh", "5 Lakh"
    lakh_match = re.search(r"(\d+(?:\.\d+)?)\s*lakh", cleaned, re.IGNORECASE)
    if lakh_match:
        val = float(lakh_match.group(1))
        return int(val * 100000)

    # Strip prefixes like Rs., INR, /-, commas, spaces
    digits_only = re.sub(r"[^\d]", "", cleaned)
    if digits_only:
        try:
            return int(digits_only)
        except ValueError:
            return None
    return None


def _parse_pay_month(text: str) -> Optional[str]:
    """Parse pay period into YYYY-MM format."""
    if not text:
        return None
    cleaned = text.strip()
    
    # 1. Matches ISO YYYY-MM directly
    if re.match(r"^\d{4}-\d{2}$", cleaned):
        return cleaned

    # 2. Month Year e.g. "FEBRUARY 2026" or "Feb 2026"
    for mfmt in ["%B %Y", "%b %Y", "%B-%Y", "%b-%Y"]:
        try:
            dt = datetime.strptime(cleaned, mfmt)
            return dt.strftime("%Y-%m")
        except ValueError:
            continue
    return None


# -------------------------------------------------------------------
# Form Extraction Logic
# -------------------------------------------------------------------

def extract_form_fields(text: str) -> Dict[str, FieldResult]:
    """Extract fields from loan application form free text."""
    fields: Dict[str, FieldResult] = {}

    # 1. Applicant Name
    name_match = re.search(r"(?:Applicant Full Name|Applicant Name|Name)\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if name_match:
        line = name_match.group(0).strip()
        raw_name = name_match.group(1).strip()
        if "ILLEGIBLE" in raw_name.upper() or "MISSING" in raw_name.upper() or len(raw_name) < 2:
            fields["applicant_name"] = FieldResult(value=None, confidence=0.30, source_line=line)
        else:
            fields["applicant_name"] = FieldResult(value=raw_name, confidence=0.95, source_line=line)
    else:
        fields["applicant_name"] = FieldResult(value=None, confidence=0.0)

    # 2. Product
    prod_match = re.search(r"(?:Loan Product Applied For|Applied For|Product|Applied Product)\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if prod_match:
        line = prod_match.group(0).strip()
        raw_prod = prod_match.group(1).lower().strip()
        if "home" in raw_prod:
            fields["product"] = FieldResult(value="home_loan", confidence=0.98, source_line=line)
        elif "personal" in raw_prod:
            fields["product"] = FieldResult(value="personal_loan", confidence=0.98, source_line=line)
        else:
            fields["product"] = FieldResult(value=raw_prod, confidence=0.50, source_line=line)
    else:
        fields["product"] = FieldResult(value=None, confidence=0.0)

    # 3. Employment Type
    emp_match = re.search(r"(?:Employment Category|Employment Type|Employment)\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if emp_match:
        line = emp_match.group(0).strip()
        raw_emp = emp_match.group(1).lower().strip()
        if "salaried" in raw_emp:
            fields["employment_type"] = FieldResult(value="salaried", confidence=0.98, source_line=line)
        elif "self" in raw_emp or "business" in raw_emp:
            fields["employment_type"] = FieldResult(value="self_employed", confidence=0.98, source_line=line)
        else:
            fields["employment_type"] = FieldResult(value=raw_emp, confidence=0.50, source_line=line)
    else:
        fields["employment_type"] = FieldResult(value=None, confidence=0.0)

    # 4. Loan Amount (INR)
    amt_match = re.search(r"(?:Requested Loan Amount|Loan Amount|Amount)\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if amt_match:
        line = amt_match.group(0).strip()
        raw_amt_str = amt_match.group(1).strip()
        # Check for ambiguity indicators
        if any(w in raw_amt_str.lower() for w in ["between", "around", "maybe", "flexible", "unspecified", "decide"]):
            fields["loan_amount"] = FieldResult(value=None, confidence=0.30, source_line=line)
        else:
            parsed_amt = _parse_indian_currency(raw_amt_str)
            if parsed_amt is not None and parsed_amt > 0:
                fields["loan_amount"] = FieldResult(value=parsed_amt, confidence=0.95, source_line=line)
            else:
                fields["loan_amount"] = FieldResult(value=None, confidence=0.30, source_line=line)
    else:
        fields["loan_amount"] = FieldResult(value=None, confidence=0.0)

    # 5. Tenure Months
    tenure_match = re.search(r"(?:Repayment Tenure \(Months\)|Tenure|Repayment Tenure)\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if tenure_match:
        line = tenure_match.group(0).strip()
        raw_tenure_str = tenure_match.group(1).strip()
        digits = re.search(r"\d+", raw_tenure_str)
        if digits and not any(w in raw_tenure_str.lower() for w in ["flexible", "unspecified", "maybe"]):
            fields["tenure_months"] = FieldResult(value=int(digits.group(0)), confidence=0.95, source_line=line)
        else:
            fields["tenure_months"] = FieldResult(value=None, confidence=0.30, source_line=line)
    else:
        fields["tenure_months"] = FieldResult(value=None, confidence=0.0)

    # 6. Application Date
    date_match = re.search(r"(?:Application Date|Date of Application|Date)\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if date_match:
        line = date_match.group(0).strip()
        raw_d_str = date_match.group(1).strip()
        parsed_d = _parse_flexible_date(raw_d_str)
        if parsed_d:
            fields["application_date"] = FieldResult(value=parsed_d, confidence=0.95, source_line=line)
        else:
            fields["application_date"] = FieldResult(value=None, confidence=0.40, source_line=line)
    else:
        fields["application_date"] = FieldResult(value=None, confidence=0.0)

    return fields


# -------------------------------------------------------------------
# Document Extraction Logic
# -------------------------------------------------------------------

def extract_document_fields(text: str, doc_type: Optional[str]) -> Dict[str, FieldResult]:
    """Extract dates and period fields from document text."""
    fields: Dict[str, FieldResult] = {}

    # 1. Expiry Date (ID Proof)
    exp_match = re.search(r"(?:Expiry Date|Date of Expiry|Valid Till|Expiry)\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if exp_match:
        line = exp_match.group(0).strip()
        parsed = _parse_flexible_date(exp_match.group(1).strip())
        if parsed:
            fields["expiry_date"] = FieldResult(value=parsed, confidence=0.95, source_line=line)
        else:
            fields["expiry_date"] = FieldResult(value=None, confidence=0.40, source_line=line)

    # 2. Issue Date (Address Proof, Utility Bill)
    issue_match = re.search(r"(?:Bill Issue Date|Bill Date|Date of Issue|Issue Date)\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if issue_match:
        line = issue_match.group(0).strip()
        parsed = _parse_flexible_date(issue_match.group(1).strip())
        if parsed:
            fields["issue_date"] = FieldResult(value=parsed, confidence=0.95, source_line=line)
        else:
            fields["issue_date"] = FieldResult(value=None, confidence=0.40, source_line=line)

    # 3. Pay Month (Salary Slip)
    pay_match = re.search(r"(?:Pay Period|Period|SALARY FOR MONTH|MONTH)\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if pay_match:
        line = pay_match.group(0).strip()
        parsed = _parse_pay_month(pay_match.group(1).strip())
        if parsed:
            fields["pay_month"] = FieldResult(value=parsed, confidence=0.95, source_line=line)
        else:
            fields["pay_month"] = FieldResult(value=None, confidence=0.40, source_line=line)

    # 4. Period Start / Period End (Bank Statement)
    stmt_match = re.search(r"(?:Statement Coverage Window|Statement Period|Statement From)\s*:\s*([^\n]+)\s+(?:to|To)\s+([^\n]+)", text, re.IGNORECASE)
    if stmt_match:
        line = stmt_match.group(0).strip()
        start_raw = stmt_match.group(1).strip()
        end_raw = stmt_match.group(2).strip()
        p_start = _parse_flexible_date(start_raw)
        p_end = _parse_flexible_date(end_raw)
        if p_start and p_end:
            fields["period_start"] = FieldResult(value=p_start, confidence=0.95, source_line=line)
            fields["period_end"] = FieldResult(value=p_end, confidence=0.95, source_line=line)
        else:
            fields["period_start"] = FieldResult(value=p_start, confidence=0.50, source_line=line)
            fields["period_end"] = FieldResult(value=p_end, confidence=0.50, source_line=line)

    # 5. Assessment Year (ITR)
    ay_match = re.search(r"Assessment Year\s*:\s*(\d{4}-\d{2,4})", text, re.IGNORECASE)
    if ay_match:
        line = ay_match.group(0).strip()
        fields["assessment_year"] = FieldResult(value=ay_match.group(1).strip(), confidence=0.98, source_line=line)

    return fields


def extract_fields(args: ExtractFieldsInput) -> ExtractFieldsOutput:
    """Execute field extraction based on target ('form' or 'document')."""
    if args.target == "form":
        extracted = extract_form_fields(args.text)
    else:
        extracted = extract_document_fields(args.text, args.doc_type)

    return ExtractFieldsOutput(
        target=args.target,
        fields=extracted
    )

