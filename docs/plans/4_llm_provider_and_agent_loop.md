# Implementation Plan: 4. LLM Provider & Agent Loop

## 1. Goal
Implement the core agent intelligence:
1. `intake/llm/provider.py` — The `LLMProvider` interface and the deterministic `FakeProvider` with fault-injection support.
2. `intake/agent.py` — The pure Python agent loop with step budget (max 12), step-by-step trace recording, and the strict safety guardrail.
3. `tests/test_agent.py` — Comprehensive unit and fault-injection tests.

---

## 2. Component Design

### 2.1 `LLMProvider` Interface & `FakeProvider` (`intake/llm/provider.py`)
- **`LLMProvider` (Abstract Base Class)**:
  - `plan_next_action(messages, available_tools, context) -> NextAction`: Returns either a tool call `{"tool": str, "args": dict}` or a final answer `{"decision": str, ...}`.
  - `extract_fields_llm(text, schema) -> dict`: Returns structured JSON.
- **`FakeProvider` (Deterministic Implementation)**:
  - **Zero Knowledge Rule**: Never reads `data/labels.jsonl`!
  - **Workflow State Machine**:
    1. If `list_documents` not run $\rightarrow$ call `list_documents`.
    2. For each document in list $\rightarrow$ call `classify_document`.
    3. Call `extract_fields` for `target="form"`.
    4. For each classified document $\rightarrow$ call `extract_fields` for `target="document"`.
    5. Call `check_completeness` with the accumulated extraction fields.
    6. Return final answer based on tool outputs.
  - **Fault Injection Capabilities**:
    - `fault_mode = "unknown_tool"`: emits unknown tool name on first action $\rightarrow$ agent must feed error back $\rightarrow$ provider recovers.
    - `fault_mode = "invalid_args"`: emits invalid args for tool $\rightarrow$ agent must feed error back $\rightarrow$ provider recovers.
    - `fault_mode = "malformed_json"`: emits malformed JSON string $\rightarrow$ agent retries once.
    - `fault_mode = "infinite_loop"`: continuously calls tools without terminating $\rightarrow$ tests step budget 12 cutoff.
    - `fault_mode = "wrong_final_decision"`: answers `COMPLETE` even when requirements are missing $\rightarrow$ tests guardrail override.

---

### 2.2 Agent Loop & Guardrail (`intake/agent.py`)
- **Trace Model**:
  - `trace_id`: UUID string.
  - `steps`: `List[TraceStep]` with `step_number`, `tool`, `args`, `result_summary`, `latency_ms`.
- **Step Budget**:
  - Maximum **12 steps**.
  - If counter exceeds 12, loop terminates with `decision = "HUMAN_REVIEW"` and reason `"STEP_BUDGET_EXCEEDED"`.
- **Error Handling & Retry**:
  - Invalid tool name or arguments: structured error dict fed back to provider in conversation history.
  - Malformed JSON from provider: retried once.
- **Decision Guardrail (Strict Priority Order)**:
  1. `HUMAN_REVIEW` if:
     - Any required form field has `confidence < confidence_threshold` (default 0.8).
     - Any requirement is `UNREADABLE` (or document type / period confidence $< 0.8$).
  2. `REQUEST_DOCUMENTS` if:
     - Any requirement is unsatisfied in the latest `check_completeness` result.
     - `document_requests` equals the unsatisfied requirements and reason codes.
  3. Otherwise `COMPLETE`.
  - For `COMPLETE` and `HUMAN_REVIEW`, `document_requests` is strictly empty `[]`.
  - If model's proposed answer disagrees with guardrail $\rightarrow$ guardrail wins and `overridden = True`.

---

## 3. Implementation Steps

1. Create `intake/llm/provider.py`.
2. Create `intake/agent.py`.
3. Create `tests/test_agent.py` covering:
   - Happy path: `COMPLETE` packet execution.
   - Defective packet: `REQUEST_DOCUMENTS` execution.
   - Fault injection: unknown tool name recovery.
   - Fault injection: invalid tool arguments recovery.
   - Fault injection: malformed JSON retry.
   - Fault injection: step budget 12 cutoff $\rightarrow$ `HUMAN_REVIEW` with `STEP_BUDGET_EXCEEDED`.
   - Fault injection: model answering `COMPLETE` on incomplete packet is overridden $\rightarrow$ `REQUEST_DOCUMENTS` with `overridden: True`.

