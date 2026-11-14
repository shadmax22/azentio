"""Intake Agent Loop, Step Budget, Trace Recorder, and Decision Guardrail."""

import time
import uuid
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from intake.schemas import Packet
from intake.llm.provider import LLMProvider, FakeProvider, NextAction
from intake.llm.tools.registry import execute_tool, TOOL_REGISTRY


# -------------------------------------------------------------------
# Agent Output & Trace Models
# -------------------------------------------------------------------

class DocumentRequestItem(BaseModel):
    """Specification of an unsatisfied requirement and reason code."""
    requirement_id: str
    reason_code: str


class TraceStep(BaseModel):
    """Record of an individual tool call within the agent loop."""
    step_number: int
    tool: str
    args: Dict[str, Any]
    result_summary: str
    latency_ms: float
    error: Optional[str] = None


class AgentTrace(BaseModel):
    """Execution trace containing all steps for auditability."""
    trace_id: str
    packet_id: str
    steps: List[TraceStep] = Field(default_factory=list)
    total_latency_ms: float = 0.0
    guardrail_applied: bool = False
    guardrail_overridden: bool = False
    final_decision: Optional[str] = None
    termination_reason: Optional[str] = None


class AgentDecisionOutput(BaseModel):
    """Validated final intake decision shape as specified by PDF."""
    packet_id: str
    decision: Literal["COMPLETE", "REQUEST_DOCUMENTS", "HUMAN_REVIEW"]
    document_requests: List[DocumentRequestItem] = Field(default_factory=list)
    fields: Dict[str, Any] = Field(default_factory=dict)
    low_confidence_fields: List[str] = Field(default_factory=list)
    overridden: bool = False
    trace_id: str
    document_classifications: Dict[str, str] = Field(default_factory=dict)


# In-memory trace store for retrieving via GET /v1/traces/{trace_id}
TRACE_STORE: Dict[str, AgentTrace] = {}


# -------------------------------------------------------------------
# Agent Loop Execution
# -------------------------------------------------------------------

def run_agent(
    packet: Dict[str, Any],
    provider: Optional[LLMProvider] = None,
    confidence_threshold: float = 0.8,
    step_budget: int = 12
) -> AgentDecisionOutput:
    """Run agent loop with step budget, trace recording, and safety guardrails."""
    if provider is None:
        provider = FakeProvider()

    if hasattr(provider, "reset"):
        provider.reset()

    trace_id = f"trace_{uuid.uuid4().hex[:12]}"
    packet_id = packet.get("packet_id", "unknown_packet")
    start_total_time = time.perf_counter()

    trace = AgentTrace(trace_id=trace_id, packet_id=packet_id)
    messages: List[Dict[str, Any]] = []
    context: Dict[str, Any] = {"packet": packet}

    # State accumulated across tool executions
    extracted_form_fields: Dict[str, Any] = {}
    extracted_doc_classifications: Dict[str, str] = {}
    latest_completeness_res: Optional[Dict[str, Any]] = None
    step_count = 0
    model_decision: Optional[str] = None
    termination_reason: Optional[str] = None

    while step_count < step_budget:
        step_count += 1
        step_start_time = time.perf_counter()

        # 1. Ask provider for next action
        try:
            action: NextAction = provider.next_action(messages, context)
        except Exception as e:
            # Handle potential exception during provider call
            action = NextAction(is_tool_call=False, raw_response=str(e))

        # Check for malformed JSON retry
        if not action.is_tool_call and action.final_decision is None and action.raw_response and "NOT_VALID_JSON" in action.raw_response:
            # Malformed JSON retry once
            messages.append({"role": "system", "error": "Malformed JSON output. Please retry."})
            action = provider.next_action(messages, context)

        # If provider returned a final answer, exit loop
        if not action.is_tool_call:
            model_decision = action.final_decision or "HUMAN_REVIEW"
            termination_reason = action.final_reason or "Model reached final decision"
            break

        # 2. Execute Tool Call
        tool_name = action.tool_name or "unknown"
        tool_args = action.tool_args or {}

        try:
            tool_result = execute_tool(tool_name, tool_args)
            step_latency = (time.perf_counter() - step_start_time) * 1000.0

            # Record step in trace
            summary = f"Executed {tool_name} successfully."
            if tool_name == "classify_document":
                if tool_result.get("classifications"):
                    for sc in tool_result["classifications"]:
                        extracted_doc_classifications[sc["doc_id"]] = sc["doc_type"]
                elif tool_result.get("doc_id") and tool_result.get("doc_type"):
                    extracted_doc_classifications[tool_result["doc_id"]] = tool_result["doc_type"]
                summary = f"Classified {len(extracted_doc_classifications)} documents."
            elif tool_name == "extract_fields":
                if tool_result.get("fields"):
                    extracted_form_fields = tool_result.get("fields", {})
                summary = f"Extracted form fields: {list(extracted_form_fields.keys())}"
            elif tool_name == "check_completeness":
                latest_completeness_res = tool_result
                summary = f"Check completeness: all_satisfied={tool_result.get('all_satisfied')}"

            trace.steps.append(TraceStep(
                step_number=step_count,
                tool=tool_name,
                args=tool_args,
                result_summary=summary,
                latency_ms=round(step_latency, 2)
            ))

            # Feed result back to model messages
            messages.append({
                "role": "tool",
                "tool_name": tool_name,
                "result": tool_result
            })

        except Exception as err:
            step_latency = (time.perf_counter() - step_start_time) * 1000.0
            error_msg = str(err)
            trace.steps.append(TraceStep(
                step_number=step_count,
                tool=tool_name,
                args=tool_args,
                result_summary=f"Tool error: {error_msg}",
                latency_ms=round(step_latency, 2),
                error=error_msg
            ))
            # Feed structured error back so model can recover
            messages.append({
                "role": "tool_error",
                "tool_name": tool_name,
                "error": error_msg
            })

    # Check if step budget was exceeded
    if step_count >= step_budget and model_decision is None:
        model_decision = "HUMAN_REVIEW"
        termination_reason = "STEP_BUDGET_EXCEEDED"

    # -------------------------------------------------------------
    # 3. Decision Guardrail in Code
    # Evaluated in strict priority order:
    # 1. HUMAN_REVIEW if low confidence or unreadable
    # 2. REQUEST_DOCUMENTS if requirements unsatisfied
    # 3. COMPLETE
    # -------------------------------------------------------------
    low_confidence_fields: List[str] = []
    has_unreadable = False

    # Check form field confidences
    for field_name, f_res in extracted_form_fields.items():
        conf = f_res.get("confidence", 1.0)
        val = f_res.get("value")
        if conf < confidence_threshold or val is None:
            low_confidence_fields.append(field_name)

    # Check completeness result for unreadable requirements
    if latest_completeness_res:
        if latest_completeness_res.get("has_unreadable"):
            has_unreadable = True
        for req_id, ev in latest_completeness_res.get("requirements", {}).items():
            if ev.get("status") == "UNREADABLE":
                has_unreadable = True

    # Priority 1: HUMAN_REVIEW
    if len(low_confidence_fields) > 0 or has_unreadable or termination_reason == "STEP_BUDGET_EXCEEDED":
        guardrail_decision = "HUMAN_REVIEW"
        doc_requests = []
    # Priority 2: REQUEST_DOCUMENTS
    elif latest_completeness_res and not latest_completeness_res.get("all_satisfied", False):
        guardrail_decision = "REQUEST_DOCUMENTS"
        doc_requests = [
            DocumentRequestItem(
                requirement_id=u["requirement_id"],
                reason_code=u["reason_code"]
            )
            for u in latest_completeness_res.get("unsatisfied", [])
        ]
    # Priority 3: COMPLETE
    else:
        guardrail_decision = "COMPLETE"
        doc_requests = []

    # Check if model answer was overridden by guardrail
    overridden = (model_decision is not None and model_decision != guardrail_decision)

    # Save to Trace Store
    trace.total_latency_ms = round((time.perf_counter() - start_total_time) * 1000.0, 2)
    trace.final_decision = guardrail_decision
    trace.termination_reason = termination_reason
    trace.guardrail_applied = True
    trace.guardrail_overridden = overridden
    TRACE_STORE[trace_id] = trace

    # Flatten extracted form values
    flattened_fields = {k: v.get("value") for k, v in extracted_form_fields.items()}

    return AgentDecisionOutput(
        packet_id=packet_id,
        decision=guardrail_decision,
        document_requests=doc_requests,
        fields=flattened_fields,
        low_confidence_fields=low_confidence_fields,
        overridden=overridden,
        trace_id=trace_id,
        document_classifications=extracted_doc_classifications
    )
