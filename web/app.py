"""FastAPI Web Server located at root /web, accessing the intake engine."""

import json
from pathlib import Path
from typing import Any, Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from intake.agent import run_agent, TRACE_STORE, AgentDecisionOutput, AgentTrace
from intake.schemas import Packet
from web.routes.llm import router as llm_router
from storage import (
    list_review_items,
    get_review_item,
    resolve_review_item,
    get_audit_log,
    AlreadyResolvedError,
    ResolveRequest,
    ReviewItem,
    AuditLogEntry,
)


app = FastAPI(
    title="Azentio Retail Loan Intake Agent API",
    version="1.0.0",
    description="Automated loan-application packet screener with tool-calling and safety guardrails"
)

app.include_router(llm_router)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR.parent / "data" / "packets"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# -------------------------------------------------------------------
# Required API Endpoints (from PDF Specification)
# -------------------------------------------------------------------

@app.post("/v1/packets/intake", response_model=AgentDecisionOutput)
def process_intake_packet(packet_data: Dict[str, Any]):
    """Process a loan-application packet and return a validated intake decision."""
    if not packet_data or "packet_id" not in packet_data:
        raise HTTPException(status_code=400, detail="Invalid packet JSON: 'packet_id' is required")
    
    try:
        decision = run_agent(packet_data)
        return decision
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent processing error: {str(e)}")


@app.get("/v1/traces/{trace_id}")
def get_execution_trace(trace_id: str):
    """Retrieve full recorded step-by-step trace of tool calls and latencies for an intake decision."""
    if trace_id not in TRACE_STORE:
        raise HTTPException(status_code=404, detail=f"Trace ID '{trace_id}' not found")
    
    trace_obj = TRACE_STORE[trace_id]
    return trace_obj.model_dump()


# -------------------------------------------------------------------
# Task 3: Human Review Queue & Regulatory Audit API Endpoints
# -------------------------------------------------------------------

@app.get("/v1/review-items", response_model=List[ReviewItem])
def get_review_items(status: str = "open"):
    """List review items filtered by status (default: open)."""
    return list_review_items(status=status)


@app.get("/v1/review-items/{item_id}", response_model=ReviewItem)
def get_single_review_item(item_id: str):
    """Retrieve details for a single review item."""
    item = get_review_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Review item '{item_id}' not found")
    return item


@app.post("/v1/review-items/{item_id}/resolve", response_model=ReviewItem)
def resolve_item(item_id: str, request: ResolveRequest):
    """Resolve an open review item. Returns 409 Conflict if already resolved."""
    try:
        updated_item = resolve_review_item(
            item_id=item_id,
            reviewer=request.reviewer,
            decision=request.decision,
            corrected_fields=request.corrected_fields,
            notes=request.notes,
        )
        return updated_item
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AlreadyResolvedError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resolve review item: {str(e)}")


@app.get("/v1/audit-log", response_model=List[AuditLogEntry])
def get_audit_trail(packet_id: str = None, limit: int = 50):
    """Retrieve immutable regulatory audit log history."""
    return get_audit_log(packet_id=packet_id, limit=limit)


# -------------------------------------------------------------------
# UI & Helper Endpoints
# -------------------------------------------------------------------

@app.get("/")
def serve_index_page():
    """Serve the interactive single-page dashboard."""
    index_file = BASE_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse({"status": "healthy", "service": "Azentio Intake Agent API"})
    return FileResponse(str(index_file))


@app.get("/api/packets")
def list_available_packets() -> List[str]:
    """Helper for UI to list available generated packets."""
    if not DATA_DIR.exists():
        return []
    packet_files = sorted(DATA_DIR.glob("*.json"))
    return [p.stem for p in packet_files]


@app.get("/api/packets/{packet_id}")
def get_packet_content(packet_id: str) -> Dict[str, Any]:
    """Helper for UI to load packet JSON content by ID."""
    p_file = DATA_DIR / f"{packet_id}.json"
    if not p_file.exists():
        raise HTTPException(status_code=404, detail="Packet not found")
    with open(p_file, "r", encoding="utf-8") as f:
        return json.load(f)

