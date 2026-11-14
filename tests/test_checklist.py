"""Unit tests for checklist configuration and loader."""

import pytest
from intake.checklist import load_checklist, ChecklistConfig


def test_checklist_loads_successfully():
    """Verify that intake/llm/config/checklist.yaml parses cleanly into Pydantic models by default."""
    checklist = load_checklist()
    assert isinstance(checklist, ChecklistConfig)
    assert checklist.version == "1.0"
    assert len(checklist.requirements) == 8


def test_all_expected_requirements_exist():
    """Verify that all 8 mandatory banking requirements are defined with borrower_labels."""
    checklist = load_checklist("config/checklist.yaml")
    expected_ids = {
        "ID_PROOF",
        "ADDRESS_PROOF",
        "SALARY_SLIPS_3M",
        "BANK_STMT_6M",
        "ITR_2Y",
        "BANK_STMT_12M",
        "BUSINESS_PROOF",
        "PROPERTY_DOC",
    }
    assert set(checklist.requirements.keys()) == expected_ids

    for rid, req in checklist.requirements.items():
        assert req.id == rid
        assert req.borrower_label and len(req.borrower_label.strip()) > 5
        assert req.rule_type in [
            "not_expired",
            "max_age_days",
            "prior_calendar_months",
            "continuous_coverage_months",
            "latest_assessment_years",
            "document_exists",
        ]


def test_product_employment_combinations():
    """Verify requirement mappings for all 4 product/employment combinations."""
    checklist = load_checklist("config/checklist.yaml")

    # 1. Personal Loan - Salaried
    pl_sal = checklist.get_requirement_ids("personal_loan", "salaried")
    assert set(pl_sal) == {"ID_PROOF", "ADDRESS_PROOF", "SALARY_SLIPS_3M", "BANK_STMT_6M"}

    # 2. Personal Loan - Self-Employed
    pl_se = checklist.get_requirement_ids("personal_loan", "self_employed")
    assert set(pl_se) == {"ID_PROOF", "ADDRESS_PROOF", "ITR_2Y", "BANK_STMT_12M", "BUSINESS_PROOF"}

    # 3. Home Loan - Salaried
    hl_sal = checklist.get_requirement_ids("home_loan", "salaried")
    assert set(hl_sal) == {"ID_PROOF", "ADDRESS_PROOF", "SALARY_SLIPS_3M", "BANK_STMT_6M", "PROPERTY_DOC"}

    # 4. Home Loan - Self-Employed
    hl_se = checklist.get_requirement_ids("home_loan", "self_employed")
    assert set(hl_se) == {"ID_PROOF", "ADDRESS_PROOF", "ITR_2Y", "BANK_STMT_12M", "BUSINESS_PROOF", "PROPERTY_DOC"}


def test_invalid_product_raises():
    """Verify error handling on invalid product or employment type."""
    checklist = load_checklist("config/checklist.yaml")
    with pytest.raises(ValueError, match="Unknown product"):
        checklist.get_requirement_ids("car_loan", "salaried")

    with pytest.raises(ValueError, match="Unknown employment type"):
        checklist.get_requirement_ids("personal_loan", "freelancer")

