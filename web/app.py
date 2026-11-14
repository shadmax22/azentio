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

