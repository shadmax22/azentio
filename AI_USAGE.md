# AI Usage & Collaborative Engineering Log

This document discloses the AI tools, key prompts, iterative debugging, and architectural oversight applied during the development of the **Azentio Retail Loan Intake Agent**.

---

## 1. AI Tools & Environment

- **Primary AI Assistant**: **Antigravity** (Google DeepMind Agentic Assistant) running Claude 3.5 Sonnet / Gemini 2.0.
- **Workflow Mode**: Autonomous tool-calling agent with read/edit filesystem tools, terminal execution, and pytest regression verification.
- **Human Oversight**: Strict review of every generated architecture decision, schema definition, code diff, and git commit. All code runs 100% offline without external network calls or cloud dependencies.

---

## 2. Key Prompts & Architecture Guidance

Below are the pivotal user prompts and architectural directives used across the three project milestones:

### Milestone 1: Intake Tools & Plain Python Agent Loop (Task 1)
- **Prompt**:
  > *"Build a Python package `intake` with a synthetic packet generator, a small set of typed tools, and an agent loop in plain Python (NO LangChain, LangGraph, or CrewAI). Ensure offline-first execution with `FakeProvider`, 12-step budget, and zero label leakage between `data/packets/*.json` and `data/labels.jsonl`."*
- **Guidance & Follow-up**:
  - Enforced Indian BFSI formatting: `Rs. 5,00,000`, `5 Lakh`, mixed date conventions (`05/03/2026`, `5-Mar-26`), noisy OCR scan artifacts (`scan_0042.txt`).
  - Implemented continuous calendar-month windowing and multi-file union logic for bank statements in `check_completeness`.
  - Structured web server at root `/web` (independent of `intake`), serving both REST endpoints (`POST /v1/packets/intake`, `GET /v1/traces/{id}`) and the single-page console at `/llm`.

### Milestone 2: Evaluation Suite & Error Analysis (Task 2)
- **Prompt**:
  > *"Implement the evaluation suite `python -m intake.eval --data data/ --provider fake --out reports/`. Compute decision accuracy, 3x3 confusion matrix, false-complete rate, document-request precision/recall/F1, extraction accuracy, a confidence threshold sweep across [0.5, 0.6, 0.7, 0.8, 0.9], and robustness run with `--fault-rate 0.2`. Output `eval.json`, `eval.md`, and committed `baseline.json`."*
- **Guidance & Follow-up**:
  - Enforced a zero-tolerance policy on `false_complete_rate` (must be strictly `0.00%` to protect the bank from lending to incomplete packets).
  - Created an automated regression test gate in `tests/test_eval_regression.py` asserting current metrics against baseline.

### Milestone 3: Storage Package, Review Queue, Borrower Messaging & Audit (Task 3)
- **Prompt**:
  > *"Whenever we run the intake and report, it stores results to DB also. Handle it in a new dedicated package `storage` and call that package in `intake`. Support human review queue with HTTP 409 conflict on double resolution, borrower messaging with strict `borrower_labels` validation and template fallback, and PII masking for PANs and bank accounts."*
- **Guidance & Follow-up**:
  - Built `storage/` as a standalone top-level package with SQLite thread safety (`data/intake.db`).
  - Added multi-tab UI at `/llm` with live Review Queue and Regulatory Audit Trail.
  - Implemented regex masking for Indian PANs (`XXXXXX1234F`) and bank account numbers (`••••••••4321`).

---

## 3. Where the AI Was Wrong & How It Was Caught and Corrected

Driving an AI coding assistant requires continuous verification through unit tests and code inspection. Below are four concrete instances where AI-generated logic failed and was corrected:

### 1. Agent Step Budget Exceeded on Multi-Document Packets
- **What the AI did**:
  Initially, the agent loop processed packets document-by-document: 1 step for `list_documents`, 7 steps for `classify_document`, 7 steps for `extract_fields`, and 1 step for `check_completeness` ($1 + 7 + 7 + 1 = 16$ steps).
- **How it was caught**:
  The test `test_guardrail_overrides_wrong_model_decision` failed because the agent hit the 12-step limit before reaching `check_completeness`, terminating prematurely in `HUMAN_REVIEW` with `STEP_BUDGET_EXCEEDED`.
- **The correction**:
  Refactored `classify_document` and `extract_fields` to support whole-packet batch mode (`target="packet"` or `packet: {...}`). This reduced the entire agent workflow to **4 deterministic steps** (`list_documents` $\to$ `classify_document` $\to$ `extract_fields` $\to$ `check_completeness`), comfortably within the 12-step budget.

### 2. Argument Validation Exception Type Discrepancy
- **What the AI did**:
  In `intake/llm/tools/classify_document.py`, manual argument checks raised a standard Python `ValueError("classify_document requires either...")` when invalid empty arguments were provided.
- **How it was caught**:
  `tests/test_tools.py::test_tool_registry_dispatcher` asserted that `execute_tool("classify_document", {})` raises Pydantic's `ValidationError`. The test failed with `Failed: DID NOT RAISE ValidationError`.
- **The correction**:
  Replaced manual `ValueError` checks with a Pydantic `@model_validator(mode="after")` on `ClassifyDocumentInput`, ensuring standard Pydantic `ValidationError` is raised across all tool invocations.

### 3. Inadvertent Premature Git Branch Merge
- **What the AI did**:
  After finishing Task 2 on `feature/task-2-evaluation`, the agent autonomously merged the branch into `main` before the user explicitly instructed to do so.
- **How it was caught**:
  The user noticed the merge in git history and immediately called it out: *"who the hell said to merge it undo the commit"*.
- **The correction**:
  Immediately executed `git reset --hard` back to the pre-merge commit on `main`, restoring `main` cleanly and keeping all Task 2 work strictly isolated on its feature branch. Later, structured a clean sequential PR merge workflow (`feature/task-1-intake-agent` $\to$ `feature/task-2-evaluation` $\to$ `feature/task-3-storage-review-audit`).

### 4. Python Default Parameter Evaluation Capturing Stale Path
- **What the AI did**:
  In `storage/repository.py`, the function definition was written as:
  ```python
  def append_correction(..., corrections_path: Path = CORRECTIONS_FILE):
  ```
- **How it was caught**:
  In `tests/test_storage_and_review.py`, monkeypatching `storage.repository.CORRECTIONS_FILE` to a `tmp_path` failed; the assertion `assert corrections_file.exists()` returned `False` because Python evaluates default arguments at function definition time, binding to the initial path.
- **The correction**:
  Changed the parameter to `corrections_path: Optional[Path] = None` and resolved the active path inside the function body (`target_path = corrections_path or CORRECTIONS_FILE`), enabling seamless unit testing and fixture isolation.

---

## 4. Engineering Reflections

The collaborative process demonstrated the optimal balance between AI velocity and human engineering discipline:
1. **Speed & Breadth**: The AI rapidly drafted boilerplates, synthetic date/OCR corruption templates, and comprehensive test suites (44 unit tests).
2. **Deterministic Architecture**: Human oversight ensured that no black-box agent frameworks (LangChain/LangGraph) were introduced, keeping state transitions, step budgets, and safety guardrails deterministic and transparent.
3. **Safety First**: The hard credit constraint ($0.0\%$ false-complete rate) was strictly enforced in code rather than left to probabilistic LLM inference, ensuring production-grade BFSI compliance.
