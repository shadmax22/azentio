"""Scenario recipes and quota distribution for synthetic packet generation."""

import random
from typing import List, Dict, Any


def build_scenario_bucket(total_packets: int, rng: random.Random) -> List[Dict[str, Any]]:
    """Build a deterministic, balanced scenario list fulfilling all BFSI test criteria.
    
    Requirements:
    - At least 40% REQUEST_DOCUMENTS covering all 4 reason codes:
      (MISSING, INCOMPLETE_COVERAGE, STALE, EXPIRED)
    - At least 15% HUMAN_REVIEW (unreadable scan or ambiguous form), with expected_requests = []
    - Remaining are COMPLETE (all rules satisfied)
    """
    if total_packets < 10:
        raise ValueError("total_packets must be at least 10 to cover all required test scenarios")

    # Minimum counts based on percentages
    min_review = max(6, int(total_packets * 0.15))
    min_requests = max(16, int(total_packets * 0.40))
    complete_count = total_packets - min_review - min_requests

    scenarios: List[Dict[str, Any]] = []

    # 1. Complete Scenarios
    for i in range(complete_count):
        # Alternate between personal/home and salaried/self_employed
        prod = "personal_loan" if i % 2 == 0 else "home_loan"
        emp = "salaried" if (i // 2) % 2 == 0 else "self_employed"
        scenarios.append({
            "decision": "COMPLETE",
            "flaw": None,
            "product": prod,
            "employment_type": emp,
        })

    # 2. Request Documents Scenarios (Split evenly across 4 reason codes)
    reason_codes = ["STALE", "EXPIRED", "INCOMPLETE_COVERAGE", "MISSING"]
    for i in range(min_requests):
        code = reason_codes[i % len(reason_codes)]
        prod = "home_loan" if code == "MISSING" else ("personal_loan" if i % 2 == 0 else "home_loan")
        emp = "salaried" if code == "INCOMPLETE_COVERAGE" else ("salaried" if i % 2 == 0 else "self_employed")
        scenarios.append({
            "decision": "REQUEST_DOCUMENTS",
            "flaw": code,
            "product": prod,
            "employment_type": emp,
        })

    # 3. Human Review Scenarios (Unreadable document or ambiguous form)
    for i in range(min_review):
        flaw_type = "UNREADABLE_DOC" if i % 2 == 0 else "AMBIGUOUS_FORM"
        prod = "personal_loan" if i % 2 == 0 else "home_loan"
        emp = "salaried" if i % 2 == 0 else "self_employed"
        scenarios.append({
            "decision": "HUMAN_REVIEW",
            "flaw": flaw_type,
            "product": prod,
            "employment_type": emp,
        })

    # Deterministically shuffle recipes across packet IDs
    rng.shuffle(scenarios)
    return scenarios

