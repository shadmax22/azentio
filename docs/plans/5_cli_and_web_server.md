# Implementation Plan: 5. CLI Runner & Root `/web` FastAPI Server with UI

## 1. Goal
Implement the user-facing interfaces for Task 1:
1. **CLI Runner (`intake/run.py`)**:
   Enables `python -m intake.run data/packets/<id>.json` to print the validated intake decision JSON.
2. **Root `/web` FastAPI Server (`web/app.py`)**:
   Placed at the root directory (`/web`), isolated from internal logic, importing and accessing the `intake` package:
   - `POST /v1/packets/intake`
   - `GET /v1/traces/{trace_id}`
   - Serves an interactive single-page UI (HTML/JS/CSS) at `http://localhost:8000/`.
3. **Interactive Frontend (`web/index.html` & `web/static/`)**:
   - Allows operators/reviewers to paste or select a packet JSON.
   - Triggers the intake agent.
   - Displays real-time decision badges, extracted fields, low-confidence warnings, and the full step-by-step audit trace.
4. **FastAPI TestClient Suite (`tests/test_api.py`)**:
   - Asserts response schema of `POST /v1/packets/intake`.
   - Asserts resolution of `GET /v1/traces/{trace_id}`.
   - Asserts frontend endpoint returns `200 OK`.

---

## 2. Directory Structure

```text
azentio/
├── intake/
│   ├── run.py                      # CLI entrypoint: python -m intake.run <path>
│   └── ...
│
├── web/                            # Root-level Web Server & UI
│   ├── app.py                      # FastAPI application & REST endpoints
│   ├── static/
│   │   ├── app.js                  # Frontend client script
│   │   └── style.css               # Modern, clean UI styling
│   └── index.html                  # Single-page visual dashboard
│
└── tests/
    └── test_api.py                 # FastAPI TestClient test suite
```

---

## 3. Component Details

### 3.1 CLI Runner (`intake/run.py`)
- Takes packet file path: `python -m intake.run data/packets/pkt_001.json`.
- Loads JSON file.
- Calls `run_agent(packet)`.
- Dumps formatted decision JSON to stdout matching:
  ```json
  {
    "packet_id": "pkt_001",
    "decision": "COMPLETE",
    "document_requests": [],
    "fields": { ... },
    "low_confidence_fields": [],
    "overridden": false,
    "trace_id": "trace_..."
  }
  ```

### 3.2 FastAPI Server (`web/app.py`)
- Endpoints:
  - `GET /` $\rightarrow$ Serves `web/index.html`.
  - `POST /v1/packets/intake` $\rightarrow$ Body: Packet JSON $\rightarrow$ Output: `AgentDecisionOutput`.
  - `GET /v1/traces/{trace_id}` $\rightarrow$ Output: `AgentTrace` with all execution steps.
  - `GET /v1/packets/sample` $\rightarrow$ Lists local packet files for quick testing from UI.

### 3.3 Visual Frontend (`web/index.html`)
- Modern, clean BFSI intake dashboard:
  - Packet selection dropdown or JSON text editor.
  - "Run Intake Agent" button.
  - Real-time decision summary card:
    - Status Badge: `COMPLETE` (Green), `REQUEST_DOCUMENTS` (Amber), `HUMAN_REVIEW` (Crimson).
    - Guardrail Override flag indicator.
    - Missing documents list with reason tags (`STALE`, `EXPIRED`, `INCOMPLETE_COVERAGE`, `MISSING`).
    - Extracted Form Fields table with confidence meters.
    - Low-confidence alert badges.
  - Step-by-Step Execution Trace view (step number, tool invoked, execution latency, arguments, result summary).

---

## 4. Execution Steps
1. Create `intake/run.py`.
2. Create `web/app.py`, `web/index.html`, `web/static/style.css`, `web/static/app.js`.
3. Create `tests/test_api.py`.
4. Run `pytest tests/` to verify all 26+ tests pass cleanly.

