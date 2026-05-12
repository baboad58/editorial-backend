"""
Gestión de códigos de invitación en SQLite local.

Tabla invitation_codes:
  code    — código enviado al usuario (ej. OBRA-BETA-001)
  email   — email al que fue enviado
  status  — 'sent' (válido) | 'used' (consumido)

El acceso se permite solo con status='sent' y la pareja correcta email+código.
La DB se crea automáticamente al arrancar el backend.
"""

import sqlite3
import os
import logging
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

INVITES_DB = os.getenv("INVITES_DB", "invites.db")


@contextmanager
def _conn():
    con = sqlite3.connect(INVITES_DB, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    """Crea la tabla si no existe. Se llama automáticamente al arrancar el servidor."""
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS invitation_codes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                code       TEXT NOT NULL,
                email      TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'sent',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                used_at    DATETIME,
                UNIQUE(code, email)
            )
        """)
    logger.info(f"[Invites] DB lista: {INVITES_DB}")


def verify_invite(code: str, email: str) -> bool:
    """True si el par code+email existe con status='sent'."""
    code  = code.strip().upper()
    email = email.strip().lower()
    with _conn() as con:
        row = con.execute(
            "SELECT status FROM invitation_codes WHERE code = ? AND email = ?",
            (code, email),
        ).fetchone()
    if row is None:
        return False
    return row["status"] == "sent"


def mark_used(code: str, email: str) -> bool:
    """Marca el código como 'used'. Idempotente — safe llamar múltiples veces."""
    code  = code.strip().upper()
    email = email.strip().lower()
    with _conn() as con:
        cursor = con.execute(
            """UPDATE invitation_codes
               SET status = 'used', used_at = CURRENT_TIMESTAMP
               WHERE code = ? AND email = ? AND status = 'sent'""",
            (code, email),
        )
    updated = cursor.rowcount > 0
    if updated:
        logger.info(f"[Invites] Código marcado como usado: {code} / {email}")
    return updated


def create_invite(code: str, email: str) -> bool:
    """Crea un nuevo código. Retorna False si ya existe la pareja code+email."""
    code  = code.strip().upper()
    email = email.strip().lower()
    try:
        with _conn() as con:
            con.execute(
                "INSERT INTO invitation_codes (code, email, status) VALUES (?, ?, 'sent')",
                (code, email),
            )
        logger.info(f"[Invites] Código creado: {code} → {email}")
        return True
    except sqlite3.IntegrityError:
        return False


def list_invites() -> list[dict]:
    """Devuelve todos los códigos de invitación."""
    with _conn() as con:
        rows = con.execute(
            "SELECT code, email, status, created_at, used_at FROM invitation_codes ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def reset_invite(code: str, email: str) -> bool:
    """Resetea un código a 'sent'. Permite reutilizar un código consumido."""
    code  = code.strip().upper()
    email = email.strip().lower()
    with _conn() as con:
        cursor = con.execute(
            "UPDATE invitation_codes SET status = 'sent', used_at = NULL WHERE code = ? AND email = ?",
            (code, email),
        )
    updated = cursor.rowcount > 0
    if updated:
        logger.info(f"[Invites] Código reseteado: {code} / {email}")
    return updated
