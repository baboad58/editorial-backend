"""
LangGraph graph builder  v2.0
Define nodos, aristas, lógica de ruteo y compila el grafo con SqliteSaver.

Cambios v2.0:
  - route_after_architect(): maneja el nuevo estado "planning" además de "writing".
  - route_after_editor(): usa editor_approved (correcto) pero también cubre el
    estado "formatting" que escribe el Editor al aprobar, evitando el dead-end
    si book_status="formatting" con editor_approved=True.
  - route_after_layouter(): cubre correctamente "publishing", "writing" y el
    fallback a "writer" para cualquier otro estado inesperado.
  - route_after_writer(): maneja el estado "editing" y ciclo "writing".
  - _safe_db_path(): crea el directorio del checkpoint si no existe,
    evitando FileNotFoundError al iniciar con rutas anidadas.
  - Logging de arranque del grafo.
"""

import logging
import os
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from backend.agents.architect import architect_node
from backend.agents.editor import editor_node
from backend.agents.layouter import layouter_node
from backend.agents.publisher import publisher_node
from backend.agents.writer import writer_node
from backend.graph.state import BookState

logger = logging.getLogger("editorial_system")


# ── Funciones de ruteo ────────────────────────────────────────────────────────

def route_after_architect(state: BookState) -> str:
    """
    Después del Arquitecto:
    - Plan aprobado (book_status="writing")  → writer
    - Plan rechazado (book_status="planning") → architect (replanificación)
    """
    status = state.get("book_status", "")
    if status == "writing":
        return "writer"
    # "planning" o cualquier otro valor → re-loop al arquitecto
    return "architect"


def route_after_writer(state: BookState) -> str:
    """
    Después del Escritor (el usuario revisó vía interrupt):
    - Usuario aprobó borrador (book_status="editing") → editor
    - Usuario quiere cambios (book_status="writing")  → writer (revisión)
    """
    status = state.get("book_status", "")
    if status == "editing":
        return "editor"
    return "writer"


def route_after_editor(state: BookState) -> str:
    """
    Después del Editor (revisión automatizada):
    - Capítulo aprobado (editor_approved=True) → layouter
    - Capítulo rechazado (editor_approved=False) → writer (revisión)

    Nota: el Editor escribe book_status="formatting" al aprobar.
    El routing se basa en editor_approved, no en book_status, para
    evitar que un estado "formatting" inesperado quede sin ruta.
    """
    if state.get("editor_approved", False):
        return "layouter"
    return "writer"


def route_after_layouter(state: BookState) -> str:
    """
    Después del Maquetador:
    - Todos los capítulos formateados (book_status="publishing") → publisher
    - Problema estructural o más capítulos (book_status="writing") → writer
    - Cualquier otro estado inesperado → writer (fallback seguro)
    """
    status = state.get("book_status", "")
    if status == "publishing":
        return "publisher"
    # "writing" (próximo capítulo o problema estructural) o fallback
    return "writer"


# ── Constructor del grafo ─────────────────────────────────────────────────────

def _safe_db_path() -> str:
    """
    Retorna la ruta al archivo SQLite de checkpoints.
    Crea el directorio padre si no existe para evitar FileNotFoundError.
    """
    db_path = os.getenv("CHECKPOINT_DB", "output/checkpoints.db")
    parent  = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return db_path


def build_graph():
    """
    Construye y compila el grafo LangGraph de la Book Factory.
    Usa SqliteSaver para checkpointing persistente — sobrevive reinicios del servidor
    y reconexiones del cliente.

    Retorna el grafo compilado listo para invocar.
    """
    builder = StateGraph(BookState)

    # ── Nodos ──────────────────────────────────────────────────────────────
    builder.add_node("architect", architect_node)
    builder.add_node("writer",    writer_node)
    builder.add_node("editor",    editor_node)
    builder.add_node("layouter",  layouter_node)
    builder.add_node("publisher", publisher_node)

    # ── Arista de entrada ──────────────────────────────────────────────────
    builder.add_edge(START, "architect")

    # ── Aristas condicionales ──────────────────────────────────────────────
    builder.add_conditional_edges(
        "architect",
        route_after_architect,
        {"architect": "architect", "writer": "writer"},
    )
    builder.add_conditional_edges(
        "writer",
        route_after_writer,
        {"writer": "writer", "editor": "editor"},
    )
    builder.add_conditional_edges(
        "editor",
        route_after_editor,
        {"writer": "writer", "layouter": "layouter"},
    )
    builder.add_conditional_edges(
        "layouter",
        route_after_layouter,
        {"writer": "writer", "publisher": "publisher"},
    )

    # ── Arista de salida ───────────────────────────────────────────────────
    builder.add_edge("publisher", END)

    # ── Checkpointer ──────────────────────────────────────────────────────
    db_path = _safe_db_path()
    conn         = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    graph = builder.compile(checkpointer=checkpointer)

    logger.info(
        f"[Builder] Grafo compilado — checkpoints en: {db_path}"
    )
    return graph
