#!/usr/bin/env python3
"""
CLI admin para gestionar códigos de invitación de Book Factory.

Uso:
  python manage_invites.py create --email user@ejemplo.com --code OBRA-BETA-001
  python manage_invites.py list
  python manage_invites.py reset  --email user@ejemplo.com --code OBRA-BETA-001
"""

import argparse
import sys

from backend.api.invites_db import init_db, create_invite, list_invites, reset_invite


STATUS_ICON = {"sent": "📨", "used": "✅"}


def cmd_create(args):
    init_db()
    if create_invite(args.code, args.email):
        print(f"✓ Código creado:  {args.code.upper()}  →  {args.email.lower()}")
    else:
        print(f"✗ Ya existe la pareja {args.code.upper()} / {args.email.lower()}")
        sys.exit(1)


def cmd_list(_args):
    init_db()
    invites = list_invites()
    if not invites:
        print("No hay códigos registrados.")
        return
    print(f"{'ESTADO':8}  {'CÓDIGO':22}  {'EMAIL':35}  {'FECHA USO'}")
    print("─" * 80)
    for inv in invites:
        icon   = STATUS_ICON.get(inv["status"], "❓")
        status = f"{icon} {inv['status']}"
        used   = inv["used_at"] or "—"
        print(f"{status:10}  {inv['code']:22}  {inv['email']:35}  {used}")


def cmd_reset(args):
    init_db()
    if reset_invite(args.code, args.email):
        print(f"✓ Reseteado a 'sent':  {args.code.upper()}  →  {args.email.lower()}")
    else:
        print(f"✗ No se encontró la pareja {args.code.upper()} / {args.email.lower()}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Gestión de códigos de invitación — Book Factory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMANDO")

    p_create = sub.add_parser("create", help="Crear un nuevo código de invitación")
    p_create.add_argument("--email", required=True, help="Email del destinatario")
    p_create.add_argument("--code",  required=True, help="Código de acceso (ej. OBRA-BETA-001)")

    sub.add_parser("list", help="Listar todos los códigos")

    p_reset = sub.add_parser("reset", help="Resetear un código a 'sent' (permite reutilizarlo)")
    p_reset.add_argument("--email", required=True)
    p_reset.add_argument("--code",  required=True)

    args = parser.parse_args()

    if args.command == "create":
        cmd_create(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "reset":
        cmd_reset(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
