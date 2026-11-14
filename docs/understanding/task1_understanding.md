# Task 1: Intake Tools and Agent Loop (Detailed Specification & Understanding)

## 1. Executive Summary
The goal of **Task 1** (50% of the project) is to build an automated, offline loan application intake agent in Python. 

When a borrower applies for a loan, they submit an application form along with supporting documents (ID, address proof, income documents, bank statements, etc.). The agent must:
1. Read the packet documents step-by-step using structured tools.
2. Evaluate them against banking policy rules (`config/checklist.yaml`).
3. Make one of three valid decisions:
   - **`COMPLETE`**: All checklist requirements are met and valid $\rightarrow$ sent to underwriting.
   - **`REQUEST_DOCUMENTS`**: Documents are missing, incomplete, stale, or expired $\rightarrow$ list specific missing documents to ask the borrower.
   - **`HUMAN_REVIEW`**: Documents are unreadable, blurry, low-confidence, or ambiguous $\rightarrow$ routed to an operations reviewer.

---

## 2. Architecture & Processing Flow

```
[Packet JSON (raw text)]
         │
         ▼
[Agent Loop (Pure Python While-Loop)] ◄───► [LLMProvider / FakeProvider]
         │ (calls tools up to 12 steps)
         ├── 1. list_documents()
         ├── 2. classify_document(doc_id)
         ├── 3. extract_fields(text, doc_type) -> with confidence [0, 1]
         └── 4. check_completeness(fields, checklist)
         │
         ▼
[Draft Decision from Model]
         │
         ▼
[Hard Code Guardrail] (Checks confidence < 0.8, unreadable docs, checklist mismatches)
         │
         ▼
[Final Decision JSON + Trace ID]
```

---

## 3. Core Components of Task 1

### Component 1: Synthetic Data Generator (`intake.generate`)
- **CLI Command**:
  ```bash
  python -m intake.generate --packets 40 --seed 7 --out data/
  ```
- **How it works**:
  - Sets `random.seed(7)` for 100% byte-identical reproducibility.
  - Programmatically generates **40 packets** in `data/packets/<packet_id>.json` containing **only raw text** (simulating OCR dumps) and metadata:
    - `packet_id`: Unique identifier (e.g., `pkt_001`).
    - `as_of`: Fixed baseline date (e.g., `2026-03-15`).
    - `application_form`: Free text containing borrower details.
    - `documents`: List of `{ "doc_id": "...", "filename": "scan_0042.txt", "text": "..." }`.
  - Realistic text noise must be injected:
    - Mixed date formats (`05/03/2026`, `5-Mar-26`, `March 5, 2026`).
    - Indian amount notations (`Rs. 5,00,000`, `5 lakh`, `500000 INR`).
    - Unhelpful filenames (`scan_0042.txt`, `doc_1.txt`).
    - Header/footer noise.
  - Simultaneously writes **`data/labels.jsonl`** (Ground Truth Answer Key):
    - Contains true form fields, true document types/periods, `expected_decision`, and `expected_requests`.
    - **Distribution requirement**:
      - $\ge 40\%$ of packets (16+) need documents and cover all 4 request reasons (`MISSING`, `INCOMPLETE_COVERAGE`, `STALE`, `EXPIRED`).
      - $\ge 15\%$ of packets (6+) must need human review (unreadable document or ambiguous form value), where `expected_requests` is empty `[]`.
      - Remaining packets are valid/complete.
  - **Crucial Rule**: Packet files must contain **zero label fields** (no `doc_type` or `expected_decision` inside packet JSONs). The Agent must **never** read `labels.jsonl`.

---

### Component 2: Checklist Configuration (`config/checklist.yaml`)
Defines the bank’s policies keyed by `product` (`personal_loan`, `home_loan`) and `employment_type` (`salaried`, `self_employed`):

| Product | Employment | Requirements |
| :--- | :--- | :--- |
| **All** | **All** | `ID_PROOF` (Not expired as of `as_of`), `ADDRESS_PROOF` (Issued $\le$ 90 days before `as_of`) |
| **Any** | **Salaried** | `SALARY_SLIPS_3M` (1 slip for each of the 3 prior calendar months), `BANK_STMT_6M` (Covering 6 full calendar months prior) |
| **Any** | **Self-Employed** | `ITR_2Y` (Latest 2 assessment years), `BANK_STMT_12M` (12 months), `BUSINESS_PROOF` (GST certificate) |
| **Home Loan** | **Any** | Adds `PROPERTY_DOC` |

Each requirement has a `borrower_label` (e.g., `"Last 3 months' salary slips"`), and statuses:
- `SATISFIED`
- Request reasons: `MISSING`, `INCOMPLETE_COVERAGE`, `STALE`, `EXPIRED`
- Or `UNREADABLE` (leads to human review, never to borrower request).

---

### Component 3: The 4 Typed Tools
All tools use **Pydantic v2 schemas** for arguments and return JSON-serializable outputs:

1. **`list_documents(packet_id)`**:
   - Returns list of document IDs and filenames available in the packet.
2. **`classify_document(doc_id, text)`**:
   - Categorizes document (e.g., `ID_PROOF`, `SALARY_SLIP`, `BANK_STATEMENT`, `UNREADABLE`, etc.) using keyword rules or provider.
3. **`extract_fields(text, doc_type)`**:
   - Extracts form fields: `applicant_name`, `product`, `employment_type`, `loan_amount`, `tenure_months`, `application_date`.
   - Extracts per-doc fields: `pay_month`, `period_start`, `period_end`, `assessment_year`, `issue_date`, `expiry_date`.
   - **Confidence Score**: Every extracted field must return a confidence in $[0, 1]$ computed from concrete heuristics/signals (not just an LLM guess).
4. **`check_completeness(extracted_fields, checklist)`**:
   - Pure, deterministic Python function.
   - Evaluates whether requirements are `SATISFIED` or returns the reason code (`MISSING`, `STALE`, etc.) with supporting `doc_ids`.

---

### Component 4: Agent Loop & `LLMProvider`
- **Plain Python agent loop** (No LangChain, CrewAI, or LangGraph).
- **`LLMProvider` interface**:
  - Defaults to a deterministic `FakeProvider` that runs completely offline with no API keys.
  - Supports field extraction and next action prediction (`{"tool": "...", "args": {...}}` or final decision).
  - Supports **fault injection** (malformed JSON, unknown tool, invalid args, wrong decision) for unit testing error recovery.
- **Step Budget**: Maximum **12 steps**. If exceeded, terminate in `HUMAN_REVIEW` with reason `STEP_BUDGET_EXCEEDED`.
- **Traces**: Every step is recorded in an audit trace (step number, tool, args, result summary, latency).

---

### Component 5: Decision Guardrail in Code
Applied to the model's final response in strict priority order:
1. **`HUMAN_REVIEW`**: If any required form field has confidence $< 0.8$ (configurable default), OR any requirement is `UNREADABLE`.
2. **`REQUEST_DOCUMENTS`**: If any requirement is unsatisfied in `check_completeness`. `document_requests` lists exact unsatisfied requirements and reason codes.
3. **`COMPLETE`**: If all requirements are satisfied with high confidence.
4. **Override Tracking**: If the model's answer contradicts the guardrail, the guardrail wins and `"overridden": true` is recorded.

---

### Component 6: Interfaces (CLI & API)
1. **CLI Execution**:
   ```bash
   python -m intake.run data/packets/<packet_id>.json
   ```
2. **FastAPI Endpoints**:
   - `POST /v1/packets/intake`:
     - Input: Packet JSON.
     - Output:
       ```json
       {
         "packet_id": "pkt_001",
         "decision": "REQUEST_DOCUMENTS",
         "document_requests": [
           {"requirement_id": "ADDRESS_PROOF", "reason_code": "STALE"}
         ],
         "fields": { ... },
         "low_confidence_fields": [],
         "overridden": false,
         "trace_id": "trace_abc123"
       }
       ```
   - `GET /v1/traces/{trace_id}`:
     - Returns the full execution step history for that decision.

---

## 4. "Done Means" Checklist for Task 1
- [ ] `pytest` passes 100% offline with zero environment variables or network calls.
- [ ] Generator is reproducible (seed 7 gives byte-identical output).
- [ ] Packet JSONs contain zero label fields.
- [ ] Unit tests for `check_completeness` cover: complete packet, salary slip missing month (`INCOMPLETE_COVERAGE`), multi-file bank statements covering 6 months, 120-day-old address proof (`STALE`), expired ID (`EXPIRED`), home loan without property doc (`MISSING`).
- [ ] Agent-loop tests verify fault recovery: unknown tool handling, invalid arguments error handling, malformed JSON retry, step budget 12 cutoff, and guardrail override (`overridden: true`).
- [ ] FastAPI `TestClient` tests verify `POST /v1/packets/intake` and `GET /v1/traces/{trace_id}`.
- [ ] Clean git commit history and documentation.

