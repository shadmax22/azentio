"""Checklist configuration parser and query helpers located in intake/llm/."""

from pathlib import Path
from typing import Dict, List, Literal, Optional
import yaml
from pydantic import BaseModel, Field


RequirementRuleType = Literal[
    "not_expired",
    "max_age_days",
    "prior_calendar_months",
    "continuous_coverage_months",
    "latest_assessment_years",
    "document_exists",
]


class RequirementConfig(BaseModel):
    """Specification of an individual checklist requirement."""
    id: str = Field(..., description="Requirement ID, e.g. ID_PROOF, SALARY_SLIPS_3M")
    borrower_label: str = Field(..., description="Customer-friendly description for notifications")
    rule_type: RequirementRuleType = Field(..., description="Evaluation logic identifier")
    max_days: Optional[int] = None
    months_count: Optional[int] = None
    years_count: Optional[int] = None


class ChecklistConfig(BaseModel):
    """Top-level configuration mapping products and employment types to requirements."""
    version: str = "1.0"
    requirements: Dict[str, RequirementConfig]
    products: Dict[str, Dict[str, List[str]]]

    def get_requirement_ids(self, product: str, employment_type: str) -> List[str]:
        """Get the list of requirement IDs for a given product and employment category."""
        prod_rules = self.products.get(product)
        if not prod_rules:
            raise ValueError(f"Unknown product: {product}. Supported: {list(self.products.keys())}")
        
        req_ids = prod_rules.get(employment_type)
        if not req_ids:
            raise ValueError(f"Unknown employment type: {employment_type} for product: {product}. Supported: {list(prod_rules.keys())}")
        
        return req_ids

    def get_requirements(self, product: str, employment_type: str) -> List[RequirementConfig]:
        """Get full RequirementConfig objects for a given product and employment category."""
        req_ids = self.get_requirement_ids(product, employment_type)
        configs = []
        for rid in req_ids:
            req_config = self.requirements.get(rid)
            if not req_config:
                raise KeyError(f"Requirement ID '{rid}' referenced in products but not defined in requirements map")
            configs.append(req_config)
        return configs


def load_checklist(config_path: Optional[str] = None) -> ChecklistConfig:
    """Load and validate the YAML checklist configuration file.
    
    Checks in intake/llm/config/checklist.yaml first, then fallback to config/checklist.yaml.
    """
    candidate_paths = [
        Path(config_path) if config_path else None,
        Path("intake/llm/config/checklist.yaml"),
        Path("config/checklist.yaml"),
        Path(__file__).parent / "config" / "checklist.yaml",
    ]

    resolved_path = None
    for p in candidate_paths:
        if p and p.exists():
            resolved_path = p
            break

    if not resolved_path:
        raise FileNotFoundError(f"Checklist configuration not found. Checked: {[str(p) for p in candidate_paths if p]}")
    
    with open(resolved_path, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f)
    
    raw_requirements = raw_data.get("requirements", {})
    parsed_reqs: Dict[str, RequirementConfig] = {}
    for req_id, req_data in raw_requirements.items():
        data_copy = dict(req_data)
        data_copy["id"] = req_id
        parsed_reqs[req_id] = RequirementConfig.model_validate(data_copy)

    return ChecklistConfig(
        version=raw_data.get("version", "1.0"),
        requirements=parsed_reqs,
        products=raw_data.get("products", {})
    )

