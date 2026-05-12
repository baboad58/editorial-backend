"""
Gestión de códigos de invitación via Supabase REST API (PostgREST).
Usa httpx directamente — evita el SDK supabase-py que requiere pyiceberg en Windows.

Tabla requerida en Supabase (ejecutar UNA VEZ en SQL Editor de tu proyecto):
─────────────────────────────────────────────────────────────────────────────
CREATE TABLE invitation_codes (
    id         BIGSERIAL PRIMARY KEY,
    code       TEXT NOT NULL,
    email      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'sent',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    used_at    TIMESTAMPTZ,
    UNIQUE(code, email)
);
─────────────────────────────────────────────────────────────────────────────

Después puedes crear/ver/resetear códigos directamente desde el Table Editor
de tu dashboard en supabase.com — sin SSH ni CLI.

Variables de entorno requeridas en .env:
  SUPABASE_URL         — https://xxxx.supabase.co          (Settings → API → Project URL)
  SUPABASE_SERVICE_KEY — service_role key que empieza eyJ  (Settings → API → service_role)
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


def _url() -> str:
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not base or not os.getenv("SUPABASE_SERVICE_KEY"):
        raise RuntimeError(
            "Faltan variables de entorno: SUPABASE_URL y SUPABASE_SERVICE_KEY. "
            "Agrégalas al archivo .env"
        )
    return f"{base}/rest/v1/{_TABLE}"


def verify_invite(code: str, email: str) -> bool:
    """True si el par code+email existe con status='sent'."""
    code  = code.strip().upper()
    email = email.strip().lower()
    try:
        res = httpx.get(
            _url(),
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
            _url(),
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
