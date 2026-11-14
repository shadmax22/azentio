"""Unit & Integration Tests for Storage Package, Review Queue, Borrower Messaging & Audit."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from storage import (
    init_db,
    get_db_connection,
    save_intake_result,
    create_review_item,
    list_review_items,
    get_review_item,
    resolve_review_item,
    append_audit_log,
    get_audit_log,
    save_eval_run,
    AlreadyResolvedError,
    mask_pii,
    mask_pii_text,
)
from storage.models import ResolveRequest
from intake.messaging import (
    draft_borrower_request,
    validate_borrower_message,
    build_template_message,
)
from intake.agent import run_agent, TRACE_STORE
from web.app import app


@pytest.fixture
def temp_db(tmp_path):
    """Provide an isolated SQLite database path for testing."""
    db_file = tmp_path / "test_intake.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def client(monkeypatch, temp_db):
    """Provide a FastAPI test client configured with the temporary database."""
    monkeypatch.setenv("INTAKE_DB_PATH", str(temp_db))
    return TestClient(app)


# -------------------------------------------------------------------
# 1. PII Masking Verification Tests
# -------------------------------------------------------------------

def test_pii_masking_pan_and_accounts():
    """Verify PANs and account numbers are strictly masked to last 4 characters."""
    sample_text = (
        "Applicant PAN is ABCDE1234F and salary account is 987654321098. "
        "Secondary PAN: PQRST9876Z, short account: 123456789."
    )
    masked = mask_pii_text(sample_text)

    # Full numbers must NOT appear
    assert "ABCDE1234F" not in masked
    assert "987654321098" not in masked
    assert "PQRST9876Z" not in masked
    assert "123456789" not in masked

    # Last 4 characters must be preserved
    assert "34F" in masked
    assert "1098" in masked
    assert "76Z" in masked
    assert "6789" in masked

    # Mask prefixes
    assert "XXXXXX" in masked


def test_pii_masking_recursive_structures():
    """Verify recursive masking across dictionaries and lists."""
    data = {
        "pan": "ABCDE1234F",
        "nested": {
            "account_number": "112233445566",
            "other_info": "Customer PAN ABCDE1234F has verified status",
        },
        "docs": ["Account: 998877665544", "Clean note"],
    }
    masked = mask_pii(data)

    assert "ABCDE1234F" not in json.dumps(masked)
    assert "112233445566" not in json.dumps(masked)
    assert "998877665544" not in json.dumps(masked)


def test_trace_store_and_audit_contain_no_full_pii(temp_db):
    """Assert no full PAN or account number appears in TRACE_STORE or SQLite audit table."""
    raw_packet = {
        "packet_id": "pkt_pii_test",
        "as_of": "2026-03-15",
        "application_form": (
            "Applicant Name: Vikram Malhotra\n"
            "PAN: ABCDE5678G\n"
            "Salary Account: 554433221100\n"
            "Loan Product: personal_loan\n"
            "Employment: salaried\n"
            "Loan Amount: 500000\n"
            "Tenure: 36\n"
        ),
        "documents": [
            {
                "doc_id": "doc_01",
                "filename": "pan_card.txt",
                "text": "INCOME TAX DEPARTMENT GOVT OF INDIA PAN ABCDE5678G VIKRAM MALHOTRA",
            }
        ]
    }

    result = run_agent(raw_packet)

    # Check Trace Store
    trace = TRACE_STORE.get(result.trace_id)
    assert trace is not None
    trace_dump = json.dumps(trace.model_dump())
    assert "ABCDE5678G" not in trace_dump, "Full PAN leaked into trace store"
    assert "554433221100" not in trace_dump, "Full account number leaked into trace store"

    # Check Audit Table in SQLite
    audit_rows = get_audit_log(packet_id="pkt_pii_test", db_path=temp_db)
    for row in audit_rows:
        row_dump = json.dumps(row.model_dump())
        assert "ABCDE5678G" not in row_dump, "Full PAN leaked into audit table"
        assert "554433221100" not in row_dump, "Full account number leaked into audit table"


# -------------------------------------------------------------------
# 2. Borrower Request Messaging & Validator Tests
# -------------------------------------------------------------------

def test_borrower_request_template_generation():
    """Verify template message contains correct applicant name and requested items."""
    reqs = [
        {"requirement_id": "ID_PROOF", "reason_code": "EXPIRED"},
        {"requirement_id": "SALARY_SLIPS_3M", "reason_code": "MISSING"},
    ]
    msg = build_template_message(reqs, applicant_name="Sunita Gupta")

    assert "Sunita Gupta" in msg
    assert "Government-issued Photo ID" in msg
    assert "Salary slips for the 3 calendar months" in msg
    assert "expired" in msg.lower()
    assert "7 business days" in msg


def test_borrower_validator_omitted_label_triggers_template():
    """Verify validator rejects drafts omitting a requested label and falls back to template."""
    reqs = [
        {"requirement_id": "ID_PROOF", "reason_code": "EXPIRED"},
        {"requirement_id": "ADDRESS_PROOF", "reason_code": "STALE"},
    ]
    # Draft mentions ID proof but omits Address proof
    bad_draft = (
        "Dear Customer, please upload Government-issued Photo ID (Passport, PAN, Voter ID, or Driving License)."
    )

    assert not validate_borrower_message(bad_draft, ["ID_PROOF", "ADDRESS_PROOF"])

    # draft_borrower_request must fall back to template
    result_msg = draft_borrower_request(reqs, candidate_draft=bad_draft)
    assert "Recent utility bill or address proof" in result_msg, "Failed to fallback to template"


def test_borrower_validator_extra_label_triggers_template():
    """Verify validator rejects drafts mentioning an unrequested requirement and falls back."""
    reqs = [{"requirement_id": "ID_PROOF", "reason_code": "EXPIRED"}]

    # Draft mentions ID proof but ALSO mentions Property deed which wasn't requested
    bad_draft = (
        "Dear Customer, please upload Government-issued Photo ID (Passport, PAN, Voter ID, or Driving License) "
        "and also Registered property sale agreement or title deed."
    )

    assert not validate_borrower_message(bad_draft, ["ID_PROOF"])

    # draft_borrower_request must fall back to template
    result_msg = draft_borrower_request(reqs, candidate_draft=bad_draft)
    assert "Registered property sale agreement" not in result_msg, "Extra unrequested label leaked"


def test_borrower_validator_valid_draft_accepted():
    """Verify validator accepts a draft that contains all requested and zero unrequested labels."""
    reqs = [{"requirement_id": "ID_PROOF", "reason_code": "EXPIRED"}]
    good_draft = (
        "Dear Applicant, kindly submit your Government-issued Photo ID (Passport, PAN, Voter ID, or Driving License) "
        "as the current one is expired."
    )

    assert validate_borrower_message(good_draft, ["ID_PROOF"])
    result_msg = draft_borrower_request(reqs, candidate_draft=good_draft)
    assert result_msg == good_draft


# -------------------------------------------------------------------
# 3. Human Review Queue & Resolve Flow Tests
# -------------------------------------------------------------------

def test_resolve_flow_closes_item_and_updates_audit(temp_db, tmp_path, monkeypatch):
    """Test complete resolve flow: closes item, stores final decision, writes audit row, appends correction."""
    corrections_file = tmp_path / "corrections.jsonl"
    monkeypatch.setattr("storage.repository.CORRECTIONS_FILE", corrections_file)

    # 1. Create open review item
    item = create_review_item(
        packet_id="pkt_test_resolve",
        low_confidence_fields=["loan_amount", "applicant_name"],
        packet_data={
            "packet_id": "pkt_test_resolve",
            "application_form": "Applicant: Ambiguous...",
            "as_of": "2026-03-15",
            "documents": []
        },
        db_path=temp_db,
    )
    assert item.status == "open"
    assert item.resolved_at is None

    # 2. Resolve the review item
    resolved = resolve_review_item(
        item_id=item.id,
        reviewer="officer_arun",
        decision="COMPLETE",
        corrected_fields={"applicant_name": "Arun Kumar", "loan_amount": 750000},
        notes="Verified physical KYC application copy in branch.",
        db_path=temp_db,
    )

    assert resolved.status == "resolved"
    assert resolved.reviewer == "officer_arun"
    assert resolved.decision == "COMPLETE"
    assert resolved.resolved_at is not None
    assert resolved.corrected_fields == {"applicant_name": "Arun Kumar", "loan_amount": 750000}

    # 3. Assert audit row exists in SQLite
    audit_rows = get_audit_log(packet_id="pkt_test_resolve", db_path=temp_db)
    reviewer_audits = [r for r in audit_rows if r.actor == "reviewer"]
    assert len(reviewer_audits) == 1
    assert reviewer_audits[0].decision == "COMPLETE"
    assert reviewer_audits[0].details.get("reviewer") == "officer_arun"

    # 4. Assert line appended to corrections.jsonl
    assert corrections_file.exists()
    with open(corrections_file, "r") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 1
    assert lines[0]["packet_id"] == "pkt_test_resolve"
    assert lines[0]["corrected_by"] == "officer_arun"
    assert lines[0]["form_fields"]["applicant_name"] == "Arun Kumar"


def test_duplicate_resolve_raises_409_conflict(temp_db, client):
    """Assert attempting to resolve an already-resolved item raises 409 Conflict."""
    item = create_review_item(
        packet_id="pkt_conflict_test",
        low_confidence_fields=["tenure_months"],
        packet_data={"packet_id": "pkt_conflict_test"},
        db_path=temp_db,
    )

    # First resolve succeeds
    res1 = client.post(f"/v1/review-items/{item.id}/resolve", json={
        "reviewer": "officer_1",
        "decision": "COMPLETE",
        "corrected_fields": {"tenure_months": 60}
    })
    assert res1.status_code == 200
    assert res1.json()["status"] == "resolved"

    # Second resolve must return 409 Conflict
    res2 = client.post(f"/v1/review-items/{item.id}/resolve", json={
        "reviewer": "officer_2",
        "decision": "COMPLETE",
        "corrected_fields": {"tenure_months": 60}
    })
    assert res2.status_code == 409
    assert "already resolved" in res2.json()["detail"].lower()


# -------------------------------------------------------------------
# 4. Evaluation Run Storage Test
# -------------------------------------------------------------------

def test_save_eval_run_persists_to_sqlite(temp_db):
    """Verify save_eval_run records evaluation run in eval_runs and audit_log."""
    eval_data = {
        "total_packets": 40,
        "decision_accuracy": 1.0,
        "false_complete_rate": 0.0,
        "request_prf": {"f1": 1.0, "precision": 1.0, "recall": 1.0},
        "doc_type_accuracy": 1.0,
        "field_accuracy": {"overall": 0.995},
        "review_rate": 0.15,
        "steps": {"mean": 4.0, "max": 4},
        "confusion_matrix": {"COMPLETE": {"COMPLETE": 18}},
    }

    record = save_eval_run(eval_data, db_path=temp_db)
    assert record.total_packets == 40
    assert record.decision_accuracy == 1.0
    assert record.false_complete_rate == 0.0

    # Query directly from DB
    with get_db_connection(temp_db) as conn:
        row = conn.execute("SELECT * FROM eval_runs WHERE run_id = ?", (record.run_id,)).fetchone()
        assert row is not None
        assert row["total_packets"] == 40
        assert row["false_complete_rate"] == 0.0

