"""Unit tests for check_completeness tool covering all PDF mandatory requirements."""

from intake.llm.tools.check_completeness import (
    check_completeness,
    CheckCompletenessInput,
    ExtractedDocument,
)


def test_complete_salaried_packet():
    """Test 1: Complete salaried packet passes all requirements."""
    inp = CheckCompletenessInput(
        product="personal_loan",
        employment_type="salaried",
        as_of="2026-03-15",
        application_date="2026-03-05",
        documents=[
            ExtractedDocument(doc_id="d1", doc_type="ID_PROOF", expiry_date="2030-01-01"),
            ExtractedDocument(doc_id="d2", doc_type="ADDRESS_PROOF", issue_date="2026-02-15"),
            ExtractedDocument(doc_id="d3", doc_type="SALARY_SLIP", pay_month="2026-02"),
            ExtractedDocument(doc_id="d4", doc_type="SALARY_SLIP", pay_month="2026-01"),
            ExtractedDocument(doc_id="d5", doc_type="SALARY_SLIP", pay_month="2025-12"),
            ExtractedDocument(
                doc_id="d6", doc_type="BANK_STATEMENT",
                period_start="2025-09-01", period_end="2026-02-28"
            ),
        ]
    )
    result = check_completeness(inp)
    assert result.all_satisfied is True
    assert result.has_unreadable is False
    assert len(result.unsatisfied) == 0
    assert result.requirements["ID_PROOF"].status == "SATISFIED"
    assert result.requirements["ADDRESS_PROOF"].status == "SATISFIED"
    assert result.requirements["SALARY_SLIPS_3M"].status == "SATISFIED"
    assert result.requirements["BANK_STMT_6M"].status == "SATISFIED"


def test_salary_slip_month_missing_incomplete_coverage():
    """Test 2: A salary slip month missing returns INCOMPLETE_COVERAGE."""
    inp = CheckCompletenessInput(
        product="personal_loan",
        employment_type="salaried",
        as_of="2026-03-15",
        application_date="2026-03-05",
        documents=[
            ExtractedDocument(doc_id="d1", doc_type="ID_PROOF", expiry_date="2030-01-01"),
            ExtractedDocument(doc_id="d2", doc_type="ADDRESS_PROOF", issue_date="2026-02-15"),
            ExtractedDocument(doc_id="d3", doc_type="SALARY_SLIP", pay_month="2026-02"),
            ExtractedDocument(doc_id="d4", doc_type="SALARY_SLIP", pay_month="2026-01"),
            # Missing 2025-12!
            ExtractedDocument(
                doc_id="d6", doc_type="BANK_STATEMENT",
                period_start="2025-09-01", period_end="2026-02-28"
            ),
        ]
    )
    result = check_completeness(inp)
    assert result.all_satisfied is False
    sal_eval = result.requirements["SALARY_SLIPS_3M"]
    assert sal_eval.status == "INCOMPLETE_COVERAGE"
    assert sal_eval.reason_code == "INCOMPLETE_COVERAGE"
    assert any(u.requirement_id == "SALARY_SLIPS_3M" and u.reason_code == "INCOMPLETE_COVERAGE" for u in result.unsatisfied)


def test_bank_statements_across_two_files_satisfied():
    """Test 3: Bank statements that together cover 6 months across two files are SATISFIED."""
    inp = CheckCompletenessInput(
        product="personal_loan",
        employment_type="salaried",
        as_of="2026-03-15",
        application_date="2026-03-05",
        documents=[
            ExtractedDocument(doc_id="d1", doc_type="ID_PROOF", expiry_date="2030-01-01"),
            ExtractedDocument(doc_id="d2", doc_type="ADDRESS_PROOF", issue_date="2026-02-15"),
            ExtractedDocument(doc_id="d3", doc_type="SALARY_SLIP", pay_month="2026-02"),
            ExtractedDocument(doc_id="d4", doc_type="SALARY_SLIP", pay_month="2026-01"),
            ExtractedDocument(doc_id="d5", doc_type="SALARY_SLIP", pay_month="2025-12"),
            # File 1: Sep 1, 2025 to Nov 30, 2025
            ExtractedDocument(
                doc_id="d6a", doc_type="BANK_STATEMENT",
                period_start="2025-09-01", period_end="2025-11-30"
            ),
            # File 2: Dec 1, 2025 to Feb 28, 2026
            ExtractedDocument(
                doc_id="d6b", doc_type="BANK_STATEMENT",
                period_start="2025-12-01", period_end="2026-02-28"
            ),
        ]
    )
    result = check_completeness(inp)
    assert result.all_satisfied is True
    bank_eval = result.requirements["BANK_STMT_6M"]
    assert bank_eval.status == "SATISFIED"
    assert set(bank_eval.evidence_doc_ids) == {"d6a", "d6b"}


def test_120_day_old_address_proof_stale():
    """Test 4: 120-day-old address proof returns STALE."""
    inp = CheckCompletenessInput(
        product="personal_loan",
        employment_type="salaried",
        as_of="2026-03-15",
        application_date="2026-03-05",
        documents=[
            ExtractedDocument(doc_id="d1", doc_type="ID_PROOF", expiry_date="2030-01-01"),
            # Issue date is 120 days before 2026-03-15 (2025-11-15)
            ExtractedDocument(doc_id="d2", doc_type="ADDRESS_PROOF", issue_date="2025-11-15"),
            ExtractedDocument(doc_id="d3", doc_type="SALARY_SLIP", pay_month="2026-02"),
            ExtractedDocument(doc_id="d4", doc_type="SALARY_SLIP", pay_month="2026-01"),
            ExtractedDocument(doc_id="d5", doc_type="SALARY_SLIP", pay_month="2025-12"),
            ExtractedDocument(
                doc_id="d6", doc_type="BANK_STATEMENT",
                period_start="2025-09-01", period_end="2026-02-28"
            ),
        ]
    )
    result = check_completeness(inp)
    assert result.all_satisfied is False
    addr_eval = result.requirements["ADDRESS_PROOF"]
    assert addr_eval.status == "STALE"
    assert addr_eval.reason_code == "STALE"


def test_expired_id_returns_expired():
    """Test 5: An expired ID returns EXPIRED."""
    inp = CheckCompletenessInput(
        product="personal_loan",
        employment_type="salaried",
        as_of="2026-03-15",
        application_date="2026-03-05",
        documents=[
            # Expired in 2025
            ExtractedDocument(doc_id="d1", doc_type="ID_PROOF", expiry_date="2025-01-10"),
            ExtractedDocument(doc_id="d2", doc_type="ADDRESS_PROOF", issue_date="2026-02-15"),
            ExtractedDocument(doc_id="d3", doc_type="SALARY_SLIP", pay_month="2026-02"),
            ExtractedDocument(doc_id="d4", doc_type="SALARY_SLIP", pay_month="2026-01"),
            ExtractedDocument(doc_id="d5", doc_type="SALARY_SLIP", pay_month="2025-12"),
            ExtractedDocument(
                doc_id="d6", doc_type="BANK_STATEMENT",
                period_start="2025-09-01", period_end="2026-02-28"
            ),
        ]
    )
    result = check_completeness(inp)
    assert result.all_satisfied is False
    id_eval = result.requirements["ID_PROOF"]
    assert id_eval.status == "EXPIRED"
    assert id_eval.reason_code == "EXPIRED"


def test_home_loan_without_property_doc_missing():
    """Test 6: Home loan without PROPERTY_DOC returns MISSING."""
    inp = CheckCompletenessInput(
        product="home_loan",
        employment_type="salaried",
        as_of="2026-03-15",
        application_date="2026-03-05",
        documents=[
            ExtractedDocument(doc_id="d1", doc_type="ID_PROOF", expiry_date="2030-01-01"),
            ExtractedDocument(doc_id="d2", doc_type="ADDRESS_PROOF", issue_date="2026-02-15"),
            ExtractedDocument(doc_id="d3", doc_type="SALARY_SLIP", pay_month="2026-02"),
            ExtractedDocument(doc_id="d4", doc_type="SALARY_SLIP", pay_month="2026-01"),
            ExtractedDocument(doc_id="d5", doc_type="SALARY_SLIP", pay_month="2025-12"),
            ExtractedDocument(
                doc_id="d6", doc_type="BANK_STATEMENT",
                period_start="2025-09-01", period_end="2026-02-28"
            ),
            # Missing PROPERTY_DOC!
        ]
    )
    result = check_completeness(inp)
    assert result.all_satisfied is False
    prop_eval = result.requirements["PROPERTY_DOC"]
    assert prop_eval.status == "MISSING"
    assert prop_eval.reason_code == "MISSING"


def test_unreadable_document_flags_human_review():
    """Test 7: Unreadable document sets has_unreadable flag."""
    inp = CheckCompletenessInput(
        product="personal_loan",
        employment_type="salaried",
        as_of="2026-03-15",
        application_date="2026-03-05",
        documents=[
            ExtractedDocument(doc_id="d1", doc_type="ID_PROOF", expiry_date="2030-01-01"),
            ExtractedDocument(doc_id="d2", doc_type="ADDRESS_PROOF", issue_date="2026-02-15"),
            ExtractedDocument(doc_id="d3", doc_type="SALARY_SLIP", pay_month="2026-02"),
            ExtractedDocument(doc_id="d4", doc_type="SALARY_SLIP", pay_month="2026-01"),
            ExtractedDocument(doc_id="d5", doc_type="SALARY_SLIP", pay_month="2025-12"),
            ExtractedDocument(
                doc_id="d6", doc_type="BANK_STATEMENT",
                period_start="2025-09-01", period_end="2026-02-28"
            ),
            ExtractedDocument(doc_id="d7", doc_type="UNREADABLE"),
        ]
    )
    result = check_completeness(inp)
    assert result.has_unreadable is True
    assert result.all_satisfied is False

