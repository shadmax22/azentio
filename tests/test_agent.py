"""Unit tests for Agent Loop, Guardrails, Trace recording, and Fault Injection."""

import json
from pathlib import Path
from intake.agent import run_agent, TRACE_STORE
from intake.llm.provider import FakeProvider


def _get_sample_complete_packet():
    """Load or build a sample complete packet."""
    path = Path("data/packets/pkt_001.json")
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "packet_id": "pkt_sample",
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


def _get_sample_incomplete_packet():
    """Packet missing one salary slip and with stale address proof."""
    return {
        "packet_id": "pkt_incomplete",
        "as_of": "2026-03-15",
        "application_form": "Applicant Full Name: Rohit Sharma\nLoan Product Applied For: personal_loan\nEmployment Category: salaried\nRequested Loan Amount: Rs. 5,00,000\nRepayment Tenure (Months): 36\nApplication Date: 05/03/2026",
        "documents": [
            {"doc_id": "doc_01", "filename": "id.txt", "text": "PASSPORT OF INDIA Expiry Date: 2030-01-01"},
            {"doc_id": "doc_02", "filename": "bill.txt", "text": "UTILITY BILL Bill Issue Date: 01/10/2025"}, # STALE > 90 days!
            {"doc_id": "doc_03", "filename": "slip1.txt", "text": "SALARY STATEMENT Pay Period: 2026-02"},
            {"doc_id": "doc_04", "filename": "slip2.txt", "text": "SALARY STATEMENT Pay Period: 2026-01"},
            # Missing 2025-12
            {"doc_id": "doc_06", "filename": "stmt.txt", "text": "ACCOUNT STATEMENT Statement Coverage Window: 2025-09-01 to 2026-02-28"},
        ]
    }


def test_agent_happy_path():
    """Verify normal agent execution with FakeProvider."""
    packet = _get_sample_complete_packet()
    output = run_agent(packet, provider=FakeProvider())

    assert output.packet_id == packet["packet_id"]
    assert output.decision in ["COMPLETE", "REQUEST_DOCUMENTS", "HUMAN_REVIEW"]
    assert output.trace_id in TRACE_STORE
    assert len(TRACE_STORE[output.trace_id].steps) > 0


def test_fault_injection_unknown_tool_recovers():
    """Verify unknown tool name produces a structured error and loop recovers."""
    packet = _get_sample_complete_packet()
    provider = FakeProvider(fault_mode="unknown_tool")
    output = run_agent(packet, provider=provider)

    trace = TRACE_STORE[output.trace_id]
    # Check that error was captured in trace
    has_error_step = any(step.error is not None and "unregistered_phantom_tool" in step.error for step in trace.steps)
    assert has_error_step, "Expected trace to record unknown tool error"
    # Verify agent still successfully recovered and finished
    assert output.decision is not None


def test_fault_injection_invalid_args_recovers():
    """Verify invalid tool arguments produce a structured error and loop recovers."""
    packet = _get_sample_complete_packet()
    provider = FakeProvider(fault_mode="invalid_args")
    output = run_agent(packet, provider=provider)

    trace = TRACE_STORE[output.trace_id]
    has_validation_err = any(step.error is not None for step in trace.steps)
    assert has_validation_err, "Expected validation error in trace step"
    assert output.decision is not None


def test_fault_injection_malformed_json_retries():
    """Verify malformed JSON output is retried once."""
    packet = _get_sample_complete_packet()
    provider = FakeProvider(fault_mode="malformed_json")
    output = run_agent(packet, provider=provider)

    assert output.decision is not None
    assert output.trace_id in TRACE_STORE


def test_step_budget_exceeded_ends_in_human_review():
    """Verify a model that never finishes terminates in HUMAN_REVIEW with STEP_BUDGET_EXCEEDED."""
    packet = _get_sample_complete_packet()
    provider = FakeProvider(fault_mode="infinite_loop")
    output = run_agent(packet, provider=provider, step_budget=12)

    assert output.decision == "HUMAN_REVIEW"
    trace = TRACE_STORE[output.trace_id]
    assert len(trace.steps) == 12
    assert trace.termination_reason == "STEP_BUDGET_EXCEEDED"


def test_guardrail_overrides_wrong_model_decision():
    """Verify a model answering COMPLETE on an incomplete packet is overridden to REQUEST_DOCUMENTS."""
    packet = _get_sample_incomplete_packet()
    provider = FakeProvider(fault_mode="wrong_final_decision")
    output = run_agent(packet, provider=provider)

    # Guardrail must catch missing docs and override model's answer
    assert output.decision == "REQUEST_DOCUMENTS"
    assert output.overridden is True
    assert len(output.document_requests) > 0

