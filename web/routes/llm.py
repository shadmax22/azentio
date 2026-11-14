"""Router for LLM agent console and endpoints."""

from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(prefix="/llm", tags=["LLM Console"])

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_FILE = BASE_DIR / "index.html"


@router.get("")
@router.get("/")
def serve_llm_frontend():
    """Serve the interactive intake agent frontend on /llm route."""
    if not INDEX_FILE.exists():
        return JSONResponse({"status": "healthy", "service": "Azentio Intake Agent UI"})
    return FileResponse(str(INDEX_FILE))

