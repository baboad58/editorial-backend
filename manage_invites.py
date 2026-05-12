#!/usr/bin/env python3
"""
CLI admin para gestionar códigos de invitación de Book Factory.
Alternativa al Table Editor de Supabase — útil para scripting en lote.

Uso:
  python manage_invites.py create --email user@ejemplo.com --code OBRA-BETA-001
  python manage_invites.py list
  python manage_invites.py reset  --email user@ejemplo.com --code OBRA-BETA-001

Requiere SUPABASE_URL y SUPABASE_SERVICE_KEY en el .env.
"""

import argparse
import os
import sys
from pathlib import Path

# Cargar .env antes de importar invites_db
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from backend.api.invites_db import verify_invite, mark_used
import httpx

_TABLE = "invitation_codes"
STATUS_ICON = {"sent": "📨", "used": "✅"}


def _headers():
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json", "Prefer": "return=representation"}

def _url():
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not base or not os.getenv("SUPABASE_SERVICE_KEY"):
        print("✗ Faltan SUPABASE_URL o SUPABASE_SERVICE_KEY en el .env")
        sys.exit(1)
    return f"{base}/rest/v1/{_TABLE}"


def cmd_create(args):
    code  = args.code.strip().upper()
    email = args.email.strip().lower()
    try:
        res = httpx.post(_url(), headers=_headers(),
                         json={"code": code, "email": email, "status": "sent"}, timeout=10)
        if res.status_code == 409:
            print(f"✗ Ya existe: {code} / {email}")
            sys.exit(1)
        res.raise_for_status()
        print(f"✓ Código creado: {code}  →  {email}")
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


def cmd_list(_args):
    try:
        res = httpx.get(_url(), headers=_headers(),
                        params={"select": "code,email,status,created_at,used_at",
                                "order": "created_at.desc"}, timeout=10)
        res.raise_for_status()
        rows = res.json()
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
    if not rows:
        print("No hay códigos registrados.")
        return
    print(f"{'':2}{'ESTADO':8}  {'CÓDIGO':22}  {'EMAIL':35}  {'USADO'}")
    print("─" * 82)
    for r in rows:
        icon = STATUS_ICON.get(r["status"], "❓")
        print(f"  {icon} {r['status']:6}  {r['code']:22}  {r['email']:35}  {r['used_at'] or '—'}")


def cmd_reset(args):
    code  = args.code.strip().upper()
    email = args.email.strip().lower()
    try:
        res = httpx.patch(_url(), headers=_headers(),
                          params={"code": f"eq.{code}", "email": f"eq.{email}"},
                          json={"status": "sent", "used_at": None}, timeout=10)
        res.raise_for_status()
        if res.json():
            print(f"✓ Reseteado a 'sent': {code} / {email}")
        else:
            print(f"✗ No encontrado: {code} / {email}")
            sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Gestión de invitaciones — Book Factory")
    sub = parser.add_subparsers(dest="command", metavar="COMANDO")

    p = sub.add_parser("create", help="Crear código de invitación")
    p.add_argument("--email", required=True)
    p.add_argument("--code",  required=True)

    sub.add_parser("list", help="Listar todos los códigos")

    p = sub.add_parser("reset", help="Resetear código a 'sent'")
    p.add_argument("--email", required=True)
    p.add_argument("--code",  required=True)

    args = parser.parse_args()
    if   args.command == "create": cmd_create(args)
    elif args.command == "list":   cmd_list(args)
    elif args.command == "reset":  cmd_reset(args)
    else: parser.print_help()


if __name__ == "__main__":
    main()
