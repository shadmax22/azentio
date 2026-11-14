# Implementation Plan: 6. Task 2 — Decision & Extraction Evaluation with Error Analysis

## 1. Goal
Implement the evaluation and error analysis suite (30% of project marks):
```bash
python -m intake.eval --data data/ --provider fake --out reports/
```
Measures the intake agent's decision accuracy, false-complete rate, document-request precision/recall/F1, extraction accuracy, threshold trade-offs, and fault tolerance.

---

## 2. Metrics Specification (from PDF Pages 3 & 4)

1. **Decision Accuracy & 3x3 Confusion Matrix**:
   - Classes: `COMPLETE`, `REQUEST_DOCUMENTS`, `HUMAN_REVIEW`.
   - 3x3 matrix showing Ground Truth vs Predicted.
2. **False-Complete Rate (Critical BFSI Metric)**:
   $$\text{False-Complete Rate} = \frac{\text{Packets truly incomplete or needing review, but predicted as COMPLETE}}{\text{Total truly incomplete or review-needing packets}}$$
   *Must be maintained at 0% or strictly penalized.*
3. **Document-Request Precision, Recall, and F1**:
   - Evaluated at the `(requirement_id, reason_code)` tuple level.
4. **Document-Type Classification Accuracy**:
   - Percentage of document types classified correctly against ground truth.
5. **Per-Field Extraction Accuracy**:
   - Compares predicted fields vs true fields after normalization:
     - `applicant_name`: normalized case and whitespace.
     - `loan_amount`: integer INR.
     - `tenure_months`: integer.
     - `application_date`: ISO format.
6. **Efficiency & Operational Metrics**:
   - `review_rate`: percentage of packets routed to human review.
   - `steps`: `mean_steps` and `max_steps` per packet.
   - `overrides`: total count of guardrail overrides.
7. **Confidence Threshold Sweep**:
   - Evaluates thresholds at: `[0.5, 0.6, 0.7, 0.8, 0.9]`.
   - Records `review_rate` and `false_complete_rate` for each.
   - Sets the optimal default threshold (lowest threshold achieving 0% false-complete).
8. **Robustness Run (`--fault-rate 0.2`)**:
   - Injects random faults on 20% of FakeProvider calls using a fixed seed.
   - Compares clean run metrics vs fault run metrics side-by-side.

---

## 3. Deliverables & File Structure

```text
azentio/
├── intake/
│   └── eval.py                     # Main evaluation script: python -m intake.eval
│
├── reports/
│   ├── eval.json                   # Machine-readable evaluation report
│   ├── eval.md                     # Human-readable markdown evaluation report
│   └── baseline.json               # Committed regression baseline
│
└── tests/
    └── test_eval_regression.py     # Regression gate test asserting against baseline
```

### Required Keys in `reports/eval.json`:
- `decision_accuracy`
- `confusion_matrix`
- `request_prf` (`precision`, `recall`, `f1`)
- `doc_type_accuracy`
- `field_accuracy`
- `false_complete_rate`
- `review_rate`
- `steps` (`mean`, `max`)
- `overrides`
- `threshold_sweep`
- `fault_run`

---

## 4. Execution Steps
1. Create feature branch `feature/task-2-evaluation`.
2. Implement `intake/eval.py`.
3. Run evaluation to produce `reports/eval.json` and `reports/eval.md`.
4. Create committed baseline `reports/baseline.json`.
5. Implement regression gate test `tests/test_eval_regression.py`.
6. Run `pytest` to verify offline execution in < 60 seconds.
7. Merge feature branch into `main`.
