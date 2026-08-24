"""Sandboxed business scripts — Before/After Save, Post, Print."""

from __future__ import annotations

import ast
import json
from typing import Any

ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.Compare, ast.Constant, ast.Dict, ast.List,
    ast.Name, ast.Load, ast.Store, ast.BinOp, ast.UnaryOp, ast.If, ast.For,
    ast.Assign, ast.AugAssign, ast.Return, ast.Pass, ast.Break, ast.Continue,
    ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Not, ast.USub,
    ast.Subscript, ast.Index, ast.Slice, ast.Tuple, ast.Call,
)

FORBIDDEN_NAMES = frozenset({
    "open", "exec", "eval", "compile", "__import__", "getattr", "setattr",
    "delattr", "globals", "locals", "vars", "dir", "input", "breakpoint",
    "os", "sys", "subprocess", "socket", "pathlib", "shutil",
})

TRIGGER_POINTS = (
    "before_save", "after_save", "before_post", "after_post", "before_print",
)


class ScriptSandbox(ast.NodeVisitor):
    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_NAMES:
            raise ValueError(f"Forbidden call: {node.func.id}")
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        raise ValueError("Import not allowed in scripts")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        raise ValueError("Import not allowed in scripts")


def validate_script(source: str) -> None:
    tree = ast.parse(source, mode="exec")
    for node in ast.walk(tree):
        if type(node) not in ALLOWED_NODES and not isinstance(node, (ast.Module, ast.expr)):
            raise ValueError(f"Disallowed syntax: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise ValueError(f"Forbidden name: {node.id}")
    ScriptSandbox().visit(tree)


def run_scripts(trigger_point: str, doc_type: str, context: dict, *, company_id: int = 1) -> dict:
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_scripts'").fetchone():
            return context
        scripts = rows_to_list(conn.execute(
            """SELECT * FROM erp_scripts
               WHERE trigger_point=? AND is_active=1 AND company_id=?
               AND (doc_type IS NULL OR doc_type=?)""",
            (trigger_point, company_id, doc_type),
        ).fetchall())
    env = {"context": dict(context), "result": None}
    safe_builtins = {"len": len, "float": float, "int": int, "str": str, "min": min, "max": max, "abs": abs}
    for script in scripts:
        body = script.get("script_body") or ""
        validate_script(body)
        exec(compile(body, f"<script:{script.get('code')}>", "exec"), {"__builtins__": safe_builtins}, env)
    return env.get("context", context)


def save_script(code: str, name: str, trigger_point: str, body: str, doc_type: str | None = None, company_id: int = 1) -> None:
    validate_script(body)
    from database import get_connection
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO erp_scripts(code,name,trigger_point,doc_type,script_body,company_id)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(code,company_id) DO UPDATE SET
               script_body=excluded.script_body, name=excluded.name""",
            (code, name, trigger_point, doc_type, body, company_id),
        )
