# Implementation Plan: 2. Checklist Configuration (`config/checklist.yaml`)

## 1. Goal
Define and implement the bank policy rulebook in `config/checklist.yaml`, along with a strongly typed Pydantic loader in `intake/checklist.py`.

The checklist config specifies exactly which documents are mandatory for each loan product and employment category, the exact validity rules, and customer-friendly `borrower_label`s for document request messages.

---

## 2. Bank Policy Specification (from PDF Page 2)

Keyed by `product` (`personal_loan`, `home_loan`) and `employment_type` (`salaried`, `self_employed`):

| Product | Employment | Mandatory Requirements |
| :--- | :--- | :--- |
| **All Packets** | **All Categories** | • **`ID_PROOF`**: Must not be expired on `as_of`<br>• **`ADDRESS_PROOF`**: Issued at most 90 days before `as_of` |
| **Any Product** | **Salaried** | • **`SALARY_SLIPS_3M`**: One slip for each of the 3 calendar months before application month<br>• **`BANK_STMT_6M`**: Statements that together cover the 6 full calendar months before application month |
| **Any Product** | **Self-Employed** | • **`ITR_2Y`**: The two latest assessment years<br>• **`BANK_STMT_12M`**: Statements that together cover the 12 full calendar months before application month<br>• **`BUSINESS_PROOF`**: GST registration certificate |
| **Home Loan** | **Any Category** | • Adds **`PROPERTY_DOC`**: Registered sale deed or title document |

### Status Codes for Each Requirement:
- `SATISFIED`: Valid, unexpired, and full coverage.
- Request Reason Codes:
  - `MISSING`: Document was not provided.
  - `INCOMPLETE_COVERAGE`: Partial period covered (e.g., only 2 months of slips or 4 months of bank statement).
  - `STALE`: Address proof issue date $> 90$ days before `as_of`.
  - `EXPIRED`: ID proof expiry date $< as\_of$.
- Review Code:
  - `UNREADABLE`: Candidate document exists but is corrupted, unclassifiable, or below confidence threshold (routes to `HUMAN_REVIEW`, never to borrower request).

---

## 3. YAML Schema Design (`config/checklist.yaml`)

```yaml
version: "1.0"

requirements:
  ID_PROOF:
    borrower_label: "Government-issued Photo ID (Passport, PAN, Voter ID, or Driving License)"
    rule_type: "not_expired"

  ADDRESS_PROOF:
    borrower_label: "Recent utility bill or address proof issued within last 90 days"
    rule_type: "max_age_days"
    max_days: 90

  SALARY_SLIPS_3M:
    borrower_label: "Salary slips for the 3 calendar months prior to application"
    rule_type: "prior_calendar_months"
    months_count: 3

  BANK_STMT_6M:
    borrower_label: "Bank statements covering the 6 full calendar months prior to application"
    rule_type: "continuous_coverage_months"
    months_count: 6

  ITR_2Y:
    borrower_label: "Income Tax Return (ITR-V) acknowledgements for the 2 latest assessment years"
    rule_type: "latest_assessment_years"
    years_count: 2

  BANK_STMT_12M:
    borrower_label: "Bank statements covering the 12 full calendar months prior to application"
    rule_type: "continuous_coverage_months"
    months_count: 12

  BUSINESS_PROOF:
    borrower_label: "GST registration certificate or registered business proof"
    rule_type: "document_exists"

  PROPERTY_DOC:
    borrower_label: "Registered property sale agreement or title deed"
    rule_type: "document_exists"

products:
  personal_loan:
    salaried:
      - ID_PROOF
      - ADDRESS_PROOF
      - SALARY_SLIPS_3M
      - BANK_STMT_6M

    self_employed:
      - ID_PROOF
      - ADDRESS_PROOF
      - ITR_2Y
      - BANK_STMT_12M
      - BUSINESS_PROOF

  home_loan:
    salaried:
      - ID_PROOF
      - ADDRESS_PROOF
      - SALARY_SLIPS_3M
      - BANK_STMT_6M
      - PROPERTY_DOC

    self_employed:
      - ID_PROOF
      - ADDRESS_PROOF
      - ITR_2Y
      - BANK_STMT_12M
      - BUSINESS_PROOF
      - PROPERTY_DOC
```

---

## 4. Architecture & Tool Location: `intake/llm/tools/`

The verification engine lives inside `intake/llm/tools/`:

```text
intake/
├── llm/
│   └── tools/
│       ├── __init__.py
│       └── check_completeness.py   # Pure deterministic checklist verification tool
```

### 4.1 Tool Contract & Schemas (`check_completeness`)
- **Pydantic Input Schema (`CheckCompletenessInput`)**:
  - `product`: `personal_loan` | `home_loan`
  - `employment_type`: `salaried` | `self_employed`
  - `as_of`: `YYYY-MM-DD` (baseline fixed date)
  - `application_date`: `YYYY-MM-DD`
  - `documents`: List of extracted document records with fields:
    - `doc_id`: `str`
    - `doc_type`: `str` (`ID_PROOF`, `ADDRESS_PROOF`, `SALARY_SLIP`, `BANK_STATEMENT`, `ITR`, `BUSINESS_PROOF`, `PROPERTY_DOC`, `UNREADABLE`)
    - `expiry_date`: `Optional[str]`
    - `issue_date`: `Optional[str]`
    - `pay_month`: `Optional[str]`
    - `period_start`: `Optional[str]`
    - `period_end`: `Optional[str]`
    - `assessment_year`: `Optional[str]`
    - `confidence`: `float` (0.0 to 1.0)

- **JSON-Serializable Output Schema (`CheckCompletenessOutput`)**:
  - `all_satisfied`: `bool`
  - `has_unreadable`: `bool`
  - `requirements`: `Dict[str, RequirementResult]`
    - `status`: `SATISFIED` | `MISSING` | `INCOMPLETE_COVERAGE` | `STALE` | `EXPIRED` | `UNREADABLE`
    - `reason_code`: `Optional[str]`
    - `evidence_doc_ids`: `List[str]`
    - `borrower_label`: `str`
  - `unsatisfied`: `List[{"requirement_id": str, "reason_code": str}]`

---

## 5. Mandatory Verification Test Cases (Covered by Unit Tests)

From the project specification (PDF Page 3), unit tests must cover at least:
1. **Complete Salaried Packet**: Valid ID, fresh utility bill ($\le 90$ days), 3 salary slips, 6 months bank statements $\rightarrow$ `SATISFIED`.
2. **Missing Salary Slip Month**: Only 2 salary slips provided $\rightarrow$ `INCOMPLETE_COVERAGE`.
3. **Multi-File Bank Statements**: Bank statements split across two files that together cover 6 full months $\rightarrow$ `SATISFIED`.
4. **Stale Address Proof**: Utility bill issued 120 days ago ($> 90$ days) $\rightarrow$ `STALE`.
5. **Expired ID**: Passport expired prior to `as_of` $\rightarrow$ `EXPIRED`.
6. **Home Loan without Property Document**: Home loan lacking property deed $\rightarrow$ `MISSING`.
7. **Unreadable Scan**: Candidate document marked `UNREADABLE` $\rightarrow$ `UNREADABLE` (routes to human review, not borrower request).

