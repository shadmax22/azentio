"""Ground-truth label generator for synthetic packets."""

import random
from typing import Dict, Any, List
from datetime import datetime, timedelta
from intake.schemas import PacketLabel, FormFields, DocumentLabel, ExpectedRequest
from intake.generator.sample_data import FIRST_NAMES, LAST_NAMES, AMOUNTS, TENURES


def create_label(packet_id: str, as_of: str, scenario: Dict[str, Any], rng: random.Random) -> PacketLabel:
    """Generate ground truth label for a given packet and scenario."""
    decision = scenario["decision"]
    flaw = scenario["flaw"]
    product = scenario["product"]
    employment = scenario["employment_type"]

    applicant_name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
    loan_amount = rng.choice(AMOUNTS)
    tenure_months = rng.choice(TENURES)
    app_date = "2026-03-05"

    as_of_dt = datetime.strptime(as_of, "%Y-%m-%d")

    # Document list builder
    doc_labels: List[DocumentLabel] = []
    expected_requests: List[ExpectedRequest] = []
    doc_counter = 1

    # 1. ID PROOF
    if flaw == "EXPIRED":
        # Expired prior to as_of (e.g. 2025-01-15)
        exp_date = (as_of_dt - timedelta(days=rng.randint(60, 300))).strftime("%Y-%m-%d")
        expected_requests.append(ExpectedRequest(requirement_id="ID_PROOF", reason_code="EXPIRED"))
    else:
        # Valid well into the future
        exp_date = (as_of_dt + timedelta(days=rng.randint(400, 2500))).strftime("%Y-%m-%d")

    doc_labels.append(DocumentLabel(
        doc_id=f"doc_{doc_counter:02d}",
        doc_type="ID_PROOF",
        expiry_date=exp_date
    ))
    doc_counter += 1

    # 2. ADDRESS PROOF
    if flaw == "STALE":
        # Issued > 90 days before as_of (e.g. 150 days ago)
        issue_date = (as_of_dt - timedelta(days=rng.randint(110, 220))).strftime("%Y-%m-%d")
        expected_requests.append(ExpectedRequest(requirement_id="ADDRESS_PROOF", reason_code="STALE"))
    else:
        # Issued <= 90 days before as_of (e.g. 25 days ago)
        issue_date = (as_of_dt - timedelta(days=rng.randint(10, 60))).strftime("%Y-%m-%d")

    doc_labels.append(DocumentLabel(
        doc_id=f"doc_{doc_counter:02d}",
        doc_type="ADDRESS_PROOF",
        issue_date=issue_date
    ))
    doc_counter += 1

    # 3. Employment-Specific Documents
    if employment == "salaried":
        # Requirement: SALARY_SLIPS_3M (2026-02, 2026-01, 2025-12)
        required_months = ["2026-02", "2026-01", "2025-12"]
        if flaw == "INCOMPLETE_COVERAGE":
            # Provide only 2 months instead of 3
            provided_months = required_months[:2]
            expected_requests.append(ExpectedRequest(requirement_id="SALARY_SLIPS_3M", reason_code="INCOMPLETE_COVERAGE"))
        else:
            provided_months = required_months

        for month in provided_months:
            doc_labels.append(DocumentLabel(
                doc_id=f"doc_{doc_counter:02d}",
                doc_type="SALARY_SLIP",
                pay_month=month
            ))
            doc_counter += 1

        # Requirement: BANK_STMT_6M (2025-09-01 to 2026-02-28)
        # Occasionally split across two files to test multi-file coverage
        if rng.random() < 0.4:
            # Multi-file split: 3 months + 3 months
            doc_labels.append(DocumentLabel(
                doc_id=f"doc_{doc_counter:02d}",
                doc_type="BANK_STATEMENT",
                period_start="2025-09-01",
                period_end="2025-11-30"
            ))
            doc_counter += 1
            doc_labels.append(DocumentLabel(
                doc_id=f"doc_{doc_counter:02d}",
                doc_type="BANK_STATEMENT",
                period_start="2025-12-01",
                period_end="2026-02-28"
            ))
            doc_counter += 1
        else:
            doc_labels.append(DocumentLabel(
                doc_id=f"doc_{doc_counter:02d}",
                doc_type="BANK_STATEMENT",
                period_start="2025-09-01",
                period_end="2026-02-28"
            ))
            doc_counter += 1

    else:  # self_employed
        # Requirement: ITR_2Y (2025-26, 2024-25)
        doc_labels.append(DocumentLabel(
            doc_id=f"doc_{doc_counter:02d}",
            doc_type="ITR",
            assessment_year="2025-26"
        ))
        doc_counter += 1
        doc_labels.append(DocumentLabel(
            doc_id=f"doc_{doc_counter:02d}",
            doc_type="ITR",
            assessment_year="2024-25"
        ))
        doc_counter += 1

        # Requirement: BANK_STMT_12M (2025-03-01 to 2026-02-28)
        doc_labels.append(DocumentLabel(
            doc_id=f"doc_{doc_counter:02d}",
            doc_type="BANK_STATEMENT",
            period_start="2025-03-01",
            period_end="2026-02-28"
        ))
        doc_counter += 1

        # Requirement: BUSINESS_PROOF (GST certificate)
        if flaw == "MISSING" and product != "home_loan":
            # Missing business proof
            expected_requests.append(ExpectedRequest(requirement_id="BUSINESS_PROOF", reason_code="MISSING"))
        else:
            doc_labels.append(DocumentLabel(
                doc_id=f"doc_{doc_counter:02d}",
                doc_type="BUSINESS_PROOF"
            ))
            doc_counter += 1

    # 4. Product-Specific: Home Loan PROPERTY_DOC
    if product == "home_loan":
        if flaw == "MISSING":
            # Property doc is omitted!
            expected_requests.append(ExpectedRequest(requirement_id="PROPERTY_DOC", reason_code="MISSING"))
        else:
            doc_labels.append(DocumentLabel(
                doc_id=f"doc_{doc_counter:02d}",
                doc_type="PROPERTY_DOC"
            ))
            doc_counter += 1

    # 5. Handle HUMAN_REVIEW seeded cases
    if decision == "HUMAN_REVIEW":
        expected_requests = []  # Strictly empty for human review!
        if flaw == "UNREADABLE_DOC":
            doc_labels.append(DocumentLabel(
                doc_id=f"doc_{doc_counter:02d}",
                doc_type="UNREADABLE"
            ))
            doc_counter += 1
        elif flaw == "AMBIGUOUS_FORM":
            loan_amount = None  # Ambiguous form value in ground truth

    form_fields = FormFields(
        applicant_name=applicant_name,
        product=product,
        employment_type=employment,
        loan_amount=loan_amount,
        tenure_months=tenure_months,
        application_date=app_date
    )

    return PacketLabel(
        packet_id=packet_id,
        expected_decision=decision,
        expected_requests=expected_requests,
        form_fields=form_fields,
        documents=doc_labels
    )

