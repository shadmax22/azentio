# Implementation Plan: 7. Task 3 — Dedicated Storage Package, Human Review Queue, Borrower Messaging & Audit

## 1. Objective & Architecture
Build a dedicated top-level `storage/` package and connect it to `intake` and `web`.
Whenever intake or evaluation runs, results, audit logs, and review queue items are automatically persisted to SQLite (`data/intake.db`).

### File Layout:
```text
azentio/
├── storage/
│   ├── __init__.py           # Exports public API (save_intake_result, create_review_item, etc.)
│   ├── database.py          # SQLite connection manager, thread safety, table initializations
│   ├── models.py            # Typed models for review items, intake results, audit logs, eval runs
│   ├── pii.py               # Masking for PANs (XXXXXX1234F) & bank accounts (••••••••4321)
│   └── repository.py        # Database operations & business logic (409 Conflict, corrections.jsonl)
│
├── intake/
│   ├── messaging.py         # draft_borrower_request & strict borrower_labels validator
│   ├── agent.py             # Integrates borrower_message & storage hook
│   ├── run.py               # Persists intake results to storage
│   └── eval.py              # Persists eval runs and baseline comparisons to storage
│
├── web/
│   ├── app.py               # Endpoints: GET /v1/review-items, POST /v1/review-items/{id}/resolve, GET /v1/audit-log
│   ├── static/
│   │   ├── app.js           # Multi-tab UI: Loan Intake Console, Review Queue, Audit Trail
│   │   └── style.css        # Tabbed layout, status badges, resolution modal
│   └── index.html           # UI markup with review queue and audit trail tabs
│
└── tests/
    └── test_storage_and_review.py  # 100% offline tests for storage, 409 conflict, borrower validator, PII masking
```

---

## 2. Step-by-Step Implementation

### Step 1: `storage/pii.py`
- Indian PAN regex: `\b([A-Z]{5}[0-9]{4}[A-Z])\b` $\to$ mask first 6 characters (`XXXXXX` + last 4).
- Indian Bank Account / Aadhaar regex: `\b(\d{9,18})\b` $\to$ mask all except last 4 digits (`••••••••` + last 4).
- Functions: `mask_pii_text(text: str) -> str`, `mask_pii_obj(data: Any) -> Any`.

### Step 2: `storage/database.py` & `storage/models.py`
- SQLite tables:
  1. `intake_results`: `packet_id`, `trace_id`, `decision`, `document_requests`, `fields`, `low_confidence_fields`, `overridden`, `borrower_message`, `created_at`.
  2. `review_items`: `id`, `packet_id`, `status` (`open` | `resolved`), `created_at`, `resolved_at`, `reviewer`, `decision`, `low_confidence_fields`, `packet_data`, `corrected_fields`.
  3. `audit_log`: `id`, `timestamp`, `actor` (`agent` | `reviewer` | `system` | `evaluator`), `packet_id`, `decision`, `reason_codes`, `details`.
  4. `eval_runs`: `run_id`, `timestamp`, `total_packets`, `decision_accuracy`, `false_complete_rate`, `request_f1`, `doc_type_accuracy`, `field_accuracy`, `review_rate`, `mean_steps`, `fault_rate`, `confusion_matrix`, `threshold_sweep`, `report_file`.
- Automatic table creation on init.

### Step 3: `storage/repository.py` & `storage/__init__.py`
- Functions:
  - `save_intake_result(result, packet_data=None)`
  - `create_review_item(packet_id, low_confidence_fields, packet_data)`
  - `list_review_items(status="open")`
  - `get_review_item(item_id)`
  - `resolve_review_item(item_id, reviewer, decision, corrected_fields)`:
    - If status == 'resolved', raises `AlreadyResolvedError` (maps to HTTP 409 Conflict).
    - Closes item, writes audit row, appends to `data/corrections.jsonl`.
  - `append_audit_log(actor, packet_id, decision, reason_codes, details)`
  - `get_audit_log(limit=50)`
  - `save_eval_run(eval_data, sweep_results, fault_run_data)`

### Step 4: `intake/messaging.py`
- `draft_borrower_request(document_requests, applicant_name, language='en') -> str`:
  - Builds clear message requesting unsatisfied documents.
  - Validates against checklist's `borrower_labels`:
    - All requested labels must appear.
    - Zero unrequested labels may appear.
    - If validation fails, safely falls back to deterministic template.

### Step 5: Integrate `storage` into `intake`
- `intake/agent.py`: Generate `borrower_message` for `REQUEST_DOCUMENTS`, mask PII in traces, call `storage.save_intake_result` & `storage.create_review_item` on `HUMAN_REVIEW`.
- `intake/run.py`: Save result to `storage`.
- `intake/eval.py`: Save eval runs to `storage.save_eval_run`.

### Step 6: `web/` Integration (FastAPI & UI)
- `GET /v1/review-items?status=open`
- `POST /v1/review-items/{id}/resolve` (returns 409 Conflict if already resolved)
- `GET /v1/audit-log`
- Tabbed interface in `web/index.html` (Intake Console, Human Review Queue, Audit Trail).

### Step 7: Comprehensive Unit Tests (`tests/test_storage_and_review.py`)
- Test resolve flow & status change (`open` $\to$ `resolved`).
- Test HTTP 409 Conflict on double resolution.
- Test borrower request validator & template fallback.
- Test zero full PAN or account number in traces, audit logs, and captured logs.
- Test eval run persistence to SQLite.
- Run `pytest` and verify 100% pass offline.
