"""Database abstraction — SQLite today; PostgreSQL/MySQL/SQL Server prepared."""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from application.config import config


class DatabaseAdapter(ABC):
    dialect: str = "generic"

    @abstractmethod
    @contextmanager
    def connection(self) -> Iterator[Any]:
        ...

    @abstractmethod
    def execute(self, sql: str, params: tuple | list = ()) -> Any:
        ...

    def placeholder(self, n: int = 1) -> str:
        return ", ".join(["?"] * n)


class SQLiteAdapter(DatabaseAdapter):
    dialect = "sqlite"

    def __init__(self, path: Path | None = None):
        self.path = path or Path(__file__).resolve().parents[2] / "ifs_erp.db"

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple | list = ()):
        with self.connection() as conn:
            return conn.execute(sql, params)


class PostgreSQLAdapter(DatabaseAdapter):
    """Stub — requires psycopg2 and connection string in erp_config."""
    dialect = "postgresql"

    @contextmanager
    def connection(self):
        raise NotImplementedError("PostgreSQL adapter: set database.driver=postgresql and install psycopg2")

    def execute(self, sql: str, params: tuple | list = ()):
        raise NotImplementedError("PostgreSQL adapter not configured")


class MySQLAdapter(DatabaseAdapter):
    dialect = "mysql"

    @contextmanager
    def connection(self):
        raise NotImplementedError("MySQL adapter: install pymysql and configure erp_config")

    def execute(self, sql: str, params: tuple | list = ()):
        raise NotImplementedError("MySQL adapter not configured")


class MSSQLAdapter(DatabaseAdapter):
    dialect = "mssql"

    @contextmanager
    def connection(self):
        raise NotImplementedError("SQL Server adapter: configure pyodbc connection in erp_config")

    def execute(self, sql: str, params: tuple | list = ()):
        raise NotImplementedError("SQL Server adapter not configured")


def get_adapter() -> DatabaseAdapter:
    driver = (config.get("database", "driver", "sqlite") or "sqlite").lower()
    adapters = {
        "sqlite": SQLiteAdapter,
        "postgresql": PostgreSQLAdapter,
        "postgres": PostgreSQLAdapter,
        "mysql": MySQLAdapter,
        "mssql": MSSQLAdapter,
        "sqlserver": MSSQLAdapter,
    }
    cls = adapters.get(driver, SQLiteAdapter)
    return cls()


def translate_sql(sql: str, from_dialect: str = "sqlite", to_dialect: str | None = None) -> str:
    """Basic SQL dialect hints for future migration scripts."""
    to_dialect = to_dialect or get_adapter().dialect
    if from_dialect == to_dialect:
        return sql
    out = sql
    if to_dialect == "postgresql":
        out = out.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        out = out.replace("AUTOINCREMENT", "")
    return out
