"""SQLite connection manager and schema initialization for storage package."""

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

DEFAULT_DB_PATH = Path("data/intake.db")
_LOCK = threading.RLock()


def get_db_path() -> Path:
    """Get active database path from environment or default."""
    env_path = os.getenv("INTAKE_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def init_db(db_path: Optional[Path] = None):
    """Initialize database tables and indexes."""
    target_path = db_path or get_db_path()
    if target_path != Path(":memory:") and str(target_path) != ":memory:":
        target_path.parent.mkdir(parents=True, exist_ok=True)

    with _LOCK:
        conn = sqlite3.connect(str(target_path), check_same_thread=False)
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS review_items (
                        id TEXT PRIMARY KEY,
                        packet_id TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('open', 'resolved')),
                        created_at TEXT NOT NULL,
                        resolved_at TEXT,
                        reviewer TEXT,
                        decision TEXT,
                        low_confidence_fields TEXT,
                        packet_data TEXT NOT NULL,
                        corrected_fields TEXT
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_review_items_status ON review_items (status);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_review_items_packet ON review_items (packet_id);
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        packet_id TEXT NOT NULL,
                        decision TEXT NOT NULL,
                        reason_codes TEXT,
                        details TEXT
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_audit_log_packet ON audit_log (packet_id);
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS intake_results (
                        packet_id TEXT PRIMARY KEY,
                        trace_id TEXT NOT NULL,
                        decision TEXT NOT NULL,
                        document_requests TEXT,
                        fields TEXT,
                        low_confidence_fields TEXT,
                        overridden INTEGER DEFAULT 0,
                        borrower_message TEXT,
                        created_at TEXT NOT NULL
                    );
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS eval_runs (
                        run_id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        total_packets INTEGER NOT NULL,
                        decision_accuracy REAL NOT NULL,
                        false_complete_rate REAL NOT NULL,
                        request_f1 REAL NOT NULL,
                        doc_type_accuracy REAL NOT NULL,
                        field_accuracy REAL NOT NULL,
                        review_rate REAL NOT NULL,
                        mean_steps REAL NOT NULL,
                        max_steps INTEGER NOT NULL,
                        fault_rate REAL DEFAULT 0.0,
                        confusion_matrix TEXT,
                        threshold_sweep TEXT,
                        report_file TEXT
                    );
                """)
        finally:
            conn.close()


@contextmanager
def get_db_connection(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """Yield a managed SQLite connection wrapped with thread lock."""
    target_path = db_path or get_db_path()
    with _LOCK:
        conn = sqlite3.connect(str(target_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

