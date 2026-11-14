"""Database repository operations for review items, audit log, intake results, and eval runs."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from storage.database import get_db_connection, init_db, get_db_path
from storage.models import ReviewItem, AuditLogEntry, IntakeResultRecord, EvalRunRecord
from storage.pii import mask_pii, mask_pii_text


class AlreadyResolvedError(Exception):
    """Raised when an attempt is made to resolve an already-resolved review item (HTTP 409)."""
    pass


CORRECTIONS_FILE = Path("data/corrections.jsonl")


def save_intake_result(
    output: Any,
    packet_data: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None
) -> IntakeResultRecord:
    """Persist an intake decision and audit log row."""
    init_db(db_path)

    packet_id = getattr(output, "packet_id", None) or packet_data.get("packet_id", "unknown")
    trace_id = getattr(output, "trace_id", "")
    decision = getattr(output, "decision", "HUMAN_REVIEW")
    overridden = bool(getattr(output, "overridden", False))
    borrower_message = getattr(output, "borrower_message", None)

    # Document requests
    raw_reqs = getattr(output, "document_requests", [])
    doc_requests = [
        {"requirement_id": r.requirement_id, "reason_code": r.reason_code}
        if hasattr(r, "requirement_id") else r
        for r in raw_reqs
    ]
    reason_codes = [r["reason_code"] for r in doc_requests]

    # Fields and low confidence
    fields = getattr(output, "fields", {})
    low_confidence_fields = getattr(output, "low_confidence_fields", [])

    masked_fields = mask_pii(fields)
    now_iso = datetime.now(timezone.utc).isoformat()

    record = IntakeResultRecord(
        packet_id=packet_id,
        trace_id=trace_id,
        decision=decision,
        document_requests=doc_requests,
        fields=masked_fields,
        low_confidence_fields=low_confidence_fields,
        overridden=overridden,
        borrower_message=mask_pii_text(borrower_message) if borrower_message else None,
        created_at=now_iso,
    )

    with get_db_connection(db_path) as conn:
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO intake_results (
                    packet_id, trace_id, decision, document_requests,
                    fields, low_confidence_fields, overridden, borrower_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.packet_id,
                record.trace_id,
                record.decision,
                json.dumps(record.document_requests),
                json.dumps(record.fields),
                json.dumps(record.low_confidence_fields),
                1 if record.overridden else 0,
                record.borrower_message,
                record.created_at,
            ))

    # Append to immutable audit log
    append_audit_log(
        actor="agent",
        packet_id=packet_id,
        decision=decision,
        reason_codes=reason_codes,
        details={
            "trace_id": trace_id,
            "overridden": overridden,
            "low_confidence_fields": low_confidence_fields,
        },
        db_path=db_path
    )

    # If decision is HUMAN_REVIEW, enqueue review item
    if decision == "HUMAN_REVIEW" and packet_data:
        create_review_item(
            packet_id=packet_id,
            low_confidence_fields=low_confidence_fields,
            packet_data=packet_data,
            db_path=db_path
        )

    return record


def create_review_item(
    packet_id: str,
    low_confidence_fields: List[str],
    packet_data: Dict[str, Any],
    db_path: Optional[Path] = None
) -> ReviewItem:
    """Create or return an open review item for a loan application."""
    init_db(db_path)

    # Check for existing open item for this packet
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM review_items WHERE packet_id = ? AND status = 'open'",
            (packet_id,)
        ).fetchone()

        if row:
            return ReviewItem(
                id=row["id"],
                packet_id=row["packet_id"],
                status=row["status"],
                created_at=row["created_at"],
                resolved_at=row["resolved_at"],
                reviewer=row["reviewer"],
                decision=row["decision"],
                low_confidence_fields=json.loads(row["low_confidence_fields"] or "[]"),
                packet_data=json.loads(row["packet_data"] or "{}"),
                corrected_fields=json.loads(row["corrected_fields"]) if row["corrected_fields"] else None,
            )

    item_id = f"rev_{uuid.uuid4().hex[:10]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    masked_packet = mask_pii(packet_data)

    item = ReviewItem(
        id=item_id,
        packet_id=packet_id,
        status="open",
        created_at=now_iso,
        low_confidence_fields=low_confidence_fields,
        packet_data=masked_packet,
    )

    with get_db_connection(db_path) as conn:
        with conn:
            conn.execute("""
                INSERT INTO review_items (
                    id, packet_id, status, created_at, low_confidence_fields, packet_data
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                item.id,
                item.packet_id,
                item.status,
                item.created_at,
                json.dumps(item.low_confidence_fields),
                json.dumps(item.packet_data),
            ))

    return item


def list_review_items(
    status: Optional[str] = "open",
    db_path: Optional[Path] = None
) -> List[ReviewItem]:
    """Retrieve list of review items, optionally filtered by status."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM review_items WHERE status = ? ORDER BY created_at DESC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM review_items ORDER BY created_at DESC"
            ).fetchall()

        items = []
        for r in rows:
            items.append(ReviewItem(
                id=r["id"],
                packet_id=r["packet_id"],
                status=r["status"],
                created_at=r["created_at"],
                resolved_at=r["resolved_at"],
                reviewer=r["reviewer"],
                decision=r["decision"],
                low_confidence_fields=json.loads(r["low_confidence_fields"] or "[]"),
                packet_data=json.loads(r["packet_data"] or "{}"),
                corrected_fields=json.loads(r["corrected_fields"]) if r["corrected_fields"] else None,
            ))
        return items


def get_review_item(item_id: str, db_path: Optional[Path] = None) -> Optional[ReviewItem]:
    """Get single review item by ID."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM review_items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return None
        return ReviewItem(
            id=row["id"],
            packet_id=row["packet_id"],
            status=row["status"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
            reviewer=row["reviewer"],
            decision=row["decision"],
            low_confidence_fields=json.loads(row["low_confidence_fields"] or "[]"),
            packet_data=json.loads(row["packet_data"] or "{}"),
            corrected_fields=json.loads(row["corrected_fields"]) if row["corrected_fields"] else None,
        )


def resolve_review_item(
    item_id: str,
    reviewer: str,
    decision: Optional[str] = None,
    corrected_fields: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
    db_path: Optional[Path] = None
) -> ReviewItem:
    """Resolve an open review item with corrected fields and reviewer decision.
    
    Raises AlreadyResolvedError (HTTP 409 Conflict) if the item is already closed.
    """
    item = get_review_item(item_id, db_path=db_path)
    if not item:
        raise KeyError(f"Review item with ID '{item_id}' not found.")

    if item.status == "resolved":
        raise AlreadyResolvedError(f"Review item '{item_id}' is already resolved.")

    corrected = corrected_fields or {}
    masked_corrected = mask_pii(corrected)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Re-evaluate completeness on corrected fields if explicit decision not supplied
    final_decision = decision
    reason_codes: List[str] = []

    if not final_decision:
        try:
            from intake.llm.tools.registry import execute_tool
            # Merge corrected fields into packet form values
            pkt = item.packet_data
            app_form = pkt.get("application_form", "")
            as_of = pkt.get("as_of", "2026-03-15")
            docs = pkt.get("documents", [])

            # Re-run check_completeness
            classified_docs = []
            for d in docs:
                c_res = execute_tool("classify_document", {"doc_id": d["doc_id"], "text": d["text"]})
                e_res = execute_tool("extract_fields", {"doc_id": d["doc_id"], "text": d["text"]})
                classified_docs.append({
                    "doc_id": d["doc_id"],
                    "doc_type": c_res.get("doc_type", "UNKNOWN"),
                    "expiry_date": e_res.get("fields", {}).get("expiry_date", {}).get("value"),
                    "issue_date": e_res.get("fields", {}).get("issue_date", {}).get("value"),
                    "pay_month": e_res.get("fields", {}).get("pay_month", {}).get("value"),
                    "period_start": e_res.get("fields", {}).get("period_start", {}).get("value"),
                    "period_end": e_res.get("fields", {}).get("period_end", {}).get("value"),
                    "assessment_year": e_res.get("fields", {}).get("assessment_year", {}).get("value"),
                    "confidence": 0.95
                })

            prod = masked_corrected.get("product") or "personal_loan"
            emp = masked_corrected.get("employment_type") or "salaried"
            app_d = masked_corrected.get("application_date") or as_of

            comp_res = execute_tool("check_completeness", {
                "product": prod,
                "employment_type": emp,
                "as_of": as_of,
                "application_date": app_d,
                "documents": classified_docs
            })

            if comp_res.get("all_satisfied"):
                final_decision = "COMPLETE"
            else:
                final_decision = "REQUEST_DOCUMENTS"
                reason_codes = [u["reason_code"] for u in comp_res.get("unsatisfied", [])]
        except Exception:
            final_decision = "COMPLETE"
    else:
        final_decision = decision.upper()

    # Update item in database
    with get_db_connection(db_path) as conn:
        with conn:
            conn.execute("""
                UPDATE review_items SET
                    status = 'resolved',
                    resolved_at = ?,
                    reviewer = ?,
                    decision = ?,
                    corrected_fields = ?
                WHERE id = ?
            """, (
                now_iso,
                reviewer,
                final_decision,
                json.dumps(masked_corrected),
                item_id,
            ))

    # Append to audit log
    append_audit_log(
        actor="reviewer",
        packet_id=item.packet_id,
        decision=final_decision,
        reason_codes=reason_codes,
        details={
            "review_item_id": item_id,
            "reviewer": reviewer,
            "notes": notes,
            "corrected_fields": masked_corrected,
        },
        db_path=db_path
    )

    # Append to data/corrections.jsonl in labels.jsonl format
    append_correction(
        packet_id=item.packet_id,
        reviewer=reviewer,
        resolved_at=now_iso,
        corrected_fields=masked_corrected,
        decision=final_decision,
    )

    # Return updated model
    item.status = "resolved"
    item.resolved_at = now_iso
    item.reviewer = reviewer
    item.decision = final_decision
    item.corrected_fields = masked_corrected
    return item


def append_correction(
    packet_id: str,
    reviewer: str,
    resolved_at: str,
    corrected_fields: Dict[str, Any],
    decision: str,
    corrections_path: Optional[Path] = None
):
    """Append a human correction row to data/corrections.jsonl in labels.jsonl format."""
    target_path = corrections_path or CORRECTIONS_FILE
    target_path.parent.mkdir(parents=True, exist_ok=True)
    correction_record = {
        "packet_id": packet_id,
        "expected_decision": decision,
        "form_fields": corrected_fields,
        "corrected_by": reviewer,
        "corrected_at": resolved_at,
    }
    with open(target_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(correction_record) + "\n")


def append_audit_log(
    actor: str,
    packet_id: str,
    decision: str,
    reason_codes: Optional[List[str]] = None,
    details: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None
) -> int:
    """Append an immutable audit entry with automatic PII masking."""
    init_db(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    codes = reason_codes or []
    det = mask_pii(details or {})

    with get_db_connection(db_path) as conn:
        with conn:
            cursor = conn.execute("""
                INSERT INTO audit_log (
                    timestamp, actor, packet_id, decision, reason_codes, details
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                now_iso,
                actor,
                packet_id,
                decision,
                json.dumps(codes),
                json.dumps(det),
            ))
            return cursor.lastrowid


def get_audit_log(
    packet_id: Optional[str] = None,
    limit: int = 100,
    db_path: Optional[Path] = None
) -> List[AuditLogEntry]:
    """Retrieve audit log entries, optionally filtered by packet_id."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        if packet_id:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE packet_id = ? ORDER BY id DESC LIMIT ?",
                (packet_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()

        entries = []
        for r in rows:
            entries.append(AuditLogEntry(
                id=r["id"],
                timestamp=r["timestamp"],
                actor=r["actor"],
                packet_id=r["packet_id"],
                decision=r["decision"],
                reason_codes=json.loads(r["reason_codes"] or "[]"),
                details=json.loads(r["details"] or "{}"),
            ))
        return entries


def save_eval_run(
    eval_data: Dict[str, Any],
    sweep_results: Optional[List[Dict[str, Any]]] = None,
    fault_run_data: Optional[Dict[str, Any]] = None,
    report_file: Optional[str] = "reports/eval.md",
    db_path: Optional[Path] = None
) -> EvalRunRecord:
    """Persist an evaluation suite run to SQLite."""
    init_db(db_path)
    run_id = f"eval_{uuid.uuid4().hex[:10]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    record = EvalRunRecord(
        run_id=run_id,
        timestamp=now_iso,
        total_packets=eval_data.get("total_packets", 0),
        decision_accuracy=eval_data.get("decision_accuracy", 0.0),
        false_complete_rate=eval_data.get("false_complete_rate", 0.0),
        request_f1=eval_data.get("request_prf", {}).get("f1", 0.0),
        doc_type_accuracy=eval_data.get("doc_type_accuracy", 0.0),
        field_accuracy=eval_data.get("field_accuracy", {}).get("overall", 0.0),
        review_rate=eval_data.get("review_rate", 0.0),
        mean_steps=eval_data.get("steps", {}).get("mean", 0.0),
        max_steps=eval_data.get("steps", {}).get("max", 0),
        fault_rate=eval_data.get("fault_rate", 0.0),
        confusion_matrix=eval_data.get("confusion_matrix", {}),
        threshold_sweep=sweep_results or [],
        report_file=report_file,
    )

    with get_db_connection(db_path) as conn:
        with conn:
            conn.execute("""
                INSERT INTO eval_runs (
                    run_id, timestamp, total_packets, decision_accuracy,
                    false_complete_rate, request_f1, doc_type_accuracy,
                    field_accuracy, review_rate, mean_steps, max_steps,
                    fault_rate, confusion_matrix, threshold_sweep, report_file
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.run_id,
                record.timestamp,
                record.total_packets,
                record.decision_accuracy,
                record.false_complete_rate,
                record.request_f1,
                record.doc_type_accuracy,
                record.field_accuracy,
                record.review_rate,
                record.mean_steps,
                record.max_steps,
                record.fault_rate,
                json.dumps(record.confusion_matrix),
                json.dumps(record.threshold_sweep),
                record.report_file,
            ))

    # Audit row for eval run
    append_audit_log(
        actor="evaluator",
        packet_id="batch_eval",
        decision=f"ACC_{record.decision_accuracy*100:.1f}%",
        details={
            "run_id": run_id,
            "total_packets": record.total_packets,
            "false_complete_rate": record.false_complete_rate,
        },
        db_path=db_path
    )

    return record
