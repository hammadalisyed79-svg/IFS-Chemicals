"""Fill blank ERP joining_date from Access Employee.JoineOn (old payroll DB)."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database as db
from import_payroll_hr import DEFAULT_SRC, EMP_SQL, _d, _open_access, _s, _uid


def main(apply: bool = True) -> int:
    src = DEFAULT_SRC
    if not src.exists():
        print(f"Access file not found: {src}")
        return 1

    ac = _open_access(src)
    rows = list(ac.cursor().execute(EMP_SQL).fetchall())
    ac.close()

    access_join = {}
    for r in rows:
        aid = int(r[0])
        join_on = _d(r[15])
        if join_on:
            access_join[aid] = join_on

    uid = _uid()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated = []
    with db.get_connection() as conn:
        erp = conn.execute(
            """SELECT e.id, e.code, e.full_name, e.joining_date, m.access_eid
               FROM employees e
               LEFT JOIN payroll_access_map m ON m.employee_id=e.id
               WHERE e.joining_date IS NULL OR TRIM(COALESCE(e.joining_date,''))=''"""
        ).fetchall()
        for e in erp:
            e = dict(e)
            aid = e.get("access_eid")
            code = e.get("code") or ""
            if aid is None and code.startswith("EMP-A") and len(code) >= 9 and code[5:9].isdigit():
                aid = int(code[5:9])
            if aid is None:
                continue
            join_on = access_join.get(int(aid))
            if not join_on:
                continue
            updated.append((e["code"], e["full_name"], join_on))
            if apply:
                conn.execute(
                    """UPDATE employees SET joining_date=?, modified_by=?, modified_at=?
                       WHERE id=?""",
                    (join_on, uid, ts, int(e["id"])),
                )

    print(f"{'Applied' if apply else 'Would update'} {len(updated)} joining dates from Access JoineOn")
    for row in updated:
        print(f"  {row[0]}  {row[1]}  ->  {row[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(apply="--preview" not in sys.argv))
