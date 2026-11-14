# Implementation Plan: 3. Remaining Intake Tools

## 1. Goal
Implement the three remaining typed tools required by the intake agent in `intake/llm/tools/`:
1. `list_documents` — Enumerates documents in a packet.
2. `classify_document` — Classifies document type and calculates confidence score.
3. `extract_fields` — Extracts form and document fields with confidence scores derived from documented textual signals.
4. `registry.py` — Central dispatcher allowing the agent loop to execute tools by name with Pydantic argument validation.

---

## 2. Tool Specifications

### 2.1 `list_documents`
- **Purpose**: Lists document IDs and filenames from a given packet.
- **Input Schema (`ListDocumentsInput`)**:
  - `packet`: `Packet` or `documents`: `List[RawDocument]`
- **Output Schema (`ListDocumentsOutput`)**:
  - `documents`: `List[{"doc_id": str, "filename": str}]`
  - `count`: `int`

---

### 2.2 `classify_document`
- **Purpose**: Determines document type using rule-based keyword & pattern heuristics.
- **Input Schema (`ClassifyDocumentInput`)**:
  - `doc_id`: `str`
  - `text`: `str`
- **Classification Categories**:
  - `ID_PROOF`: Keywords like "PASSPORT", "VOTER ID", "DRIVING LICENCE", "NATIONAL ID", "PERMANENT ACCOUNT NUMBER", "PAN"
  - `ADDRESS_PROOF`: Keywords like "UTILITY", "ELECTRICITY", "BILL", "CONSUMER", "WATER", "IGL", "BESCOM"
  - `SALARY_SLIP`: Keywords like "SALARY", "PAYSLIP", "PAY PERIOD", "BASIC SALARY", "HRA", "DISBURSED"
  - `BANK_STATEMENT`: Keywords like "BANK", "STATEMENT", "SAVINGS ACCOUNT", "CREDITS", "DEBITS", "BALANCE"
  - `ITR`: Keywords like "INCOME TAX", "ITR", "ASSESSMENT YEAR", "ACKNOWLEDGEMENT"
  - `BUSINESS_PROOF`: Keywords like "GST", "GSTIN", "REGISTRATION CERTIFICATE", "TRADE NAME"
  - `PROPERTY_DOC`: Keywords like "SALE DEED", "TITLE CONVEYANCE", "PROPERTY DESCRIPTION", "REGISTRATION NUMBER"
  - `UNREADABLE`: Keywords like "ERROR CODE", "OCR FAILED", "RESOLUTION", "GLARE", "CORRUPTION", "ILLEGIBLE"
- **Confidence Computation**:
  - High confidence ($\ge 0.90$) when primary keywords are found with clean structure.
  - Low confidence ($< 0.80$) or `UNREADABLE` (confidence $< 0.50$) when corruption signals appear or keyword frequency is sparse.
- **Output Schema (`ClassifyDocumentOutput`)**:
  - `doc_id`: `str`
  - `doc_type`: `str`
  - `confidence`: `float`
  - `matched_keywords`: `List[str]`

---

### 2.3 `extract_fields`
- **Purpose**: Extracts structured values from application forms and documents with concrete confidence metrics.
- **Input Schema (`ExtractFieldsInput`)**:
  - `text`: `str`
  - `target`: `Literal["form", "document"]`
  - `doc_type`: `Optional[str]`
- **Extracted Fields & Normalization**:
  - **Form Fields**:
    - `applicant_name`: normalized whitespace/title case.
    - `product`: `personal_loan` | `home_loan`.
    - `employment_type`: `salaried` | `self_employed`.
    - `loan_amount`: integer INR (normalized from e.g. "Rs. 7.5 Lakh" $\rightarrow$ `750000`, "5,00,000" $\rightarrow$ `500000`).
    - `tenure_months`: integer (e.g. "36 months" $\rightarrow$ `36`).
    - `application_date`: ISO string (`YYYY-MM-DD`).
  - **Document Period Fields**:
    - `pay_month`: ISO string (`YYYY-MM`).
    - `period_start` / `period_end`: ISO string (`YYYY-MM-DD`).
    - `assessment_year`: normalized string (e.g. `2025-26`).
    - `issue_date`: ISO string (`YYYY-MM-DD`).
    - `expiry_date`: ISO string (`YYYY-MM-DD`).
- **Confidence Formula (Documented Heuristics)**:
  - Base score: $1.0$.
  - Field missing or null: Confidence $= 0.0$.
  - Ambiguous / fuzzy phrases (e.g., "between forty to fifty lakhs", "flexible", "illegible"): Confidence $= 0.30$.
  - Date ambiguous or partially parsed: Confidence $= 0.65$.
  - Clean regex match on standard key-value pattern: Confidence $= 0.95$.
- **Output Schema (`ExtractFieldsOutput`)**:
  - `fields`: `Dict[str, FieldExtractionResult]`
    - `value`: `Any`
    - `confidence`: `float` (0.0 to 1.0)
    - `source_text`: `Optional[str]`

---

### 2.4 `registry.py`
- Central tool registry mapping tool names (`list_documents`, `classify_document`, `extract_fields`, `check_completeness`) to their executable functions and argument schemas.

---

## 3. Implementation Steps & Tests
1. Create `intake/llm/tools/list_documents.py`.
2. Create `intake/llm/tools/classify_document.py`.
3. Create `intake/llm/tools/extract_fields.py`.
4. Create `intake/llm/tools/registry.py`.
5. Create `tests/test_tools.py` covering:
   - `list_documents` with real packet.
   - `classify_document` across all document types and unreadable text.
   - `extract_fields` form extraction (currency normalization, date normalization, low-confidence handling for ambiguous values).
   - `extract_fields` document extraction (period parsing and confidence).

