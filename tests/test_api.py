"""Unit and integration tests for FastAPI server and TestClient endpoints."""

import json
from pathlib import Path
from fastapi.testclient import TestClient

from web.app import app


client = TestClient(app)


def _get_test_packet():
    path = Path("data/packets/pkt_001.json")
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "packet_id": "pkt_api_test",
        "as_of": "2026-03-15",
        "application_form": "Applicant Full Name: Rohit Sharma\nLoan Product Applied For: personal_loan\nEmployment Category: salaried\nRequested Loan Amount: Rs. 5,00,000\nRepayment Tenure (Months): 36\nApplication Date: 05/03/2026",
        "documents": [
            {"doc_id": "doc_01", "filename": "id.txt", "text": "PASSPORT OF INDIA Expiry Date: 2030-01-01"},
            {"doc_id": "doc_02", "filename": "bill.txt", "text": "UTILITY BILL Bill Issue Date: 10/02/2026"},
            {"doc_id": "doc_03", "filename": "slip1.txt", "text": "SALARY STATEMENT Pay Period: 2026-02"},
            {"doc_id": "doc_04", "filename": "slip2.txt", "text": "SALARY STATEMENT Pay Period: 2026-01"},
            {"doc_id": "doc_05", "filename": "slip3.txt", "text": "SALARY STATEMENT Pay Period: 2025-12"},
            {"doc_id": "doc_06", "filename": "stmt.txt", "text": "ACCOUNT STATEMENT Statement Coverage Window: 2025-09-01 to 2026-02-28"},
        ]
    }


def test_post_intake_and_get_trace_resolution():
    """Verify POST /v1/packets/intake response shape and GET /v1/traces/{trace_id} resolution."""
    packet = _get_test_packet()
    
    # 1. Test POST /v1/packets/intake
    response = client.post("/v1/packets/intake", json=packet)
    assert response.status_code == 200, f"POST failed: {response.text}"
    
    data = response.json()
    # Check exact keys specified by PDF
    expected_keys = {
        "packet_id",
        "decision",
        "document_requests",
        "fields",
        "low_confidence_fields",
        "overridden",
        "trace_id"
    }
    assert expected_keys.issubset(set(data.keys())), f"Missing keys in intake response: {expected_keys - set(data.keys())}"
    assert data["packet_id"] == packet["packet_id"]
    assert data["decision"] in ["COMPLETE", "REQUEST_DOCUMENTS", "HUMAN_REVIEW"]
    assert isinstance(data["document_requests"], list)
    assert isinstance(data["fields"], dict)
    assert isinstance(data["low_confidence_fields"], list)
    assert isinstance(data["overridden"], bool)
    assert isinstance(data["trace_id"], str)

    trace_id = data["trace_id"]

    # 2. Test GET /v1/traces/{trace_id}
    trace_res = client.get(f"/v1/traces/{trace_id}")
    assert trace_res.status_code == 200, f"GET trace failed: {trace_res.text}"
    
    trace_data = trace_res.json()
    assert trace_data["trace_id"] == trace_id
    assert trace_data["packet_id"] == packet["packet_id"]
    assert len(trace_data["steps"]) > 0

    first_step = trace_data["steps"][0]
    assert "step_number" in first_step
    assert "tool" in first_step
    assert "args" in first_step
    assert "result_summary" in first_step
    assert "latency_ms" in first_step


def test_get_trace_not_found():
    """Verify 404 response on non-existent trace_id."""
    response = client.get("/v1/traces/trace_non_existent_9999")
    assert response.status_code == 404


def test_post_intake_invalid_body():
    """Verify 400 error when packet_id is missing."""
    response = client.post("/v1/packets/intake", json={"wrong_key": 123})
    assert response.status_code == 400


def test_serve_frontend_index():
    """Verify GET / and GET /llm serve HTML dashboard."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Azentio" in response.text

    response_llm = client.get("/llm")
    assert response_llm.status_code == 200
    assert "Azentio" in response_llm.text

