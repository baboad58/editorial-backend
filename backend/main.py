"""
Book Factory – Punto de entrada CLI  v2.0
Uso: python -m backend.main

Cambios v2.0:
  - initial_state corregido: book_status="planning" (antes "interviewing" — valor
    que no existe en el enum BookState v2); añadidos plan_revision,
    editor_rejection_count y system_warning faltantes.
  - display_interrupt: chapter_review muestra las tres acciones (approve/edit/rewrite)
    y guía al usuario claramente. Se eliminó "layouter_question" y "final_approval"
    que ya no existen en los agentes v2.
  - get_user_input para chapter_review: menú interactivo que construye el JSON
    correcto según la acción elegida por el usuario.
  - system_warning del estado se muestra al usuario como aviso informativo,
    sin interrumpir el flujo.
  - Errores capturan PermanentError de retry.py para mostrar mensajes en español.
  - Logging no reconfigura basicConfig (ya lo hace utils.py al importarse).
"""

import json
import os
import sys
import uuid

from dotenv import load_dotenv
from langgraph.types import Command
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

load_dotenv()

# Forzar UTF-8 en Windows para que Rich pueda renderizar emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

console = Console(legacy_windows=False)

AGENT_COLORS = {
    "Arquitecto": "blue",
    "Escritor":   "yellow",
    "Editor":     "red",
    "Maquetador": "cyan",
    "Publicador": "magenta",
}
AGENT_EMOJIS = {
    "Arquitecto": "🏛️",
    "Escritor":   "✍️",
    "Editor":     "🔍",
    "Maquetador": "📐",
    "Publicador": "🚀",
}


# ── Renderizado de interrupts ─────────────────────────────────────────────────

def _agent_panel(agent: str, content: str, hint: str = "") -> Panel:
    color = AGENT_COLORS.get(agent, "white")
    emoji = AGENT_EMOJIS.get(agent, "🤖")
    body  = content
    if hint:
        body += f"\n\n[dim italic]{hint}[/dim italic]"
    return Panel(
        body,
        title=f"[bold {color}]{emoji}  {agent}[/bold {color}]",
        border_style=color,
        padding=(1, 2),
    )


def display_interrupt(interrupt_value: dict) -> None:
    """Renderiza el interrupt en el terminal según su tipo."""
    itype  = interrupt_value.get("type", "generic")
    agent  = interrupt_value.get("agent", "Sistema")
    content = interrupt_value.get("content", "")
    hint   = interrupt_value.get("hint", "")

    if itype == "interview":
        console.print()
        console.print(_agent_panel(agent, content, hint))

    elif itype == "plan_approval":
        console.print()
        console.rule("[bold green]📋 Plan del Libro")
        console.print(_agent_panel(agent, content, ""))
        # Mostrar acciones disponibles
        actions = interrupt_value.get("actions", {})
        if actions:
            console.print()
            console.print("[bold cyan]Acciones disponibles:[/bold cyan]")
            for key, desc in actions.items():
                console.print(f"  [bold]{key}[/bold] → {desc}")

    elif itype == "chapter_review":
        chapter_num = interrupt_value.get("chapter_num", "?")
        total       = interrupt_value.get("total_chapters", "?")
        title       = interrupt_value.get("chapter_title", "")
        revision    = interrupt_value.get("revision", 0)
        draft       = interrupt_value.get("draft", "")
        note        = interrupt_value.get("note", "")
        word_count  = interrupt_value.get("word_count", 0)
        word_target = interrupt_value.get("word_target", 0)

        console.print()
        console.rule(
            f"[bold yellow]✍️  Capítulo {chapter_num}/{total}: {title}  "
            f"| {word_count}/{word_target} palabras"
        )
        if note:
            console.print(f"[dim]{note}[/dim]\n")

        # Mostrar borrador — truncar si es muy largo para el terminal
        draft_display = (
            draft if len(draft) <= 3000
            else draft[:3000] + "\n\n[dim]… (texto completo generado — continúa)[/dim]"
        )
        console.print(Panel(
            draft_display,
            title=f"[bold white]Borrador — Revisión #{revision}[/bold white]",
            border_style="white",
            padding=(1, 2),
        ))

        # Mostrar las tres acciones disponibles
        console.print()
        console.print("[bold cyan]Acciones disponibles:[/bold cyan]")
        actions = interrupt_value.get("actions", {})
        for key, desc in actions.items():
            console.print(f"  [bold]{key}[/bold] → {desc}")

    elif itype == "author_info":
        console.print()
        console.rule("[bold magenta]🚀 Fase de Publicación")
        console.print(_agent_panel(agent, content, hint))

    else:
        # Tipo desconocido — mostrar contenido genérico
        console.print()
        display_content = content or str(interrupt_value)
        console.print(_agent_panel(agent, display_content, hint))


def display_system_warning(message: str) -> None:
    """Muestra un aviso de sistema (límite de revisiones, etc.) sin interrumpir el flujo."""
    console.print()
    console.print(Panel(
        f"[yellow]{message}[/yellow]",
        title="[bold yellow]⚠️  Aviso del Sistema[/bold yellow]",
        border_style="yellow",
        padding=(0, 2),
    ))


# ── Captura de respuesta del usuario ─────────────────────────────────────────

def get_user_input(interrupt_value: dict) -> str:
    """
    Obtiene la respuesta del usuario según el tipo de interrupt.

    Para chapter_review: muestra un menú con las tres acciones y construye
    el JSON correcto que el Escritor v2.1 espera.
    Para el resto: entrada de texto libre.
    """
    itype = interrupt_value.get("type", "generic")
    console.print()

    if itype == "chapter_review":
        return _get_chapter_review_response(interrupt_value)

    if itype == "plan_approval":
        return _get_plan_approval_response(interrupt_value)

    try:
        return console.input("[bold cyan]▶  Tu respuesta:[/bold cyan] ")
    except (KeyboardInterrupt, EOFError):
        console.print("\n\n[bold red]Sesión cancelada.[/bold red]")
        sys.exit(0)


def _get_plan_approval_response(interrupt_value: dict) -> str:
    """
    Menú interactivo para la aprobación del plan.
    Retorna el JSON que _parse_plan_approval() en architect.py espera.

    Acciones:
      approve  → {"action": "approve"}
      edit     → {"action": "edit", "plan_data": <plan modificado>}
      rewrite  → {"action": "rewrite", "feedback": "<instrucciones>"}
    """
    plan_data = interrupt_value.get("plan_data", {})

    console.print()
    console.print("[bold cyan]Acciones disponibles:[/bold cyan]")
    console.print("  [bold]approve[/bold]  → Aprobar el plan y comenzar a escribir")
    console.print("  [bold]edit[/bold]     → Modificar capítulos específicos del plan")
    console.print("  [bold]rewrite[/bold]  → Pedir al Arquitecto que regenere con instrucciones")

    while True:
        try:
            choice = console.input(
                "\n[bold cyan]Elige una acción [/bold cyan]"
                "[cyan](approve / edit / rewrite):[/cyan] "
            ).strip().lower()
        except (KeyboardInterrupt, EOFError):
            console.print("\n\n[bold red]Sesión cancelada.[/bold red]")
            sys.exit(0)

        if choice in ("approve", "a", "aprobar", "sí", "si", "ok"):
            return json.dumps({"action": "approve"})

        elif choice in ("edit", "e", "editar"):
            return _edit_plan_interactively(plan_data)

        elif choice in ("rewrite", "r", "regenerar", "cambios"):
            try:
                feedback = console.input(
                    "[bold cyan]▶  Instrucciones para el Arquitecto:[/bold cyan] "
                ).strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]Cancelado. Volviendo al menú.[/yellow]")
                continue
            if not feedback:
                console.print("[yellow]Las instrucciones no pueden estar vacías.[/yellow]")
                continue
            return json.dumps({"action": "rewrite", "feedback": feedback})

        else:
            console.print(
                "[yellow]Opción no reconocida. Escribe:[/yellow] "
                "[bold]approve[/bold], [bold]edit[/bold] o [bold]rewrite[/bold]"
            )


def _edit_plan_interactively(plan_data: dict) -> str:
    """
    Permite al usuario editar capítulos específicos del plan.
    Muestra cada capítulo y pregunta si quiere modificarlo.
    Retorna JSON con el plan_data modificado.
    """
    import copy
    edited = copy.deepcopy(plan_data)
    chapters = edited.get("chapter_outlines", [])

    console.print()
    console.print("[bold]Edición quirúrgica del plan[/bold] — capítulo por capítulo.")
    console.print("[dim]Presiona Enter para conservar el valor actual.[/dim]\n")

    # Editar metadatos del libro
    for field, label in [
        ("title",           "Título"),
        ("subtitle",        "Subtítulo"),
        ("target_audience", "Audiencia objetivo"),
        ("tone",            "Tono"),
    ]:
        current = edited.get(field, "")
        try:
            val = console.input(
                f"[cyan]{label}[/cyan] [dim](actual: {current[:60]})[/dim]: "
            ).strip()
        except (KeyboardInterrupt, EOFError):
            break
        if val:
            edited[field] = val

    # Editar capítulos
    console.print()
    for i, ch in enumerate(chapters):
        console.print(
            f"[bold]Capítulo {i + 1}:[/bold] {ch['title']} "
            f"[dim]({ch.get('arc_role', '')})[/dim]"
        )
        try:
            modify = console.input(
                "  ¿Modificar este capítulo? [dim](Enter = no)[/dim]: "
            ).strip().lower()
        except (KeyboardInterrupt, EOFError):
            break

        if modify not in ("s", "si", "sí", "y", "yes", "1"):
            continue

        for field, label in [
            ("title",   "  Título"),
            ("summary", "  Resumen"),
            ("arc_role","  Rol en el arco"),
        ]:
            current = ch.get(field, "")
            try:
                val = console.input(
                    f"[cyan]{label}[/cyan] [dim](actual: {current[:60]})[/dim]: "
                ).strip()
            except (KeyboardInterrupt, EOFError):
                break
            if val:
                ch[field] = val

        # Editar key_points
        try:
            kp_raw = console.input(
                f"  [cyan]Puntos clave[/cyan] [dim](actual: {str(ch.get('key_points', []))[:60]}) "
                f"— separados por | o Enter para conservar[/dim]: "
            ).strip()
        except (KeyboardInterrupt, EOFError):
            kp_raw = ""
        if kp_raw:
            ch["key_points"] = [k.strip() for k in kp_raw.split("|") if k.strip()]

    console.print("\n[green]Plan editado. Enviando al Arquitecto para validación…[/green]")
    return json.dumps({"action": "edit", "plan_data": edited})


def _get_chapter_review_response(interrupt_value: dict) -> str:
    """
    Menú interactivo para la revisión de capítulo.
    Retorna el JSON que _parse_user_response() en writer.py espera.

    Acciones:
      approve  → {"action": "approve"}
      edit     → {"action": "edit", "content": "<texto completo editado>"}
      rewrite  → {"action": "rewrite", "feedback": "<instrucciones>"}
    """
    draft = interrupt_value.get("draft", "")

    while True:
        try:
            choice = console.input(
                "\n[bold cyan]Elige una acción [/bold cyan]"
                "[cyan](approve / edit / rewrite):[/cyan] "
            ).strip().lower()
        except (KeyboardInterrupt, EOFError):
            console.print("\n\n[bold red]Sesión cancelada.[/bold red]")
            sys.exit(0)

        if choice in ("approve", "a", "aprobar", "sí", "si", "ok"):
            return json.dumps({"action": "approve"})

        elif choice in ("edit", "e", "editar"):
            console.print(
                "\n[dim]Pega el texto completo del capítulo editado y termina con una línea "
                "que contenga solo: [bold]FIN[/bold][/dim]\n"
            )
            lines = []
            try:
                while True:
                    line = input()
                    if line.strip().upper() == "FIN":
                        break
                    lines.append(line)
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]Edición cancelada. Volviendo al menú.[/yellow]")
                continue

            edited = "\n".join(lines).strip()
            if not edited:
                console.print("[yellow]Sin contenido. Usando borrador original.[/yellow]")
                edited = draft
            return json.dumps({"action": "edit", "content": edited})

        elif choice in ("rewrite", "r", "reescribir", "cambios"):
            try:
                feedback = console.input(
                    "[bold cyan]▶  Instrucciones para el Escritor:[/bold cyan] "
                ).strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]Cancelado. Volviendo al menú.[/yellow]")
                continue

            if not feedback:
                console.print("[yellow]Las instrucciones no pueden estar vacías.[/yellow]")
                continue
            return json.dumps({"action": "rewrite", "feedback": feedback})

        else:
            console.print(
                "[yellow]Opción no reconocida. Escribe:[/yellow] "
                "[bold]approve[/bold], [bold]edit[/bold] o [bold]rewrite[/bold]"
            )


# ── Helpers del grafo ─────────────────────────────────────────────────────────

def _get_interrupt_value(graph, config: dict) -> dict | None:
    """Extrae el valor del interrupt del estado del grafo."""
    state = graph.get_state(config)
    for task in state.tasks:
        if hasattr(task, "interrupts") and task.interrupts:
            iv = task.interrupts[0]
            return iv.value if hasattr(iv, "value") else iv
    return None


def _check_system_warning(graph, config: dict) -> str:
    """Lee system_warning del estado y lo retorna si existe."""
    try:
        return graph.get_state(config).values.get("system_warning", "")
    except Exception:
        return ""


# ── Loop principal CLI ────────────────────────────────────────────────────────

def run_cli():
    console.print()
    console.print(Panel.fit(
        "[bold magenta]BOOK FACTORY[/bold magenta]\n"
        "[white]Sistema de Generación de Libros con Inteligencia Artificial[/white]\n"
        "[dim]Powered by Claude · LangGraph · python-docx[/dim]",
        border_style="magenta",
        padding=(1, 4),
    ))
    console.print()

    # Verificar API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print(
            "[bold red]ERROR:[/bold red] No se encontró ANTHROPIC_API_KEY en el archivo .env\n"
            "Copia [bold].env.example[/bold] → [bold].env[/bold] y configura tu API key."
        )
        sys.exit(1)

    idea = console.input("[bold]💡 ¿Cuál es la idea para tu libro? [/bold]").strip()
    if not idea:
        console.print("[red]Por favor, ingresa una idea para comenzar.[/red]")
        sys.exit(1)

    # Construir grafo
    from backend.graph.builder import build_graph
    from backend.graph.retry import PermanentError
    from backend.graph.error_handler import handle_error

    graph      = build_graph()
    session_id = str(uuid.uuid4())
    config     = {"configurable": {"thread_id": session_id}}
    output_dir = os.getenv("OUTPUT_DIR", "output")

    console.print(f"\n[dim]Session ID: {session_id}[/dim]")

    initial_state = {
        "idea":                   idea,
        "book_status":            "planning",   # v2: "planning" no "interviewing"
        "current_chapter_index":  0,
        "draft_revision":         0,
        "plan_revision":          0,            # v2: nuevo campo
        "editor_rejection_count": 0,            # v2: nuevo campo
        "plan_feedback_history":  [],           # v2.1: historial acumulado
        "chapter_rewrite_history": [],          # v2.2: historial reescrituras
        "editor_feedback_history":  [],          # v2.2: historial rechazos editor
        "review_chapters":               False,  # se fija en el interrupt review_mode del Arquitecto
        "layouter_feedback":             "",     # v2.2: feedback del Maquetador
        "layouter_rejection_count":      0,     # v2.2: intentos de reestructuración
        # Datos del autor (se llenan en la entrevista del Arquitecto)
        "author_name":                   "",
        "author_email":                  "",
        "author_bio":                    "",
        "author_cover_preferences":      "",
        "author_acknowledgment_context": "",
        "interview_answers":             "",
        "approved_chapters":      [],
        "editor_approved":        False,
        "visual_context":         "",
        "output_dir":             output_dir,
    }

    current_input = initial_state

    console.print()
    console.rule("[dim]Iniciando sistema de agentes[/dim]")

    # Interrupt actual para saber cómo pedir respuesta
    current_interrupt: dict = {}

    while True:
        # ── Ejecutar el grafo hasta el próximo interrupt ───────────────
        try:
            for chunk in graph.stream(current_input, config, stream_mode="updates"):
                # Mostrar qué agente está trabajando
                if "__interrupt__" in chunk:
                    break
                for node_name in chunk:
                    if node_name not in ("__interrupt__",):
                        agent_label = {
                            "architect": "Arquitecto",
                            "writer":    "Escritor",
                            "editor":    "Editor",
                            "layouter":  "Maquetador",
                            "publisher": "Publicador",
                        }.get(node_name, node_name)
                        console.print(f"\n[dim]⚙  {agent_label} trabajando…[/dim]")

        except PermanentError as pe:
            console.print()
            console.print(Panel(
                str(pe),
                title="[bold red]❌ Error del Sistema[/bold red]",
                border_style="red",
                padding=(1, 2),
            ))
            sys.exit(1)

        except Exception as e:
            error_info = handle_error(e, context="CLI/stream")
            console.print()
            console.print(Panel(
                error_info.user_message,
                title="[bold red]❌ Error[/bold red]",
                border_style="red",
                padding=(1, 2),
            ))
            if not error_info.retryable:
                sys.exit(1)
            # Error reintentable — el retry ya ocurrió dentro del agente;
            # si llegó aquí es que se agotaron los reintentos
            sys.exit(1)

        # ── Verificar estado ───────────────────────────────────────────
        state = graph.get_state(config)

        # Mostrar system_warning si existe
        warning = state.values.get("system_warning", "")
        if warning:
            display_system_warning(warning)

        # Libro completado
        if not state.next:
            final_state = state.values
            console.print()
            console.rule("[bold green]✅ Libro Completado")
            console.print(Panel(
                f"[bold green]¡Tu libro ha sido generado exitosamente![/bold green]\n\n"
                f"📖 Título:       [bold]{final_state.get('title', '')}[/bold]\n"
                f"📁 Libro final:  [bold]{final_state.get('final_book_path', 'Ver carpeta output/')}[/bold]\n"
                f"🎨 Brief portada:[bold]{final_state.get('cover_brief_path', '—')}[/bold]\n"
                f"📂 Carpeta:      [bold]{output_dir}/[/bold]",
                border_style="green",
                padding=(1, 2),
            ))
            break

        # ── Obtener interrupt y mostrarlo ──────────────────────────────
        interrupt_value = _get_interrupt_value(graph, config)

        if interrupt_value is None:
            console.print("[yellow]El sistema terminó sin interrupción esperada.[/yellow]")
            break

        current_interrupt = interrupt_value
        display_interrupt(interrupt_value)

        # ── Obtener respuesta del usuario y continuar ──────────────────
        user_input    = get_user_input(interrupt_value)
        current_input = Command(resume=user_input)


if __name__ == "__main__":
    run_cli()
