"""Per-document processing status, shared between consumer and hoa-bot pods.

consumer and hoa-bot run in separate K8s pods with no shared memory, but
both mount the same PVC — so a status file per doc_id on that shared volume
is the channel. consumer writes as it moves through each stage; hoa-bot
reads it to answer GET /status/{doc_id} for the frontend's polling.

See PLAN.md Phase 2 Step 2.5 for the full design.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional, TypedDict

from src.config.settings import DATA_DIR

Stage = Literal[
    "uploaded",
    "extracting",
    "chunking",
    "embedding",
    "summarizing",
    "ready",
    "error",
]


class Status(TypedDict):
    doc_id: str
    filename: str
    stage: Stage
    doc_type: Optional[str]
    chunks_total: Optional[int]
    chunks_done: Optional[int]
    summary: Optional[str]
    error_message: Optional[str]
    updated_at: str


def _status_dir() -> Path:
    return Path(DATA_DIR) / "status"


def _status_path(doc_id: str) -> Path:
    return _status_dir() / f"{doc_id}.json"


def write_status(
    doc_id: str,
    filename: str,
    stage: Stage,
    doc_type: Optional[str] = None,
    chunks_total: Optional[int] = None,
    chunks_done: Optional[int] = None,
    summary: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Status:
    """Write (overwrite) the status file for a document.

    Fields not provided fall back to whatever was already on disk, so
    intermediate stages don't need to re-pass earlier-known values like
    doc_type. Except chunks_done/chunks_total: pass None to mean "unknown at
    this stage" only on the very first write, otherwise stale progress
    numbers from a prior run could linger.
    """
    existing = read_status(doc_id) or {}

    status: Status = {
        "doc_id": doc_id,
        "filename": filename,
        "stage": stage,
        "doc_type": doc_type if doc_type is not None else existing.get("doc_type"),
        "chunks_total": chunks_total if chunks_total is not None else existing.get("chunks_total"),
        "chunks_done": chunks_done if chunks_done is not None else existing.get("chunks_done"),
        "summary": summary if summary is not None else existing.get("summary"),
        "error_message": error_message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    _status_dir().mkdir(parents=True, exist_ok=True)
    path = _status_path(doc_id)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(status, indent=2))
    os.replace(tmp_path, path)  # atomic on POSIX, avoids a reader seeing a half-written file

    return status


def read_status(doc_id: str) -> Optional[Status]:
    """Read the status file for a document. Returns None if it doesn't exist yet."""
    path = _status_path(doc_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
