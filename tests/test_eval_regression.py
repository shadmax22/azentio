"""Regression Gate Tests for Intake Agent Evaluation."""

import json
from pathlib import Path
import pytest

from intake.eval import evaluate_dataset, run_threshold_sweep


DATA_DIR = Path("data")
BASELINE_PATH = Path("reports/baseline.json")


@pytest.fixture(scope="module")
def baseline_config():
    """Load baseline performance thresholds."""
    if not BASELINE_PATH.exists():
        pytest.fail(f"Baseline file missing at {BASELINE_PATH}. Run python -m intake.eval first.")
    with open(BASELINE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_evaluation_meets_baseline_standards(baseline_config):
    """Assert evaluation metrics meet or exceed the committed regression gate baseline."""
    results = evaluate_dataset(data_dir=DATA_DIR, provider_name="fake", fault_rate=0.0)

    # Decision Accuracy
    assert results["decision_accuracy"] >= baseline_config["decision_accuracy_min"], (
        f"Decision accuracy {results['decision_accuracy']} is below baseline {baseline_config['decision_accuracy_min']}"
    )

    # False-Complete Rate (Strictly zero tolerance for leaked incomplete applications)
    assert results["false_complete_rate"] <= baseline_config["false_complete_rate_max"], (
        f"False complete rate {results['false_complete_rate']} exceeds maximum {baseline_config['false_complete_rate_max']}"
    )
    assert results["false_complete_rate"] == 0.0, "False complete rate must be strictly 0.0% in production"

    # Document Request Precision, Recall, F1
    assert results["request_prf"]["f1"] >= baseline_config["request_f1_min"], (
        f"Request F1 {results['request_prf']['f1']} is below baseline {baseline_config['request_f1_min']}"
    )
    assert results["request_prf"]["precision"] >= 0.90, "Request precision should be high"
    assert results["request_prf"]["recall"] >= 0.90, "Request recall should be high"

    # Document Type Classification
    assert results["doc_type_accuracy"] >= baseline_config["doc_type_accuracy_min"], (
        f"Doc type accuracy {results['doc_type_accuracy']} is below baseline {baseline_config['doc_type_accuracy_min']}"
    )

    # Form Field Extraction
    assert results["field_accuracy"]["overall"] >= baseline_config["field_accuracy_min"], (
        f"Field extraction accuracy {results['field_accuracy']['overall']} is below baseline {baseline_config['field_accuracy_min']}"
    )

    # Step budget adherence
    assert results["steps"]["max"] <= baseline_config.get("max_steps_limit", 12), (
        f"Max steps taken ({results['steps']['max']}) exceeded step budget limit of 12"
    )


def test_confusion_matrix_coverage():
    """Assert all 3 decision classes have ground-truth representation and non-zero true positives."""
    results = evaluate_dataset(data_dir=DATA_DIR, provider_name="fake", fault_rate=0.0)
    cm = results["confusion_matrix"]

    for category in ["COMPLETE", "REQUEST_DOCUMENTS", "HUMAN_REVIEW"]:
        assert category in cm, f"Missing category {category} in confusion matrix"
        total_gt = sum(cm[category].values())
        assert total_gt > 0, f"Expected ground truth representation for {category}"
        assert cm[category][category] > 0, f"Expected non-zero true positive count for {category}"


def test_threshold_sweep_operability():
    """Verify confidence threshold sweep executes across [0.5, 0.6, 0.7, 0.8, 0.9] with zero false-complete."""
    sweep_results, recommended = run_threshold_sweep(
        data_dir=DATA_DIR,
        provider_name="fake",
        thresholds=[0.5, 0.6, 0.7, 0.8, 0.9],
    )

    assert len(sweep_results) == 5
    for item in sweep_results:
        assert item["false_complete_rate"] == 0.0, f"False-complete leaked at threshold {item['threshold']}"
        assert item["review_rate"] >= 0.10, f"Review rate should reflect ambiguous/unreadable cases"
        assert item["decision_accuracy"] >= 0.90

    assert recommended in [0.5, 0.6, 0.7, 0.8, 0.9]


def test_robustness_run_fault_tolerance():
    """Assert agent survives 20% random fault injection and enforces safety guardrails."""
    results = evaluate_dataset(data_dir=DATA_DIR, provider_name="fake", fault_rate=0.2, seed=7)

    # Safety constraint: Zero false-completes even during faulty execution
    assert results["false_complete_rate"] == 0.0
    # Recovery constraint: Survives errors and completes decision
    assert results["decision_accuracy"] >= 0.90
    # Efficiency: Step budget must not be exceeded despite recovery turns
    assert results["steps"]["max"] <= 12
