"""Data models for SQLite review queue, audit trail, intake results, and eval runs."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ReviewItem(BaseModel):
    """A loan application needing human reviewer attention."""
    id: str
    packet_id: str
    status: Literal["open", "resolved"] = "open"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    reviewer: Optional[str] = None
    decision: Optional[str] = None
    low_confidence_fields: List[str] = Field(default_factory=list)
    packet_data: Dict[str, Any] = Field(default_factory=dict)
    corrected_fields: Optional[Dict[str, Any]] = None


class ResolveRequest(BaseModel):
    """Payload for resolving a human review item."""
    reviewer: str = Field(..., description="Username or ID of the human reviewer")
    decision: Optional[str] = Field(None, description="Optional explicit decision override (COMPLETE, REQUEST_DOCUMENTS, etc.)")
    corrected_fields: Dict[str, Any] = Field(default_factory=dict, description="Corrected or confirmed form field values")
    notes: Optional[str] = None


class AuditLogEntry(BaseModel):
    """An immutable record in the regulatory audit trail."""
    id: Optional[int] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    actor: str = Field(..., description="'agent', 'reviewer', 'system', or 'evaluator'")
    packet_id: str
    decision: str
    reason_codes: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)


class IntakeResultRecord(BaseModel):
    """Persistent record of an intake agent decision."""
    packet_id: str
    trace_id: str
    decision: str
    document_requests: List[Dict[str, Any]] = Field(default_factory=list)
    fields: Dict[str, Any] = Field(default_factory=dict)
    low_confidence_fields: List[str] = Field(default_factory=list)
    overridden: bool = False
    borrower_message: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EvalRunRecord(BaseModel):
    """Persistent summary of an intake evaluation execution."""
    run_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_packets: int
    decision_accuracy: float
    false_complete_rate: float
    request_f1: float
    doc_type_accuracy: float
    field_accuracy: float
    review_rate: float
    mean_steps: float
    max_steps: int
    fault_rate: float = 0.0
    confusion_matrix: Dict[str, Any] = Field(default_factory=dict)
    threshold_sweep: List[Dict[str, Any]] = Field(default_factory=list)
    report_file: Optional[str] = None

