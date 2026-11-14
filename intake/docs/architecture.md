# Intake Generator Architecture: How These Files Work Together

This document outlines the internal architecture, component interactions, and data flow of the `intake` generation system.

---

## 1. Package Architecture Overview

```text
intake/
├── __init__.py
├── generate.py                     # Main CLI entrypoint (python -m intake.generate)
├── schemas.py                      # Pydantic schemas for Packets and Labels
│
├── docs/                           # Internal package documentation
│   └── architecture.md             # This architecture document
│
└── generator/                      # Generation subpackage
    ├── __init__.py
    ├── scenarios.py                # Scenario recipes & quota distribution (40% req docs, 15% review)
    ├── generate_labels.py          # Ground truth generator (outputs data for labels.jsonl)
    ├── generate_packets.py         # Packet text renderer (converts ground truth into noisy text)
    ├── templates.py                # Document & form text templates (Passport, Bills, Salary slips, etc.)
    └── noise.py                    # Noise generators (Indian currency formatting, mixed dates, scan names)
```

---

## 2. Component Collaboration & Data Flow

```
                               ┌───────────────────────────┐
                               │     intake/generate.py    │
                               │   (CLI: --packets, --seed)│
                               └─────────────┬─────────────┘
                                             │
                              1. Calls build_scenario_bucket()
                                             ▼
                               ┌───────────────────────────┐
                               │   generator/scenarios.py  │
                               │(Recipe list & seed shuffle│
                               └─────────────┬─────────────┘
                                             │
                For each packet i:           │
                ┌────────────────────────────┴────────────────────────────┐
                ▼                                                         ▼
    2. Calls create_label()                                    3. Calls render_packet()
    ┌──────────────────────────────┐                           ┌──────────────────────────────┐
    │ generator/generate_labels.py │                           │ generator/generate_packets.py│
    │                              │                           │                              │
    │ • Assigns true dates/amounts │───(passes structured)────►│ • Injects noisy dates/INR    │
    │ • Sets expected_decision     │    label object           │ • Uses generator/templates.py│
    │ • Sets expected_requests     │                           │ • Uses generator/noise.py    │
    └──────────────┬───────────────┘                           └──────────────┬───────────────┘
                   │                                                          │
                   ▼                                                          ▼
      Appends 1 line to:                                           Writes raw packet to:
       data/labels.jsonl                                         data/packets/<packet_id>.json
```

---

## 3. Detailed Component Contracts

### 3.1 `intake/generate.py` (CLI & Orchestrator)
- **Role**: Entry point for the CLI command `python -m intake.generate`.
- **Inputs**: `--packets` (int), `--seed` (int), `--out` (path).
- **Execution**:
  1. Initializes `random.seed(seed)` to guarantee byte-level reproducibility.
  2. Ensures output directory structure exists (`<out>/packets/`).
  3. Requests scenario distribution from `scenarios.py`.
  4. Iterates sequentially over each scenario:
     - Invokes `generate_labels.create_label` to get structured truth.
     - Writes record to `<out>/labels.jsonl`.
     - Invokes `generate_packets.render_packet` to produce raw noisy text packet.
     - Writes raw packet JSON to `<out>/packets/<packet_id>.json`.

---

### 3.2 `intake/generator/scenarios.py` (Distribution & Recipe Bucket)
- **Role**: Ensures that the generated dataset meets strict BFSI regulatory testing quotas.
- **Contract**:
  - Total packets default = 40.
  - $\ge 40\%$ (16 packets) marked `REQUEST_DOCUMENTS`:
    - 4 $\times$ `MISSING` (e.g. Home loan missing Property Document).
    - 4 $\times$ `INCOMPLETE_COVERAGE` (e.g. only 2 of 3 salary slips or 4 of 6 bank statement months).
    - 4 $\times$ `STALE` (e.g. Address proof issued $>90$ days prior to `as_of`).
    - 4 $\times$ `EXPIRED` (e.g. ID proof expired prior to `as_of`).
  - $\ge 15\%$ (6 packets) marked `HUMAN_REVIEW`:
    - 3 $\times$ `UNREADABLE_DOC` (garbled/corrupted OCR scans).
    - 3 $\times$ `AMBIGUOUS_FORM` (unclear loan amount or ambiguous applicant details).
    - **Requirement**: `expected_requests` is strictly empty `[]`.
  - $\approx 45\%$ (18 packets) marked `COMPLETE` (all requirements valid and satisfied).
  - Shuffles recipes using the seeded pseudo-random number generator.

---

### 3.3 `intake/generator/generate_labels.py` (Answer Key Builder)
- **Role**: Generates the authoritative Ground Truth for each packet.
- **Contract**:
  - Builds the structured Python dictionary matching the `PacketGroundTruthLabel` schema in `intake/schemas.py`.
  - Calculates true calendar windows relative to `as_of` (e.g., prior 3 months for salaried slips).
  - Explicitly states `expected_decision` and `expected_requests` (requirement IDs + reason codes).

---

### 3.4 `intake/generator/generate_packets.py` (Raw Text & Packet Renderer)
- **Role**: Transforms structured ground-truth data into raw, realistic, unstructured text files.
- **Contract**:
  - Consumes the label object produced by `generate_labels.py`.
  - Calls `templates.py` to populate free-text document contents.
  - Applies `noise.py` to format dates and numbers realistically.
  - **Zero Leakage Rule**: Validates that no label fields (`doc_type`, `expected_decision`, `expected_requests`, `period_start`, etc.) are written into `data/packets/<packet_id>.json`.

---

### 3.5 `intake/generator/templates.py` & `intake/generator/noise.py` (Content & Noise Engine)
- **`templates.py`**:
  - Contains plain-text layouts for Indian Banking documents:
    - Passports, PAN Cards, Voter IDs.
    - Utility Bills (Electricity, Water, Piped Gas).
    - Salary slips with Indian company headers.
    - Bank statements with transaction summaries.
    - ITR-V acknowledgement forms and GST registration certificates.
    - Property sale deeds.
- **`noise.py`**:
  - Randomly formats dates across `DD/MM/YYYY`, `D-Mon-YY`, `Month DD, YYYY`, and `YYYY-MM-DD`.
  - Formats monetary values with Indian notation (`Rs. 5,00,000`, `5 Lakh INR`, `500000`).
  - Generates realistic unhelpful scanner filenames (`scan_0042.txt`, `upload_doc1.txt`).
  - Generates corrupted/unreadable OCR strings for `HUMAN_REVIEW` test cases.

