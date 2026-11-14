"""LLMProvider interface and deterministic FakeProvider with fault injection."""

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class NextAction(BaseModel):
    """The agent's next action returned by an LLM provider."""
    is_tool_call: bool = False
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    final_decision: Optional[Literal["COMPLETE", "REQUEST_DOCUMENTS", "HUMAN_REVIEW"]] = None
    final_reason: Optional[str] = None
    raw_response: Optional[str] = None


class LLMProvider(ABC):
    """Abstract interface for LLM calls."""

    @abstractmethod
    def next_action(self, messages: List[Dict[str, Any]], context: Dict[str, Any]) -> NextAction:
        """Decide the next action: either a tool call or a final answer."""
        pass


class FakeProvider(LLMProvider):
    """Deterministic, offline provider that plans actions step-by-step without reading labels.jsonl."""

    def __init__(self, fault_mode: Optional[str] = None):
        """Initialize FakeProvider with optional fault injection mode.
        
        Supported fault modes:
        - 'unknown_tool': calls an unknown tool on first action, then recovers
        - 'invalid_args': calls classify_document with missing required args, then recovers
        - 'malformed_json': returns malformed JSON string on first call, recovers on retry
        - 'infinite_loop': keeps calling list_documents repeatedly to exceed step budget
        - 'wrong_final_decision': returns COMPLETE on an incomplete packet to test guardrail
        """
        self.fault_mode = fault_mode
        self.fault_injected = False
        self.state: Dict[str, Any] = {}

    def reset(self):
        """Reset internal provider state between packet executions."""
        self.state = {
            "listed": False,
            "doc_ids": [],
            "classified": False,
            "classifications": {},   # doc_id -> doc_type
            "extracted": False,
            "form_fields": {},
            "doc_fields": {},        # doc_id -> fields dict
            "checked": False,
            "completeness_res": None,
        }
        self.fault_injected = False

    def next_action(self, messages: List[Dict[str, Any]], context: Dict[str, Any]) -> NextAction:
        """Deterministically plan the next tool call or produce final decision."""
        if not self.state:
            self.reset()

        packet = context.get("packet", {})
        packet_id = packet.get("packet_id", "")
        as_of = packet.get("as_of", "2026-03-15")
        documents = packet.get("documents", [])

        # -------------------------------------------------------------
        # Fault Injection Triggers
        # -------------------------------------------------------------
        if self.fault_mode and not self.fault_injected:
            if self.fault_mode == "unknown_tool":
                self.fault_injected = True
                return NextAction(
                    is_tool_call=True,
                    tool_name="unregistered_phantom_tool",
                    tool_args={"query": "test"},
                    raw_response=json.dumps({"tool": "unregistered_phantom_tool", "args": {}})
                )
            elif self.fault_mode == "invalid_args":
                self.fault_injected = True
                # classify_document requires 'doc_id' and 'text', or 'packet'; pass empty args
                return NextAction(
                    is_tool_call=True,
                    tool_name="classify_document",
                    tool_args={},
                    raw_response=json.dumps({"tool": "classify_document", "args": {}})
                )
            elif self.fault_mode == "malformed_json":
                self.fault_injected = True
                return NextAction(
                    is_tool_call=False,
                    raw_response="### NOT_VALID_JSON {{{ tool: list_docs"
                )

        if self.fault_mode == "infinite_loop":
            # Continuously call list_documents so step budget is exceeded
            return NextAction(
                is_tool_call=True,
                tool_name="list_documents",
                tool_args={"packet": packet},
                raw_response=json.dumps({"tool": "list_documents", "args": {}})
            )

        # -------------------------------------------------------------
        # Normal Deterministic Planning Flow
        # -------------------------------------------------------------

        # Inspect latest tool result from messages
        if messages:
            last_msg = messages[-1]
            if last_msg.get("role") == "tool":
                tool_name = last_msg.get("tool_name")
                tool_result = last_msg.get("result", {})
                
                if tool_name == "list_documents":
                    self.state["listed"] = True
                    self.state["doc_ids"] = [d["doc_id"] for d in tool_result.get("documents", [])]

                elif tool_name == "classify_document":
                    self.state["classified"] = True
                    for sc in tool_result.get("classifications", []):
                        self.state["classifications"][sc["doc_id"]] = sc["doc_type"]
                    if tool_result.get("doc_id") and tool_result.get("doc_type"):
                        self.state["classifications"][tool_result["doc_id"]] = tool_result["doc_type"]

                elif tool_name == "extract_fields":
                    self.state["extracted"] = True
                    self.state["form_fields"] = tool_result.get("fields", {})
                    self.state["doc_fields"] = tool_result.get("documents", {})

                elif tool_name == "check_completeness":
                    self.state["checked"] = True
                    self.state["completeness_res"] = tool_result

        # Step 1: Call list_documents if not yet done
        if not self.state["listed"]:
            return NextAction(
                is_tool_call=True,
                tool_name="list_documents",
                tool_args={"packet": packet},
                raw_response=json.dumps({"tool": "list_documents", "args": {"packet_id": packet_id}})
            )

        # Step 2: Classify all documents
        if not self.state["classified"]:
            return NextAction(
                is_tool_call=True,
                tool_name="classify_document",
                tool_args={"packet": packet},
                raw_response=json.dumps({"tool": "classify_document", "args": {"packet_id": packet_id}})
            )

        # Step 3: Extract Form Fields & Document Period Fields
        if not self.state["extracted"]:
            return NextAction(
                is_tool_call=True,
                tool_name="extract_fields",
                tool_args={"packet": packet, "target": "packet"},
                raw_response=json.dumps({"tool": "extract_fields", "args": {"target": "packet"}})
            )

        # Step 4: Run check_completeness
        if not self.state["checked"]:
            extracted_doc_list = []
            doc_fields_map = self.state.get("doc_fields", {})
            classifications_map = self.state.get("classifications", {})

            for doc in documents:
                did = doc.get("doc_id", "")
                dtype = classifications_map.get(did, "UNKNOWN")
                dfields = doc_fields_map.get(did, {})

                extracted_doc_list.append({
                    "doc_id": did,
                    "doc_type": dtype,
                    "expiry_date": dfields.get("expiry_date", {}).get("value"),
                    "issue_date": dfields.get("issue_date", {}).get("value"),
                    "pay_month": dfields.get("pay_month", {}).get("value"),
                    "period_start": dfields.get("period_start", {}).get("value"),
                    "period_end": dfields.get("period_end", {}).get("value"),
                    "assessment_year": dfields.get("assessment_year", {}).get("value"),
                    "confidence": 0.95 if dtype != "UNREADABLE" else 0.40
                })

            form_f = self.state.get("form_fields", {})
            prod = form_f.get("product", {}).get("value") or "personal_loan"
            emp = form_f.get("employment_type", {}).get("value") or "salaried"
            app_d = form_f.get("application_date", {}).get("value") or as_of

            return NextAction(
                is_tool_call=True,
                tool_name="check_completeness",
                tool_args={
                    "product": prod,
                    "employment_type": emp,
                    "as_of": as_of,
                    "application_date": app_d,
                    "documents": extracted_doc_list
                },
                raw_response=json.dumps({"tool": "check_completeness", "args": {"product": prod}})
            )

        # Step 5: Final Decision Generation
        if self.fault_mode == "wrong_final_decision":
            # Intentionally produce wrong COMPLETE answer to test guardrail override
            return NextAction(
                is_tool_call=False,
                final_decision="COMPLETE",
                final_reason="Model mistakenly assumed packet is complete.",
                raw_response=json.dumps({"decision": "COMPLETE"})
            )

        res = self.state.get("completeness_res", {})
        if res.get("has_unreadable"):
            return NextAction(
                is_tool_call=False,
                final_decision="HUMAN_REVIEW",
                final_reason="Document identified as UNREADABLE.",
                raw_response=json.dumps({"decision": "HUMAN_REVIEW"})
            )
        elif res.get("all_satisfied"):
            return NextAction(
                is_tool_call=False,
                final_decision="COMPLETE",
                final_reason="All checklist requirements satisfied.",
                raw_response=json.dumps({"decision": "COMPLETE"})
            )
        else:
            return NextAction(
                is_tool_call=False,
                final_decision="REQUEST_DOCUMENTS",
                final_reason="Certain checklist requirements unsatisfied.",
                raw_response=json.dumps({"decision": "REQUEST_DOCUMENTS"})
            )
