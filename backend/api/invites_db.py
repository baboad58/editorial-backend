"""
Gestión de códigos de invitación via Supabase REST API (PostgREST).
Usa httpx directamente — sin SDK de supabase-py para evitar dependencias de pyiceberg en Windows.

Tabla requerida en Supabase (ejecutar en SQL Editor):
─────────────────────────────────────────────────────
CREATE TABLE invitation_codes (
    id         BIGSERIAL PRIMARY KEY,
    code       TEXT NOT NULL,
    email      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'sent',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    used_at    TIMESTAMPTZ,
    UNIQUE(code, email)
);

-- Solo el backend (service role) puede modificar la tabla
ALTER TABLE invitation_codes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only" ON invitation_codes USING (false);
─────────────────────────────────────────────────────

Variables de entorno requeridas:
  SUPABASE_URL         — https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY — service role key (nunca el anon key en el backend)
"""

import os
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_TABLE = "invitation_codes"


def _headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


def _base_url() -> str:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL es obligatoria. Agrégala al archivo .env")
    if not os.getenv("SUPABASE_SERVICE_KEY"):
        raise RuntimeError("SUPABASE_SERVICE_KEY es obligatoria. Agrégala al archivo .env")
    return f"{url}/rest/v1/{_TABLE}"


def verify_invite(code: str, email: str) -> bool:
    """True si el par code+email existe con status='sent'."""
    code  = code.strip().upper()
    email = email.strip().lower()
    try:
        res = httpx.get(
            _base_url(),
            headers=_headers(),
            params={"code": f"eq.{code}", "email": f"eq.{email}", "select": "status"},
            timeout=10,
        )
        res.raise_for_status()
        rows = res.json()
        return bool(rows) and rows[0].get("status") == "sent"
    except Exception:
        logger.exception("[Invites] Error al verificar código")
        return False


def mark_used(code: str, email: str) -> bool:
    """Marca el código como 'used'. Idempotente — safe llamar múltiples veces."""
    code  = code.strip().upper()
    email = email.strip().lower()
    try:
        now = datetime.now(timezone.utc).isoformat()
        res = httpx.patch(
            _base_url(),
            headers=_headers(),
            params={"code": f"eq.{code}", "email": f"eq.{email}", "status": "eq.sent"},
            json={"status": "used", "used_at": now},
            timeout=10,
        )
        res.raise_for_status()
        updated = len(res.json() or []) > 0
        if updated:
            logger.info(f"[Invites] Código marcado como usado: {code} / {email}")
        return updated
    except Exception:
        logger.exception("[Invites] Error al marcar código como usado")
        return False


def create_invite(code: str, email: str) -> bool:
    """Crea un nuevo código. Retorna False si ya existe la pareja code+email."""
    code  = code.strip().upper()
    email = email.strip().lower()
    try:
        res = httpx.post(
            _base_url(),
            headers=_headers(),
            json={"code": code, "email": email, "status": "sent"},
            timeout=10,
        )
        if res.status_code == 409:   # UNIQUE constraint violation
            return False
        res.raise_for_status()
        logger.info(f"[Invites] Código creado: {code} → {email}")
        return True
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return False
        logger.exception("[Invites] Error al crear código")
        raise


def list_invites() -> list[dict]:
    """Devuelve todos los códigos de invitación, ordenados por fecha desc."""
    try:
        res = httpx.get(
            _base_url(),
            headers=_headers(),
            params={"select": "code,email,status,created_at,used_at", "order": "created_at.desc"},
            timeout=10,
        )
        res.raise_for_status()
        return res.json() or []
    except Exception:
        logger.exception("[Invites] Error al listar códigos")
        return []


def reset_invite(code: str, email: str) -> bool:
    """Resetea un código a 'sent'. Permite reutilizar un código consumido."""
    code  = code.strip().upper()
    email = email.strip().lower()
    try:
        res = httpx.patch(
            _base_url(),
            headers=_headers(),
            params={"code": f"eq.{code}", "email": f"eq.{email}"},
            json={"status": "sent", "used_at": None},
            timeout=10,
        )
        res.raise_for_status()
        updated = len(res.json() or []) > 0
        if updated:
            logger.info(f"[Invites] Código reseteado: {code} / {email}")
        return updated
    except Exception:
        logger.exception("[Invites] Error al resetear código")
        return False
