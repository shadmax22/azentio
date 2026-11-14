# Implementation Plan: 1. Synthetic Packet & Labels Generator (`intake.generate`)

## 1. Goal
Implement the data generation CLI module:
```bash
python -m intake.generate --packets 40 --seed 7 --out data/
```
This command programmatically generates:
1. `data/packets/<packet_id>.json` — Individual packet files containing only unstructured raw text and metadata.
2. `data/labels.jsonl` — The ground-truth answer key, used exclusively by evaluation and unit tests.

---

## 2. File Schemas

### 2.1 Packet File Schema (`data/packets/<packet_id>.json`)
Each packet file contains **only raw text** that simulates OCR dumps or scanned text files. **Zero ground-truth fields** (no `doc_type`, no `expected_decision`) are allowed in this file.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "LoanApplicationPacket",
  "type": "object",
  "required": ["packet_id", "as_of", "application_form", "documents"],
  "properties": {
    "packet_id": {
      "type": "string",
      "description": "Unique identifier, e.g. 'pkt_001'"
    },
    "as_of": {
      "type": "string",
      "format": "date",
      "description": "Fixed baseline date for relative time calculations, e.g. '2026-03-15'"
    },
    "application_form": {
      "type": "string",
      "description": "Free text containing applicant details and requested loan terms"
    },
    "documents": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["doc_id", "filename", "text"],
        "properties": {
          "doc_id": { "type": "string", "description": "e.g. 'doc_01'" },
          "filename": { "type": "string", "description": "e.g. 'scan_0042.txt' or 'salary_feb.txt'" },
          "text": { "type": "string", "description": "Simulated raw OCR/text dump with noise" }
        }
      }
    }
  }
}
```

#### Example 1: Incomplete Packet (`pkt_001.json`) — Matches Sample 1 Label
*(Notice: Free text with realistic noise, Indian rupee notations, mixed date formats, and zero ground-truth keys)*

```json
{
  "packet_id": "pkt_001",
  "as_of": "2026-03-15",
  "application_form": "==============================================\n        RETAIL LOAN APPLICATION FORM\n==============================================\nApplicant Full Name : Rahul Kumar Verma\nProduct Requested   : personal_loan\nEmployment Type     : salaried\nLoan Amount (INR)   : Rs. 6,50,000 (Six Lakh Fifty Thousand)\nRepayment Tenure    : 36 months\nApplication Date    : 10/03/2026\nMonthly In-Hand Net : Rs. 75,000\n----------------------------------------------\nDeclaration: I hereby declare that all details\ngiven above are true and complete.\n==============================================",
  "documents": [
    {
      "doc_id": "doc_01",
      "filename": "scan_0012.txt",
      "text": "REPUBLIC OF INDIA - PASSPORT OFFICE\n--------------------------------------------\nDocument: PASSPORT\nGiven Names: Rahul Kumar Verma\nNationality: INDIAN | Sex: M\nDate of Birth: 12-08-1992\nPlace of Issue: Delhi\nDate of Expiry: 14-Aug-2032\nPassport Number: Z9283719\n============================================"
    },
    {
      "doc_id": "doc_02",
      "filename": "bill_old_scan.txt",
      "text": "TATA POWER DELHI DISTRIBUTION LIMITED\nELECTRICITY CONSUMER BILL\nConsumer Name: Rahul Kumar Verma\nCA Number: 6001928371\nBill Issue Date: 05/10/2025\nDue Date: 20/10/2025\nUnits Consumed: 240 kWh\nTotal Payable: Rs. 1,840\n*** Please save electricity - Switch off appliances ***"
    },
    {
      "doc_id": "doc_03",
      "filename": "salary_feb.txt",
      "text": "INFOSYS TECHNOLOGIES PRIVATE LIMITED\nSALARY SLIP FOR MONTH: FEBRUARY 2026\n--------------------------------------------\nEmployee: Rahul Kumar Verma | Emp ID: INF7712\nPay Date: 28-Feb-2026\nBasic Salary: Rs. 45,000\nHRA: Rs. 20,000\nSpecial Allowance: Rs. 15,000\nTotal Deductions: Rs. 5,000\nNET DISBURSED: Rs. 75,000 (Seventy Five Thousand)"
    },
    {
      "doc_id": "doc_04",
      "filename": "salary_jan.txt",
      "text": "INFOSYS TECHNOLOGIES PRIVATE LIMITED\nSALARY SLIP FOR MONTH: JANUARY 2026\n--------------------------------------------\nEmployee: Rahul Kumar Verma | Emp ID: INF7712\nPay Date: 31-Jan-2026\nNET DISBURSED: Rs. 75,000"
    },
    {
      "doc_id": "doc_05",
      "filename": "bank_stmt_6m.txt",
      "text": "HDFC BANK LIMITED - ACCOUNT STATEMENT\nAccount Holder: Rahul Kumar Verma\nAccount Number: 50100293847192\nStatement Period: 01/09/2025 to 28/02/2026\nOpening Balance: Rs. 42,100.50\nClosing Balance: Rs. 89,320.00\n--- Transaction Summary Included ---"
    }
  ]
}
```

#### Example 2: Complete Packet (`pkt_002.json`) — Matches Sample 2 Label
*(All required documents present: ID valid, fresh Address Proof, 3 full Salary Slips, 6 months Bank Statement)*

```json
{
  "packet_id": "pkt_002",
  "as_of": "2026-03-15",
  "application_form": "APPLICATION FOR PERSONAL CREDIT\nName: Pooja Natarajan\nApplied Product: personal_loan\nEmployment: salaried\nAmount: 4 Lakh INR\nTenure: 24 Months\nDate: 05-Mar-2026",
  "documents": [
    {
      "doc_id": "doc_01",
      "filename": "pan_card.txt",
      "text": "INCOME TAX DEPARTMENT - GOVT OF INDIA\nPermanent Account Number Card\nName: Pooja Natarajan\nPAN: ABCPN1234K\nValid Till: 20-Nov-2030"
    },
    {
      "doc_id": "doc_02",
      "filename": "utility_bill.txt",
      "text": "BANGALORE ELECTRICITY SUPPLY CO (BESCOM)\nBill Date: 15/02/2026\nConsumer: Pooja Natarajan\nAmount: Rs. 1,420"
    },
    {
      "doc_id": "doc_03",
      "filename": "slip_feb26.txt",
      "text": "WIPRO LTD - SALARY VOUCHER\nPeriod: February 2026\nName: Pooja Natarajan\nNet Pay: Rs. 55,000"
    },
    {
      "doc_id": "doc_04",
      "filename": "slip_jan26.txt",
      "text": "WIPRO LTD - SALARY VOUCHER\nPeriod: January 2026\nName: Pooja Natarajan\nNet Pay: Rs. 55,000"
    },
    {
      "doc_id": "doc_05",
      "filename": "slip_dec25.txt",
      "text": "WIPRO LTD - SALARY VOUCHER\nPeriod: December 2025\nName: Pooja Natarajan\nNet Pay: Rs. 55,000"
    },
    {
      "doc_id": "doc_06",
      "filename": "icici_statement.txt",
      "text": "ICICI BANK ACCOUNT STATEMENT\nCustomer: Pooja Natarajan\nStatement From: 2025-09-01 To: 2026-02-28\nTransactions: Salary credits verified"
    }
  ]
}
```

#### Example 3: Messy / Unreadable Packet (`pkt_003.json`) — Matches Sample 3 Label
*(Contains garbled/corrupted OCR text and ambiguous loan amount in form)*

```json
{
  "packet_id": "pkt_003",
  "as_of": "2026-03-15",
  "application_form": "BORROWER REGISTRATION\nName: Venkatesh Iyer\nProduct: home_loan\nEmployment: self_employed\nRequired Loan Amount: somewhere around fifty or sixty lakhs maybe\nTenure: 180 months\nDate: 01/03/2026",
  "documents": [
    {
      "doc_id": "doc_01",
      "filename": "passport_scan.txt",
      "text": "PASSPORT OF INDIA\nName: Venkatesh Iyer\nExpiry: 12-Jun-2029"
    },
    {
      "doc_id": "doc_02",
      "filename": "scan_unreadable_09.txt",
      "text": "###%% ERROR: OCR FAILED TO READ IMAGE %%%###\n~~?? garbled characters ^^^ 102938472910 ~~\n--- corrupted optical scan resolution 48dpi ---"
    }
  ]
}
```

---

### 2.2 Ground Truth Labels Schema (`data/labels.jsonl`)
Stored as one JSON object per line in `data/labels.jsonl`. Represents the absolute ground truth.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "PacketGroundTruthLabel",
  "type": "object",
  "required": [
    "packet_id",
    "expected_decision",
    "expected_requests",
    "form_fields",
    "documents"
  ],
  "properties": {
    "packet_id": { "type": "string" },
    "expected_decision": {
      "type": "string",
      "enum": ["COMPLETE", "REQUEST_DOCUMENTS", "HUMAN_REVIEW"]
    },
    "expected_requests": {
      "type": "array",
      "description": "Empty if decision is COMPLETE or HUMAN_REVIEW",
      "items": {
        "type": "object",
        "required": ["requirement_id", "reason_code"],
        "properties": {
          "requirement_id": {
            "type": "string",
            "enum": [
              "ID_PROOF",
              "ADDRESS_PROOF",
              "SALARY_SLIPS_3M",
              "BANK_STMT_6M",
              "ITR_2Y",
              "BANK_STMT_12M",
              "BUSINESS_PROOF",
              "PROPERTY_DOC"
            ]
          },
          "reason_code": {
            "type": "string",
            "enum": ["MISSING", "INCOMPLETE_COVERAGE", "STALE", "EXPIRED"]
          }
        }
      }
    },
    "form_fields": {
      "type": "object",
      "required": [
        "applicant_name",
        "product",
        "employment_type",
        "loan_amount",
        "tenure_months",
        "application_date"
      ],
      "properties": {
        "applicant_name": { "type": ["string", "null"] },
        "product": { "type": ["string", "null"], "enum": ["personal_loan", "home_loan", null] },
        "employment_type": { "type": ["string", "null"], "enum": ["salaried", "self_employed", null] },
        "loan_amount": { "type": ["integer", "null"] },
        "tenure_months": { "type": ["integer", "null"] },
        "application_date": { "type": ["string", "null"], "format": "date" }
      }
    },
    "documents": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["doc_id", "doc_type"],
        "properties": {
          "doc_id": { "type": "string" },
          "doc_type": {
            "type": "string",
            "enum": [
              "ID_PROOF",
              "ADDRESS_PROOF",
              "SALARY_SLIP",
              "BANK_STATEMENT",
              "ITR",
              "BUSINESS_PROOF",
              "PROPERTY_DOC",
              "UNREADABLE"
            ]
          },
          "pay_month": { "type": ["string", "null"], "description": "YYYY-MM" },
          "period_start": { "type": ["string", "null"], "format": "date" },
          "period_end": { "type": ["string", "null"], "format": "date" },
          "assessment_year": { "type": ["string", "null"], "description": "e.g. '2025-26'" },
          "issue_date": { "type": ["string", "null"], "format": "date" },
          "expiry_date": { "type": ["string", "null"], "format": "date" }
        }
      }
    }
  }
}
```

#### Concrete Samples for `data/labels.jsonl`:
*(Formatted with indentation for readability below. In the actual `labels.jsonl` file, each record is serialized as a single line)*

**Sample 1: Incomplete Packet (`REQUEST_DOCUMENTS`)**
*(Address proof is 150 days old [STALE] and only 2 months of salary slips are provided [INCOMPLETE_COVERAGE])*

```json
{
  "packet_id": "pkt_001",
  "expected_decision": "REQUEST_DOCUMENTS",
  "expected_requests": [
    {
      "requirement_id": "ADDRESS_PROOF",
      "reason_code": "STALE"
    },
    {
      "requirement_id": "SALARY_SLIPS_3M",
      "reason_code": "INCOMPLETE_COVERAGE"
    }
  ],
  "form_fields": {
    "applicant_name": "Rahul Kumar Verma",
    "product": "personal_loan",
    "employment_type": "salaried",
    "loan_amount": 650000,
    "tenure_months": 36,
    "application_date": "2026-03-10"
  },
  "documents": [
    {
      "doc_id": "doc_01",
      "doc_type": "ID_PROOF",
      "pay_month": null,
      "period_start": null,
      "period_end": null,
      "assessment_year": null,
      "issue_date": null,
      "expiry_date": "2032-08-14"
    },
    {
      "doc_id": "doc_02",
      "doc_type": "ADDRESS_PROOF",
      "pay_month": null,
      "period_start": null,
      "period_end": null,
      "assessment_year": null,
      "issue_date": "2025-10-05",
      "expiry_date": null
    },
    {
      "doc_id": "doc_03",
      "doc_type": "SALARY_SLIP",
      "pay_month": "2026-02",
      "period_start": null,
      "period_end": null,
      "assessment_year": null,
      "issue_date": null,
      "expiry_date": null
    },
    {
      "doc_id": "doc_04",
      "doc_type": "SALARY_SLIP",
      "pay_month": "2026-01",
      "period_start": null,
      "period_end": null,
      "assessment_year": null,
      "issue_date": null,
      "expiry_date": null
    },
    {
      "doc_id": "doc_05",
      "doc_type": "BANK_STATEMENT",
      "pay_month": null,
      "period_start": "2025-09-01",
      "period_end": "2026-02-28",
      "assessment_year": null,
      "issue_date": null,
      "expiry_date": null
    }
  ]
}
```

**Sample 2: Perfect Packet (`COMPLETE`)**
*(Salaried personal loan with valid ID, fresh address proof, 3 full salary slips, and 6 full months of bank statements)*

```json
{
  "packet_id": "pkt_002",
  "expected_decision": "COMPLETE",
  "expected_requests": [],
  "form_fields": {
    "applicant_name": "Pooja Natarajan",
    "product": "personal_loan",
    "employment_type": "salaried",
    "loan_amount": 400000,
    "tenure_months": 24,
    "application_date": "2026-03-05"
  },
  "documents": [
    {
      "doc_id": "doc_01",
      "doc_type": "ID_PROOF",
      "pay_month": null,
      "period_start": null,
      "period_end": null,
      "assessment_year": null,
      "issue_date": null,
      "expiry_date": "2030-11-20"
    },
    {
      "doc_id": "doc_02",
      "doc_type": "ADDRESS_PROOF",
      "pay_month": null,
      "period_start": null,
      "period_end": null,
      "assessment_year": null,
      "issue_date": "2026-02-15",
      "expiry_date": null
    },
    {
      "doc_id": "doc_03",
      "doc_type": "SALARY_SLIP",
      "pay_month": "2026-02",
      "period_start": null,
      "period_end": null,
      "assessment_year": null,
      "issue_date": null,
      "expiry_date": null
    },
    {
      "doc_id": "doc_04",
      "doc_type": "SALARY_SLIP",
      "pay_month": "2026-01",
      "period_start": null,
      "period_end": null,
      "assessment_year": null,
      "issue_date": null,
      "expiry_date": null
    },
    {
      "doc_id": "doc_05",
      "doc_type": "SALARY_SLIP",
      "pay_month": "2025-12",
      "period_start": null,
      "period_end": null,
      "assessment_year": null,
      "issue_date": null,
      "expiry_date": null
    },
    {
      "doc_id": "doc_06",
      "doc_type": "BANK_STATEMENT",
      "pay_month": null,
      "period_start": "2025-09-01",
      "period_end": "2026-02-28",
      "assessment_year": null,
      "issue_date": null,
      "expiry_date": null
    }
  ]
}
```

**Sample 3: Low-Confidence / Blurry Packet (`HUMAN_REVIEW`)**
*(Scan is unreadable/corrupt and form loan amount is ambiguous; expected_requests is strictly empty)*

```json
{
  "packet_id": "pkt_003",
  "expected_decision": "HUMAN_REVIEW",
  "expected_requests": [],
  "form_fields": {
    "applicant_name": "Venkatesh Iyer",
    "product": "home_loan",
    "employment_type": "self_employed",
    "loan_amount": null,
    "tenure_months": 180,
    "application_date": "2026-03-01"
  },
  "documents": [
    {
      "doc_id": "doc_01",
      "doc_type": "ID_PROOF",
      "pay_month": null,
      "period_start": null,
      "period_end": null,
      "assessment_year": null,
      "issue_date": null,
      "expiry_date": "2029-06-12"
    },
    {
      "doc_id": "doc_02",
      "doc_type": "UNREADABLE",
      "pay_month": null,
      "period_start": null,
      "period_end": null,
      "assessment_year": null,
      "issue_date": null,
      "expiry_date": null
    }
  ]
}
```

---

## 3. Dataset Distribution Requirements (40 Packets)

To satisfy the project requirements:
1. **$\ge 40\%$ (at least 16 packets) `REQUEST_DOCUMENTS`**:
   - Must cover all 4 reason codes:
     - `MISSING`: A required document is completely absent (e.g. Home loan without Property Doc).
     - `INCOMPLETE_COVERAGE`: Partial period covered (e.g. only 2 of 3 salary slips, or 4 of 6 months bank statement).
     - `STALE`: Address proof issued $> 90$ days prior to `as_of`.
     - `EXPIRED`: ID proof expired before `as_of`.
2. **$\ge 15\%$ (at least 6 packets) `HUMAN_REVIEW`**:
   - Unreadable/corrupted OCR document text (`"###%% CORRUPT SCAN UNREADABLE ..."`).
   - Ambiguous form value (e.g., loan amount is written as `"5 or 10 lakhs maybe"`, or missing applicant name).
   - **Important**: For all `HUMAN_REVIEW` cases, `expected_requests` **must be empty `[]`**.
3. **$\approx 45\%$ (around 18 packets) `COMPLETE`**:
   - All checklist documents present, within valid timeframes, and clear.

---

## 4. Realistic Text Noise & Rendering Rules

The generator must inject realistic variations:
1. **Date Formatting Variations**:
   - `YYYY-MM-DD` (e.g. `2026-03-10`)
   - `DD/MM/YYYY` (e.g. `10/03/2026`)
   - `D-Mon-YY` or `D-Mon-YYYY` (e.g. `10-Mar-26`, `10-March-2026`)
   - `Month DD, YYYY` (e.g. `March 10, 2026`)
2. **Indian Amount Formatting Variations**:
   - `Rs. 5,00,000`
   - `5 Lakh` / `5.5 Lakhs`
   - `INR 500000`
   - `500,000.00`
3. **Filenames**:
   - Mix of generic scanner names (`scan_0042.txt`, `IMG_20260301_001.txt`) and descriptive names (`salary_slip_jan.txt`, `aadhaar_front.txt`).
4. **Header/Footer Noise**:
   - Page numbers: `Page 1 of 3`
   - Watermarks / Disclaimer footers: `*** Confidential Banking Record ***`, `Computer Generated - No Signature Required`.

---

## 5. Implementation Steps & File Architecture

### 5.1 Modular File Structure
The generation module is organized cleanly under `intake/`:

```text
intake/
├── __init__.py
├── generate.py                     # Main CLI entrypoint (python -m intake.generate)
├── schemas.py                      # Pydantic schemas for Packets and Labels
│
├── docs/                           # Internal package documentation
│   └── architecture.md             # How these files work together & component contracts
│
└── generator/                      # Generation subpackage
    ├── __init__.py
    ├── scenarios.py                # Scenario recipes & quota distribution (40% req docs, 15% review)
    ├── generate_labels.py          # Ground truth generator (outputs data for labels.jsonl)
    ├── generate_packets.py         # Packet text renderer (converts ground truth into noisy text)
    ├── templates.py                # Document & form text templates (Passport, Bills, Salary slips, etc.)
    └── noise.py                    # Noise generators (Indian currency formatting, mixed dates, scan names)
```

### 5.2 Flow & Component Responsibilities
1. **`intake/generate.py` (CLI & Conductor)**:
   - Parses arguments `--packets 40 --seed 7 --out data/`.
   - Sets `random.seed(seed)`.
   - Calls `scenarios.build_scenario_bucket(packets)`.
   - For each packet:
     - Calls `generate_labels.create_label(...)` $\rightarrow$ appends to `<out>/labels.jsonl`.
     - Calls `generate_packets.render_packet(...)` $\rightarrow$ saves to `<out>/packets/<packet_id>.json`.

2. **`intake/generator/scenarios.py` (Distribution & Quotas)**:
   - Builds deterministic recipe buckets:
     - 18 $\times$ `COMPLETE`
     - 16 $\times$ `REQUEST_DOCUMENTS` (4 $\times$ `MISSING`, 4 $\times$ `INCOMPLETE_COVERAGE`, 4 $\times$ `STALE`, 4 $\times$ `EXPIRED`)
     - 6 $\times$ `HUMAN_REVIEW` (3 $\times$ `UNREADABLE_DOC`, 3 $\times$ `AMBIGUOUS_FORM`)
   - Shuffles deterministically using the seeded RNG.

3. **`intake/generator/generate_labels.py` (Answer Key Builder)**:
   - Generates the clean ground-truth Python dictionary.
   - Populates `packet_id`, `expected_decision`, `expected_requests`, `form_fields`, and `documents` (with exact dates, doc types, and period fields).

4. **`intake/generator/generate_packets.py` (Raw Noisy Text Renderer)**:
   - Uses `templates.py` and `noise.py` to turn structured fields into realistic, unstructured text files.
   - Strips away all ground-truth labels so packets contain **only** `doc_id`, `filename`, and `text`.

5. **`intake/generator/templates.py` & `noise.py`**:
   - Realistic text templates (Passport, Utility Bills, Salary Slips, Bank Statements, ITR, GST Certificates).
   - Random noise injectors (Indian currency formatting e.g. `Rs. 5,00,000` / `5 Lakh`, mixed date formats e.g. `05/03/2026` / `5-Mar-26`, generic filenames like `scan_0042.txt`).

---

## 6. Verification & Done Means Checklist
1. **Reproducibility Test (`tests/test_generator.py`)**:
   - Run generator twice with `--seed 7` into two different directories.
   - Assert all files are **byte-for-byte identical**.
2. **Leakage Test**:
   - Scan all JSON files in `data/packets/` and assert none contain keys `doc_type`, `expected_decision`, `expected_requests`.
3. **Distribution Assertion**:
   - Read `data/labels.jsonl`.
   - Assert $\ge 40\%$ have `expected_decision == "REQUEST_DOCUMENTS"` and all 4 reason codes appear.
   - Assert $\ge 15\%$ have `expected_decision == "HUMAN_REVIEW"` and their `expected_requests == []`.

