"""
Consola de administración: gestión de solicitudes de invitación y códigos de acceso.

Endpoints:
  POST /api/admin/login            — autenticar contra tabla admin_users de Supabase
  GET  /api/admin/data             — listar submissions + códigos (requiere token)
  POST /api/admin/assign           — asignar código a una solicitud + enviar correo
  POST /api/admin/generate-codes   — generar N códigos disponibles en el pool

Variables de entorno requeridas en .env:
  SUPABASE_URL         — ya existente
  SUPABASE_SERVICE_KEY — ya existente
  RESEND_API_KEY       — API key de Resend para envío de correos (opcional)

Migración SQL requerida (ejecutar UNA VEZ en SQL Editor de Supabase):
─────────────────────────────────────────────────────────────────────
-- Permitir códigos sin email asignado aún (pool disponible)
ALTER TABLE invitation_codes ALTER COLUMN email DROP NOT NULL;
ALTER TABLE invitation_codes DROP CONSTRAINT IF EXISTS invitation_codes_code_email_key;
ALTER TABLE invitation_codes ADD CONSTRAINT IF NOT EXISTS invitation_codes_code_key UNIQUE (code);

-- Campos de gestión en solicitudes de contacto
ALTER TABLE contact_submissions ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';
ALTER TABLE contact_submissions ADD COLUMN IF NOT EXISTS assigned_code TEXT;
─────────────────────────────────────────────────────────────────────
"""

import os
import ssl
import time
import uuid
import random
import string
import logging
from datetime import datetime, timezone

import httpx
import bcrypt
try:
    import truststore
    _ssl_ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
except Exception:
    _ssl_ctx = True

logger = logging.getLogger(__name__)

_TOKEN_TTL = 8 * 3600   # 8 horas
_admin_tokens: dict[str, dict] = {}


# ── Helpers Supabase ──────────────────────────────────────────────────────────

def _supa_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    key  = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY", "")
    if not base or not key:
        raise RuntimeError("Faltan SUPABASE_URL y SUPABASE_SERVICE_KEY en .env")
    return f"{base}/rest/v1/{table}"

def _supa_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY", "")
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


# ── Token admin ───────────────────────────────────────────────────────────────

def create_admin_token(usuario: str) -> dict:
    token = uuid.uuid4().hex
    exp   = time.time() + _TOKEN_TTL
    _admin_tokens[token] = {"codigo_usuario": usuario, "exp": exp}
    return {"token": token, "codigo_usuario": usuario, "exp": int(exp)}

def verify_admin_token(token: str) -> dict:
    entry = _admin_tokens.get(token or "")
    if not entry or time.time() > entry["exp"]:
        _admin_tokens.pop(token, None)
        return None
    return entry


# ── Autenticación ─────────────────────────────────────────────────────────────

async def handle_login(body: dict) -> dict:
    codigo   = str(body.get("codigo_usuario", "")).strip()
    contrasena = str(body.get("contrasena", "")).strip()
    if not codigo or not contrasena:
        raise PermissionError("Credenciales incorrectas.")

    async with httpx.AsyncClient(verify=_ssl_ctx, timeout=10) as client:
        r = await client.get(
            _supa_url("usuarios"),
            headers=_supa_headers(),
            params={
                "codigo_usuario": f"eq.{codigo}",
                "estado":         "eq.Activo",
                "select":         "codigo_usuario,contrasena,estado",
            },
        )
        r.raise_for_status()
        rows = r.json()

    if not rows:
        raise PermissionError("Credenciales incorrectas o usuario inactivo.")

    hash_guardado = rows[0].get("contrasena", "")
    if not bcrypt.checkpw(contrasena.encode("utf-8"), hash_guardado.encode("utf-8")):
        raise PermissionError("Credenciales incorrectas.")

    return create_admin_token(rows[0]["codigo_usuario"])


# ── Datos ─────────────────────────────────────────────────────────────────────

async def handle_data(token_entry: dict) -> dict:
    async with httpx.AsyncClient(verify=_ssl_ctx, timeout=15) as client:
        # Solicitudes de contacto (todas)
        r_sub = await client.get(
            _supa_url("contact_submissions"),
            headers=_supa_headers(),
            params={"select": "id,name,email,idea,created_at,status,codigo_asignado",
                    "order": "created_at.desc"},
        )
        r_sub.raise_for_status()
        submissions = r_sub.json() or []

        # Códigos de invitación
        r_cod = await client.get(
            _supa_url("invitation_codes"),
            headers=_supa_headers(),
            params={"select": "id,code,email,status,created_at,used_at",
                    "order": "created_at.desc"},
        )
        r_cod.raise_for_status()
        codes_raw = r_cod.json() or []

    # Normalizar status de códigos para la consola
    codes = []
    for c in codes_raw:
        st = (c.get("status") or "").lower()
        if st == "sent":
            st = "sent"       # ya asignado, pendiente de canje → 'sent' = Asignado en UI
        elif st == "used":
            st = "used"
        else:
            st = "available"  # null, available, o cualquier otro
        codes.append({**c, "status": st})

    return {
        "submissions": submissions,
        "codes":       codes,
        "me":          {"codigo_usuario": token_entry["codigo_usuario"]},
    }


# ── Asignar código ────────────────────────────────────────────────────────────

async def handle_assign(body: dict) -> dict:
    submission_id = body.get("submission_id")
    code_id       = body.get("code_id")
    if not submission_id or not code_id:
        raise ValueError("submission_id y code_id son requeridos.")

    async with httpx.AsyncClient(verify=_ssl_ctx, timeout=15) as client:
        # Obtener submission
        r_sub = await client.get(
            _supa_url("contact_submissions"),
            headers=_supa_headers(),
            params={"id": f"eq.{submission_id}", "select": "id,name,email"},
        )
        r_sub.raise_for_status()
        rows = r_sub.json()
        if not rows:
            raise ValueError(f"Solicitud {submission_id} no encontrada.")
        submission = rows[0]

        # Obtener código
        r_cod = await client.get(
            _supa_url("invitation_codes"),
            headers=_supa_headers(),
            params={"id": f"eq.{code_id}", "select": "id,code,status"},
        )
        r_cod.raise_for_status()
        cod_rows = r_cod.json()
        if not cod_rows:
            raise ValueError(f"Código {code_id} no encontrado.")
        code_row = cod_rows[0]
        code_val = code_row["code"]

        now = datetime.now(timezone.utc).isoformat()

        # Actualizar código: asignar email y marcar como 'sent'
        await client.patch(
            _supa_url("invitation_codes"),
            headers=_supa_headers(),
            params={"id": f"eq.{code_id}"},
            json={"email": submission["email"], "status": "sent"},
        )

        # Actualizar submission: marcar como asignado
        await client.patch(
            _supa_url("contact_submissions"),
            headers=_supa_headers(),
            params={"id": f"eq.{submission_id}"},
            json={"status": "asignado", "codigo_asignado": code_val},
        )

    # Enviar correo via Resend
    email_result = await _send_assignment_email(
        name=submission.get("name", ""),
        email=submission["email"],
        code=code_val,
    )

    return {"code": code_val, **email_result}


async def _send_assignment_email(name: str, email: str, code: str) -> dict:
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        logger.warning("[Admin] RESEND_API_KEY no configurada — correo no enviado.")
        return {"email_sent": False, "email_error_reason": "missing_resend_api_key"}
    if not email:
        return {"email_sent": False, "email_error_reason": "missing_recipient"}
    if not code:
        return {"email_sent": False, "email_error_reason": "missing_code"}

    html = f"""<!doctype html>
<html lang="es">
  <body style="margin:0;padding:24px;background:#f5f5f4;font-family:Helvetica,Arial,sans-serif;color:#1c1917;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
           style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e7e5e4;border-radius:12px;">
      <tr><td style="padding:28px 28px 8px;">
        <p style="font-size:12px;letter-spacing:0.2em;text-transform:uppercase;color:#a8a29e;margin:0 0 8px;">Editorial OBRA</p>
        <h1 style="font-family:Georgia,serif;font-size:22px;margin:0 0 16px;color:#0c0a09;">Felicitaciones {name}</h1>
        <p style="font-size:15px;line-height:1.55;margin:0 0 16px;">
          Te entrego el código de acceso para que puedas ingresar al portal con tu correo
          <strong>{email}</strong>.
        </p>
        <p style="margin:24px 0;text-align:center;">
          <span style="display:inline-block;padding:14px 22px;font-family:'Courier New',monospace;
                       font-size:20px;letter-spacing:0.18em;background:#fafaf9;
                       border:1px solid #d6d3d1;border-radius:8px;color:#0c0a09;">{code}</span>
        </p>
        <p style="font-size:15px;line-height:1.55;margin:0 0 24px;">Adelante con tu obra.</p>
        <p style="font-size:14px;color:#57534e;margin:0;">Te saluda atentamente,<br/><strong>Alfred</strong></p>
      </td></tr>
    </table>
  </body>
</html>"""

    text = f"Felicitaciones {name},\n\nTu código de acceso es: {code}\nÚsalo con tu correo: {email}\n\nAdelante con tu obra.\n\nAlfred"

    payload = {
        "from":    "Editorial OBRA <onboarding@resend.dev>",
        "to":      [email],
        "subject": "Tu código de acceso a OBRA",
        "html":    html,
        "text":    text,
    }

    try:
        async with httpx.AsyncClient(verify=_ssl_ctx, timeout=15) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        if r.status_code == 200 or r.status_code == 201:
            logger.info(f"[Admin] Correo enviado a {email} con código {code}")
            return {"email_sent": True}
        elif 400 <= r.status_code < 500:
            logger.warning(f"[Admin] Resend rechazó el correo: {r.status_code} {r.text[:200]}")
            return {"email_sent": False, "email_error_reason": "resend_client_error",
                    "email_error_status": r.status_code, "email_error": r.text[:200]}
        else:
            return {"email_sent": False, "email_error_reason": "resend_server_error",
                    "email_error_status": r.status_code}
    except Exception as e:
        logger.exception("[Admin] Error de red al enviar correo")
        return {"email_sent": False, "email_error_reason": "network_error", "email_error": str(e)}


# ── Generar códigos ───────────────────────────────────────────────────────────

def _gen_code() -> str:
    segment = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    num     = ''.join(random.choices(string.digits, k=3))
    return f"OBRA-{segment}-{num}"

async def handle_generate_codes(count: int = 10) -> dict:
    count = max(1, min(count, 50))
    codes = [{"code": _gen_code(), "email": None, "status": "available"} for _ in range(count)]

    async with httpx.AsyncClient(verify=_ssl_ctx, timeout=15) as client:
        r = await client.post(
            _supa_url("invitation_codes"),
            headers=_supa_headers(),
            json=codes,
        )
        r.raise_for_status()
        inserted = r.json() or []

    logger.info(f"[Admin] {len(inserted)} códigos generados")
    return {"count": len(inserted)}
