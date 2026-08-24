"""Data access gateway — UI must import from here, never database/db_v3 directly."""

from __future__ import annotations

import importlib

_database = importlib.import_module("database")
_db_v3 = importlib.import_module("db_v3")


def __getattr__(name: str):
    if hasattr(_db_v3, name):
        return getattr(_db_v3, name)
    if hasattr(_database, name):
        return getattr(_database, name)
    raise AttributeError(f"data_gateway has no attribute {name!r}")


# Explicit re-exports for static analysis / IDE
get_connection = _database.get_connection
init_db = _database.init_db
authenticate = _database.authenticate
