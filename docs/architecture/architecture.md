# Architecture: How The Intake Files Work Together

See the package internal architecture in [intake/docs/architecture.md](file:///Users/mdali/Documents/azentio/intake/docs/architecture.md).

```text
intake/
├── __init__.py
├── generate.py                     # Main CLI entrypoint (python -m intake.generate)
├── schemas.py                      # Pydantic schemas for Packets and Labels
│
├── docs/                           # Internal package documentation
│   └── architecture.md             # Detailed architecture & contract specification
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

## Component Collaboration Flow

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

