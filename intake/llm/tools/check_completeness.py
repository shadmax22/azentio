"""Deterministic completeness and checklist verification tool."""

from datetime import datetime, date, timedelta
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from intake.llm.checklist import load_checklist, ChecklistConfig


# -------------------------------------------------------------------
# Input / Output Pydantic Schemas
# -------------------------------------------------------------------

class ExtractedDocument(BaseModel):
    """Extracted fields and metadata for a single document."""
    doc_id: str
    doc_type: str = Field(..., description="ID_PROOF, ADDRESS_PROOF, SALARY_SLIP, BANK_STATEMENT, ITR, BUSINESS_PROOF, PROPERTY_DOC, UNREADABLE")
    expiry_date: Optional[str] = None       # YYYY-MM-DD
    issue_date: Optional[str] = None        # YYYY-MM-DD
    pay_month: Optional[str] = None         # YYYY-MM
    period_start: Optional[str] = None      # YYYY-MM-DD
    period_end: Optional[str] = None        # YYYY-MM-DD
    assessment_year: Optional[str] = None   # e.g. 2025-26
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class CheckCompletenessInput(BaseModel):
    """Input arguments for check_completeness tool."""
    product: Literal["personal_loan", "home_loan"]
    employment_type: Literal["salaried", "self_employed"]
    as_of: str = Field(..., description="Fixed reference date (YYYY-MM-DD)")
    application_date: str = Field(..., description="Application date (YYYY-MM-DD)")
    documents: List[ExtractedDocument]


class RequirementEvaluation(BaseModel):
    """Result of checking a single requirement."""
    requirement_id: str
    status: Literal["SATISFIED", "MISSING", "INCOMPLETE_COVERAGE", "STALE", "EXPIRED", "UNREADABLE"]
    reason_code: Optional[Literal["MISSING", "INCOMPLETE_COVERAGE", "STALE", "EXPIRED"]] = None
    evidence_doc_ids: List[str] = Field(default_factory=list)
    borrower_label: str


class UnsatisfiedRequirement(BaseModel):
    """Deficient requirement specification for document request notifications."""
    requirement_id: str
    reason_code: str


class CheckCompletenessOutput(BaseModel):
    """JSON-serializable result of check_completeness."""
    all_satisfied: bool
    has_unreadable: bool
    requirements: Dict[str, RequirementEvaluation]
    unsatisfied: List[UnsatisfiedRequirement]


# -------------------------------------------------------------------
# Helper Date & Coverage Calculations
# -------------------------------------------------------------------

def _parse_date(d_str: Optional[str]) -> Optional[date]:
    if not d_str:
        return None
    try:
        return datetime.strptime(d_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _get_prior_calendar_months(app_date: date, count: int) -> List[str]:
    """Get the 'count' full calendar months prior to the application month (YYYY-MM)."""
    months = []
    # Start from 1st day of application month
    curr = app_date.replace(day=1)
    for _ in range(count):
        # Step back to the last day of the preceding month
        prev_month_last_day = curr - timedelta(days=1)
        months.append(prev_month_last_day.strftime("%Y-%m"))
        curr = prev_month_last_day.replace(day=1)
    return months


def _get_prior_coverage_window(app_date: date, months_count: int) -> tuple[date, date]:
    """Get start date and end date for 'months_count' full calendar months prior to application month."""
    # End date: last day of month prior to app_date
    first_of_app_month = app_date.replace(day=1)
    end_date = first_of_app_month - timedelta(days=1)
    
    # Start date: 1st day of (months_count - 1) months prior to end_date's month
    curr = end_date.replace(day=1)
    for _ in range(months_count - 1):
        prev = curr - timedelta(days=1)
        curr = prev.replace(day=1)
    start_date = curr
    return start_date, end_date


def _check_continuous_coverage(intervals: List[tuple[date, date]], required_start: date, required_end: date) -> bool:
    """Check if the union of intervals continuously covers [required_start, required_end]."""
    if not intervals:
        return False

    # Sort intervals by start date
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    
    # Merge overlapping or contiguous intervals
    merged: List[tuple[date, date]] = []
    for start, end in sorted_intervals:
        if not merged:
            merged.append((start, end))
        else:
            prev_start, prev_end = merged[-1]
            # Contiguous if next start <= prev_end + 1 day
            if start <= prev_end + timedelta(days=1):
                merged[-1] = (prev_start, max(prev_end, end))
            else:
                merged.append((start, end))

    # Check if any merged interval covers required_start to required_end
    for start, end in merged:
        if start <= required_start and end >= required_end:
            return True
    return False


# -------------------------------------------------------------------
# Core Check Completeness Implementation
# -------------------------------------------------------------------

def check_completeness(
    input_data: CheckCompletenessInput,
    checklist: Optional[ChecklistConfig] = None
) -> CheckCompletenessOutput:
    """Evaluate extracted documents against bank checklist rules deterministically."""
    if checklist is None:
        checklist = load_checklist("config/checklist.yaml")

    required_configs = checklist.get_requirements(input_data.product, input_data.employment_type)
    as_of_dt = _parse_date(input_data.as_of) or date(2026, 3, 15)
    app_dt = _parse_date(input_data.application_date) or as_of_dt

    evaluations: Dict[str, RequirementEvaluation] = {}
    unsatisfied_list: List[UnsatisfiedRequirement] = []
    has_unreadable = False

    # Group documents by doc_type
    docs_by_type: Dict[str, List[ExtractedDocument]] = {}
    for d in input_data.documents:
        docs_by_type.setdefault(d.doc_type, []).append(d)

    for req in required_configs:
        rid = req.id
        label = req.borrower_label

        # -----------------------------------------------------------
        # 1. ID_PROOF Evaluation
        # -----------------------------------------------------------
        if rid == "ID_PROOF":
            id_docs = docs_by_type.get("ID_PROOF", [])
            # Also check if any candidate ID doc was unreadable
            if any(d.doc_type == "UNREADABLE" for d in input_data.documents if "id" in d.doc_id.lower()):
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="UNREADABLE", borrower_label=label
                )
                has_unreadable = True
                continue

            if not id_docs:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="MISSING", reason_code="MISSING", borrower_label=label
                )
                unsatisfied_list.append(UnsatisfiedRequirement(requirement_id=rid, reason_code="MISSING"))
                continue

            # Check expiry
            valid_id = None
            evidence_ids = [d.doc_id for d in id_docs]
            for d in id_docs:
                exp = _parse_date(d.expiry_date)
                if exp and exp >= as_of_dt:
                    valid_id = d
                    break

            if valid_id:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="SATISFIED", evidence_doc_ids=[valid_id.doc_id], borrower_label=label
                )
            else:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="EXPIRED", reason_code="EXPIRED", evidence_doc_ids=evidence_ids, borrower_label=label
                )
                unsatisfied_list.append(UnsatisfiedRequirement(requirement_id=rid, reason_code="EXPIRED"))

        # -----------------------------------------------------------
        # 2. ADDRESS_PROOF Evaluation (Issued <= 90 days before as_of)
        # -----------------------------------------------------------
        elif rid == "ADDRESS_PROOF":
            addr_docs = docs_by_type.get("ADDRESS_PROOF", [])
            if not addr_docs:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="MISSING", reason_code="MISSING", borrower_label=label
                )
                unsatisfied_list.append(UnsatisfiedRequirement(requirement_id=rid, reason_code="MISSING"))
                continue

            valid_addr = None
            evidence_ids = [d.doc_id for d in addr_docs]
            for d in addr_docs:
                issue = _parse_date(d.issue_date)
                if issue:
                    age_days = (as_of_dt - issue).days
                    if 0 <= age_days <= req.max_days:
                        valid_addr = d
                        break

            if valid_addr:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="SATISFIED", evidence_doc_ids=[valid_addr.doc_id], borrower_label=label
                )
            else:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="STALE", reason_code="STALE", evidence_doc_ids=evidence_ids, borrower_label=label
                )
                unsatisfied_list.append(UnsatisfiedRequirement(requirement_id=rid, reason_code="STALE"))

        # -----------------------------------------------------------
        # 3. SALARY_SLIPS_3M Evaluation (Prior 3 calendar months)
        # -----------------------------------------------------------
        elif rid == "SALARY_SLIPS_3M":
            slips = docs_by_type.get("SALARY_SLIP", [])
            evidence_ids = [d.doc_id for d in slips]
            required_months = set(_get_prior_calendar_months(app_dt, req.months_count or 3))
            provided_months = {d.pay_month for d in slips if d.pay_month}

            if not slips:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="MISSING", reason_code="MISSING", borrower_label=label
                )
                unsatisfied_list.append(UnsatisfiedRequirement(requirement_id=rid, reason_code="MISSING"))
            elif required_months.issubset(provided_months):
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="SATISFIED", evidence_doc_ids=evidence_ids, borrower_label=label
                )
            else:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="INCOMPLETE_COVERAGE", reason_code="INCOMPLETE_COVERAGE",
                    evidence_doc_ids=evidence_ids, borrower_label=label
                )
                unsatisfied_list.append(UnsatisfiedRequirement(requirement_id=rid, reason_code="INCOMPLETE_COVERAGE"))

        # -----------------------------------------------------------
        # 4. BANK_STMT_6M / BANK_STMT_12M Evaluation (Interval Union)
        # -----------------------------------------------------------
        elif rid in ["BANK_STMT_6M", "BANK_STMT_12M"]:
            stmts = docs_by_type.get("BANK_STATEMENT", [])
            evidence_ids = [d.doc_id for d in stmts]
            months_count = req.months_count or (6 if rid == "BANK_STMT_6M" else 12)
            req_start, req_end = _get_prior_coverage_window(app_dt, months_count)

            if not stmts:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="MISSING", reason_code="MISSING", borrower_label=label
                )
                unsatisfied_list.append(UnsatisfiedRequirement(requirement_id=rid, reason_code="MISSING"))
                continue

            intervals = []
            for d in stmts:
                s = _parse_date(d.period_start)
                e = _parse_date(d.period_end)
                if s and e:
                    intervals.append((s, e))

            is_covered = _check_continuous_coverage(intervals, req_start, req_end)
            if is_covered:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="SATISFIED", evidence_doc_ids=evidence_ids, borrower_label=label
                )
            else:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="INCOMPLETE_COVERAGE", reason_code="INCOMPLETE_COVERAGE",
                    evidence_doc_ids=evidence_ids, borrower_label=label
                )
                unsatisfied_list.append(UnsatisfiedRequirement(requirement_id=rid, reason_code="INCOMPLETE_COVERAGE"))

        # -----------------------------------------------------------
        # 5. ITR_2Y Evaluation (Latest 2 assessment years)
        # -----------------------------------------------------------
        elif rid == "ITR_2Y":
            itr_docs = docs_by_type.get("ITR", [])
            evidence_ids = [d.doc_id for d in itr_docs]
            required_years = {"2025-26", "2024-25"}
            provided_years = {d.assessment_year for d in itr_docs if d.assessment_year}

            if not itr_docs:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="MISSING", reason_code="MISSING", borrower_label=label
                )
                unsatisfied_list.append(UnsatisfiedRequirement(requirement_id=rid, reason_code="MISSING"))
            elif required_years.issubset(provided_years):
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="SATISFIED", evidence_doc_ids=evidence_ids, borrower_label=label
                )
            else:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="INCOMPLETE_COVERAGE", reason_code="INCOMPLETE_COVERAGE",
                    evidence_doc_ids=evidence_ids, borrower_label=label
                )
                unsatisfied_list.append(UnsatisfiedRequirement(requirement_id=rid, reason_code="INCOMPLETE_COVERAGE"))

        # -----------------------------------------------------------
        # 6. BUSINESS_PROOF Evaluation
        # -----------------------------------------------------------
        elif rid == "BUSINESS_PROOF":
            biz_docs = docs_by_type.get("BUSINESS_PROOF", [])
            if biz_docs:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="SATISFIED", evidence_doc_ids=[d.doc_id for d in biz_docs], borrower_label=label
                )
            else:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="MISSING", reason_code="MISSING", borrower_label=label
                )
                unsatisfied_list.append(UnsatisfiedRequirement(requirement_id=rid, reason_code="MISSING"))

        # -----------------------------------------------------------
        # 7. PROPERTY_DOC Evaluation
        # -----------------------------------------------------------
        elif rid == "PROPERTY_DOC":
            prop_docs = docs_by_type.get("PROPERTY_DOC", [])
            if prop_docs:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="SATISFIED", evidence_doc_ids=[d.doc_id for d in prop_docs], borrower_label=label
                )
            else:
                evaluations[rid] = RequirementEvaluation(
                    requirement_id=rid, status="MISSING", reason_code="MISSING", borrower_label=label
                )
                unsatisfied_list.append(UnsatisfiedRequirement(requirement_id=rid, reason_code="MISSING"))

    # Also check if any UNREADABLE document was supplied in the packet
    if any(d.doc_type == "UNREADABLE" for d in input_data.documents):
        has_unreadable = True

    all_satisfied = (
        not has_unreadable and
        len(unsatisfied_list) == 0 and
        all(ev.status == "SATISFIED" for ev in evaluations.values())
    )

    return CheckCompletenessOutput(
        all_satisfied=all_satisfied,
        has_unreadable=has_unreadable,
        requirements=evaluations,
        unsatisfied=unsatisfied_list
    )

