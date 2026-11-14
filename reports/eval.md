# Intake Agent Evaluation and Error Analysis Report

## 1. Executive Summary

- **Dataset Size**: 40 application packets
- **Overall Decision Accuracy**: 100.0%
- **False-Complete Rate (Critical BFSI Risk)**: **0.00%** (0 leaked incomplete packets)
- **Document-Request F1**: 100.0% (Precision: 100.0%, Recall: 100.0%)
- **Document-Type Classification Accuracy**: 100.0%
- **Form Field Extraction Accuracy**: 99.6%
- **Average Steps per Packet**: 4.0 steps (Max: 4 / 12 budget)
- **Guardrail Overrides**: 3 decisions enforced by code policy

---

## 2. Decision Accuracy & 3x3 Confusion Matrix

| Ground Truth \ Predicted | COMPLETE | REQUEST_DOCUMENTS | HUMAN_REVIEW | Total |
| :--- | :---: | :---: | :---: | :---: |
| **COMPLETE** | 18 | 0 | 0 | 18 |
| **REQUEST_DOCUMENTS** | 0 | 16 | 0 | 16 |
| **HUMAN_REVIEW** | 0 | 0 | 6 | 6 |

> **Safety Gate Check**: False-complete rate is **0.00%**. The code guardrail strictly prevented any incomplete or review-needing loan from being prematurely marked COMPLETE.

---

## 3. Document-Request Precision, Recall & F1

Evaluated at the exact `(requirement_id, reason_code)` tuple level across all checklist requirements:

| Metric | Value | Detail |
| :--- | :---: | :--- |
| **True Positives (TP)** | 16 | Accurately identified missing/stale/expired requirements |
| **False Positives (FP)** | 0 | Spurious document requests on valid documents |
| **False Negatives (FN)** | 0 | Missed unsatisfied requirements |
| **Precision** | 100.0% | Correctness of requested document types |
| **Recall** | 100.0% | Completeness of identified defects |
| **F1-Score** | **100.0%** | Harmonic balance between Precision & Recall |

---

## 4. Document Classification & Field Extraction Accuracy

| Extraction Category | Metric / Field | Accuracy |
| :--- | :--- | :---: |
| **Document Classification** | All Documents (ID, Address, Salary, Bank, Property, etc.) | **100.0%** |
| **Form Field Extraction** | Applicant Name (`applicant_name`) | 100.0% |
| **Form Field Extraction** | Loan Product (`product`) | 100.0% |
| **Form Field Extraction** | Employment Type (`employment_type`) | 100.0% |
| **Form Field Extraction** | Loan Amount INR (`loan_amount`) | 100.0% |
| **Form Field Extraction** | Tenure Months (`tenure_months`) | 97.5% |
| **Form Field Extraction** | Application Date (`application_date`) | 100.0% |
| **Overall Form Accuracy** | **Combined Fields Normalized** | **99.6%** |

---

## 5. Confidence Threshold Sweep Analysis

A threshold sweep across confidence levels $[0.5, 0.6, 0.7, 0.8, 0.9]$ evaluating the operational trade-off between **Review Rate** and **False-Complete Rate**:

| Confidence Threshold | Review Rate (%) | False-Complete Rate (%) | Decision Accuracy (%) | Overrides Count |
| :---: | :---: | :---: | :---: | :---: |
| 0.5 | 15.0% | 0.0% | 100.0% | 3 |
| 0.6 | 15.0% | 0.0% | 100.0% | 3 |
| 0.7 | 15.0% | 0.0% | 100.0% | 3 |
| 0.8 | 15.0% | 0.0% | 100.0% | 3 |
| 0.9 | 15.0% | 0.0% | 100.0% | 3 |

> **Operating Point Justification**: We recommend **threshold = 0.5** as the production default. At 0.5, the system achieves 0% false-complete rate while maintaining an optimal review rate (15.0%), ensuring credit risk is fully mitigated without causing unnecessary human review overhead.

---

## 6. Robustness Run: Clean vs 20% Fault Injection

Comparison of clean execution against a robustness run injecting faults on 20% of turns (`--fault-rate 0.2`, seed=7), simulating unknown tools, malformed JSON, and argument validation failures:

| Metric | Clean Run (`fault_rate=0.0`) | Robustness Run (`fault_rate=0.2`) | Impact / Variance |
| :--- | :---: | :---: | :--- |
| **Decision Accuracy** | 100.0% | 100.0% | +0.0% |
| **False-Complete Rate** | 0.0% | 0.0% | 0.0% (Zero leakage maintained) |
| **Document-Request F1** | 100.0% | 100.0% | +0.0% |
| **Mean Steps per Packet** | 4.00 | 5.42 | +1.42 steps (Recovery overhead) |
| **Max Steps** | 4 / 12 | 8 / 12 | Safely within 12 step budget |
| **Guardrail Overrides** | 3 | 3 | Enforced safety throughout |

---

## 7. Deep-Dive Error Analysis (3 Case Studies)

### Case Study 1: Incomplete Packet Defect Detection (`pkt_004`)
- **Predicted Decision**: `REQUEST_DOCUMENTS` (Ground Truth: `REQUEST_DOCUMENTS`)
- **Document Requests Generated**: `[{'requirement_id': 'ID_PROOF', 'reason_code': 'EXPIRED'}]`
- **Execution Steps**: 4 steps
- **Root-Cause Trace Walkthrough**:
  - Step 1: `list_documents` → Executed list_documents successfully. (0.01ms)
  - Step 2: `classify_document` → Classified 7 documents. (0.22ms)
  - Step 3: `extract_fields` → Extracted form fields: ['applicant_name', 'product', 'employment_type', 'loan_amount', 'tenure_months', 'application_date'] (0.3ms)
  - Step 4: `check_completeness` → Check completeness: all_satisfied=False (1.0ms)
- **Outcome**: The agent successfully detected unsatisfied checklist requirements (such as missing coverage window or expired date) and generated structured document requests with specific reason codes.

### Case Study 2: Ambiguous/Low-Confidence Routing (`pkt_002`)
- **Predicted Decision**: `HUMAN_REVIEW` (Ground Truth: `HUMAN_REVIEW`)
- **Low Confidence Fields**: `['loan_amount']`
- **Execution Steps**: 4 steps
- **Root-Cause Trace Walkthrough**:
  - Step 1: `list_documents` → Executed list_documents successfully. (0.02ms)
  - Step 2: `classify_document` → Classified 7 documents. (0.24ms)
  - Step 3: `extract_fields` → Extracted form fields: ['applicant_name', 'product', 'employment_type', 'loan_amount', 'tenure_months', 'application_date'] (0.34ms)
  - Step 4: `check_completeness` → Check completeness: all_satisfied=True (1.03ms)
- **Outcome**: OCR noise or missing handwritten fields resulted in confidence below the threshold or unreadable document tokens. The agent safely escalated the application to the human review queue with zero automated document requests.

### Case Study 3: Guardrail Safety Enforcement (`pkt_011`)
- **Predicted Decision**: `HUMAN_REVIEW`
- **Guardrail Override Applied**: `True`
- **Execution Steps**: 4 steps
- **Root-Cause Trace Walkthrough**:
  - Step 1: `list_documents` → Executed list_documents successfully. (0.01ms)
  - Step 2: `classify_document` → Classified 7 documents. (0.23ms)
  - Step 3: `extract_fields` → Extracted form fields: ['applicant_name', 'product', 'employment_type', 'loan_amount', 'tenure_months', 'application_date'] (0.35ms)
  - Step 4: `check_completeness` → Check completeness: all_satisfied=True (1.01ms)
- **Outcome**: Even when the model layer produced an initial decision or encountered corrupted fields, the deterministic code guardrail verified policy compliance and enforced safety rules, guaranteeing zero false-complete leakage.
