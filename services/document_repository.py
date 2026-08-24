"""Document repository — versioned file storage with metadata."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1] / "data" / "documents"
REPO_ROOT.mkdir(parents=True, exist_ok=True)

CATEGORIES = (
    "invoice", "purchase_order", "qc_report", "coa", "image", "pdf",
    "contract", "employee", "other",
)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def store_document(
    *,
    category: str,
    title: str,
    source_path: Path | str,
    ref_type: str | None = None,
    ref_id: int | None = None,
    company_id: int = 1,
    branch_id: int | None = None,
    uploaded_by: int | None = None,
    tags: str | None = None,
    mime_type: str | None = None,
) -> int:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(str(source))
    dest_dir = REPO_ROOT / str(company_id) / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"{ts}_{source.name}"
    shutil.copy2(source, dest)
    size = dest.stat().st_size
    from database import get_connection
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO erp_documents(
                company_id,branch_id,doc_category,ref_type,ref_id,title,file_name,file_path,
                mime_type,file_size,version_no,is_current,tags,uploaded_by)
               VALUES(?,?,?,?,?,?,?,?,?,?,1,1,?,?)""",
            (
                company_id, branch_id, category, ref_type, ref_id, title, source.name,
                str(dest), mime_type, size, tags, uploaded_by,
            ),
        )
        doc_id = cur.lastrowid
        conn.execute(
            """INSERT INTO erp_document_versions(document_id,version_no,file_path,file_size,uploaded_by)
               VALUES(?,1,?,?,?)""",
            (doc_id, str(dest), size, uploaded_by),
        )
    return doc_id


def add_version(document_id: int, source_path: Path | str, uploaded_by: int | None = None, note: str = "") -> int:
    source = Path(source_path)
    from database import get_connection
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM erp_documents WHERE id=?", (document_id,)).fetchone()
        if not row:
            raise ValueError("Document not found")
        doc = dict(row)
        ver = (doc.get("version_no") or 1) + 1
        dest_dir = Path(doc["file_path"]).parent
        dest = dest_dir / f"v{ver}_{source.name}"
        shutil.copy2(source, dest)
        conn.execute("UPDATE erp_documents SET is_current=0 WHERE id=?", (document_id,))
        conn.execute(
            """UPDATE erp_documents SET version_no=?, file_path=?, file_size=?, is_current=1
               WHERE id=?""",
            (ver, str(dest), dest.stat().st_size, document_id),
        )
        conn.execute(
            """INSERT INTO erp_document_versions(document_id,version_no,file_path,file_size,change_note,uploaded_by)
               VALUES(?,?,?,?,?,?)""",
            (document_id, ver, str(dest), dest.stat().st_size, note, uploaded_by),
        )
    return ver


def list_documents(*, ref_type: str | None = None, ref_id: int | None = None, category: str | None = None):
    from database import get_connection, rows_to_list
    where, params = ["is_current=1"], []
    if ref_type:
        where.append("ref_type=?"); params.append(ref_type)
    if ref_id:
        where.append("ref_id=?"); params.append(ref_id)
    if category:
        where.append("doc_category=?"); params.append(category)
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            f"SELECT * FROM erp_documents WHERE {' AND '.join(where)} ORDER BY created_at DESC",
            params,
        ).fetchall())


def get_versions(document_id: int):
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            "SELECT * FROM erp_document_versions WHERE document_id=? ORDER BY version_no DESC",
            (document_id,),
        ).fetchall())
