"""
BookState — Esquema de estado del grafo LangGraph  v2.0

Cambios v2.0:
  - plan_revision (int): contador de rechazos del plan en el Arquitecto.
  - editor_rejection_count (int): contador de rechazos por capítulo en el Editor.
  - system_warning (str): mensajes de advertencia cuando se supera un límite de ciclo.
  - cover_brief_path (str): ruta al brief de portada guardado por el Publicador.
  - current_agent tipado como str (compatible con AgentName enum — str subclass).
  - Comentarios de book_status actualizados con todos los valores posibles.
  - layouter_notes eliminado (no se usa en ningún agente — era campo huérfano).
  - messages eliminado: el historial de conversación se gestiona en la capa API,
    no en el estado del grafo. Simplifica el estado y evita crecimiento ilimitado.
"""

from typing import Annotated, List, Optional, TypedDict


class BookState(TypedDict, total=False):

    # ── Input ──────────────────────────────────────────────────────────────
    idea: str

    # ── Metadatos del libro (completados por el Arquitecto) ────────────────
    title: str
    subtitle: str
    genre: str
    target_audience: str
    tone: str
    writing_style: str
    num_chapters: int
    chapter_outlines: List[dict]  # cada item incluye arc_role desde v2.1
    book_arc: dict                # {opening, development, resolution} — v2.1

    # ── Progreso general ───────────────────────────────────────────────────
    # book_status: "planning" | "writing" | "editing" | "formatting" |
    #              "publishing" | "complete"
    book_status: str

    # current_agent: valor del enum AgentName (str subclass):
    #   "architect" | "writer" | "editor" | "layouter" | "publisher" | "complete"
    current_agent: str

    current_chapter_index: int

    # ── Control de ciclos (nuevo en v2.0) ──────────────────────────────────
    # Número de veces que el usuario ha rechazado el plan del Arquitecto
    plan_revision: int

    # Número de veces que el Editor ha rechazado el capítulo actual
    editor_rejection_count: int

    # Mensaje de advertencia cuando un agente supera su límite de reintentos
    system_warning: str

    # ── Trabajo del capítulo actual ────────────────────────────────────────
    current_draft: str
    current_chapter_title: str
    draft_revision: int

    # ── Feedback entre agentes ─────────────────────────────────────────────
    user_feedback_on_draft: str
    editor_feedback: str
    # Historial acumulado de rechazos del plan (v2.1)
    # Cada elemento es el feedback de una revisión, en orden cronológico
    plan_feedback_history: List[str]
    # Historial acumulado de reescrituras del capítulo actual (v2.2)
    # Se resetea al cambiar de capítulo o al aprobar
    chapter_rewrite_history: List[str]
    # Historial acumulado de rechazos del Editor (v2.2)
    # Se resetea al aprobar el capítulo o al cambiar al siguiente
    editor_feedback_history: List[str]
    editor_approved: bool

    # ── Datos del autor (recopilados por el Arquitecto en la entrevista) ─────
    # Guardados al inicio para no interrumpir la generación al final
    author_name: str
    author_email: str
    author_bio: str
    author_cover_preferences: str
    author_acknowledgment_context: str
    interview_answers: str          # guardadas para reescrituras del plan

    # ── Modo de revisión de capítulos (elegido por el usuario tras aprobar el plan) ──
    # True → el usuario revisa y aprueba cada capítulo antes de continuar
    # False → el sistema genera todos los capítulos sin interrupción (modo automático)
    review_chapters: bool

    # ── Humanización de la escritura (v2.3) ───────────────────────────────
    # True  → el Escritor activa instrucciones de imperfección humana:
    #   simetría rota, errores intencionales, diálogos con ruido, ambigüedad.
    # False → comportamiento estándar sin instrucciones adicionales (default).
    # Configurable por libro — el Arquitecto pregunta al usuario y persiste aquí.
    humanize_writing: bool

    # ── Feedback del Maquetador al Escritor (v2.2) ────────────────────────
    # Cuando el capítulo supera el límite del género, el Maquetador lo devuelve
    layouter_feedback: str
    layouter_rejection_count: int

    # ── Preferencias de formato (preguntadas una vez, reutilizadas) ────────
    format_preferences: str

    # ── Contexto visual del libro (generado una vez, persistido entre capítulos) ──
    # Contiene: Época/lugar, Personajes visuales, Estilo artístico, Prohibiciones.
    # Lo genera el Maquetador en el capítulo 1 y lo reutiliza en los siguientes
    # para que todos los [IMAGEN:] sean coherentes entre sí.
    visual_context: str

    # ── Capítulos completados ──────────────────────────────────────────────
    # Cada elemento: {index, title, content, formatted_content, docx_path, layout_notes}
    approved_chapters: List[dict]

    # ── Contenido generado por el Publicador (guardado para regeneración) ──
    prefacio: str
    pagina_legal: str
    agradecimientos: str
    sobre_el_autor: str       # sección editorial completa (≠ author_bio cruda)

    # ── Output final ───────────────────────────────────────────────────────
    output_dir: str
    final_book_path: str

    # Ruta al brief de portada (archivo separado, no incluido en el libro)
    cover_brief_path: str

    # Imagen de referencia visual subida por el usuario (opcional).
    # Si está presente, Ideogram usa remix en lugar de generate para portada
    # e ilustraciones de capítulo, manteniendo coherencia de estilo.
    reference_image_path: str

    # Número de imágenes interiores por capítulo elegido por el usuario.
    # 0  → sin imágenes interiores (solo portada)
    # 1  → una imagen por capítulo (típico adulto con imágenes o juvenil)
    # 2  → dos imágenes por capítulo (típico infantil)
    # El Arquitecto pregunta al usuario y parsea la respuesta.
    # El Maquetador lo usa en _filter_image_blocks() para respetar el límite.
    images_per_chapter: int

    # ── Formato de salida del libro (elegido por el usuario) ─────────────────
    # "docx"     → Microsoft Word (default)
    # "epub"     → EPUB (estándar ebooks — Kindle, Apple Books, Kobo)
    # "html"     → HTML autocontenido con imágenes embebidas en base64
    # "markdown" → Markdown plano con imágenes como referencias
    output_format: str
