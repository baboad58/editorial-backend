"""
Utilidades compartidas — Sistema Editorial Multi-Agente
Centraliza: extracción JSON, validación de extensión, logging y constantes globales.

Re-exporta para que todos los agentes importen desde un único lugar:
  from backend.graph.utils import (
      retry_llm_call, PermanentError, handle_error,   # reintentos y errores
      AgentName, MAX_PLAN_REVISIONS, ...,              # constantes
      extract_json, check_word_count, ...,             # helpers
  )
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Union


# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("editorial_system")


# ── Constantes de ciclo ───────────────────────────────────────────────────────
MAX_PLAN_REVISIONS     = 3
MAX_CHAPTER_REVISIONS  = 5
MAX_EDITOR_REJECTIONS  = 3


# ── Enum de agentes ──────────────────────────────────────────────────────────
class AgentName(str, Enum):
    ARCHITECT = "architect"
    WRITER    = "writer"
    EDITOR    = "editor"
    LAYOUTER  = "layouter"
    PUBLISHER = "publisher"
    COMPLETE  = "complete"


# ── Router Dinámico de modelos LLM ───────────────────────────────────────────
# Asigna el modelo óptimo a cada agente según su complejidad cognitiva.
# Puede sobrescribirse con variables de entorno individuales.

_AGENT_MODEL_CONFIG: dict[str, str] = {
    # Alta complejidad — claude-sonnet-4-6 (razonamiento, creatividad, revisión)
    AgentName.ARCHITECT.value: os.getenv("MODEL_ARCHITECT", "claude-sonnet-4-6"),  # Ideación
    AgentName.WRITER.value:    os.getenv("MODEL_WRITER",    "claude-sonnet-4-6"),  # Escritura Creativa
    AgentName.EDITOR.value:    os.getenv("MODEL_EDITOR",    "claude-sonnet-4-6"),  # Revisión Final
    # Baja complejidad — claude-haiku-4-5 (tareas mecánicas, formato, empaquetado)
    AgentName.LAYOUTER.value:  os.getenv("MODEL_LAYOUTER",  "claude-haiku-4-5-20251001"),   # Formato
    AgentName.PUBLISHER.value: os.getenv("MODEL_PUBLISHER", "claude-haiku-4-5-20251001"),   # Empaquetado
    # Extensiones futuras del sistema (ya mapeadas para cuando se implementen)
    "spell_checker":           os.getenv("MODEL_SPELL",     "claude-haiku-4-5-20251001"),   # Corrección Ortográfica
    "translator":              os.getenv("MODEL_TRANSLATOR","claude-haiku-4-5-20251001"),   # Traducción Técnica
}


def get_llm_for_agent(agent_name: str, **kwargs: Any) -> Any:
    """
    Router Dinámico: retorna un ChatAnthropic configurado con el modelo
    asignado al agente según _AGENT_MODEL_CONFIG.

    Uso en cada agente:
        from backend.graph.utils import get_llm_for_agent, AgentName
        llm = get_llm_for_agent(AgentName.WRITER.value, temperature=0.7, max_tokens=8192)

    Los kwargs (temperature, max_tokens) se pasan directamente a ChatAnthropic.
    Si el agente no está en el mapa, usa ANTHROPIC_MODEL como fallback.
    """
    from langchain_anthropic import ChatAnthropic  # import local para evitar ciclos

    model = _AGENT_MODEL_CONFIG.get(
        agent_name,
        os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
    )
    logger.debug(f"[LLM Router] Agente '{agent_name}' → modelo '{model}'")
    return ChatAnthropic(model=model, **kwargs)


# ── Prompt Caching — Anthropic ephemeral cache ───────────────────────────────

def cached_system_message(text: str) -> Any:
    """
    Retorna un SystemMessage con cache_control ephemeral en el bloque de texto.

    La API de Anthropic cachea el contenido si supera los 1024 tokens (~750 palabras).
    En llamadas repetidas al mismo SystemMessage (ej: mismo agente procesando
    múltiples capítulos o el Publisher con 5 llamadas seguidas), ahorra hasta
    el 90 % de los tokens de entrada del system prompt.

    Si el prompt es demasiado corto para caching (< 1024 tokens), la API simplemente
    ignora el campo — no hay error, no hay cambio de comportamiento.

    Uso:
        from backend.graph.utils import cached_system_message
        response = retry_llm_call(llm, [
            cached_system_message(SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ], context="Agente/tarea")
    """
    from langchain_core.messages import SystemMessage  # import local para evitar ciclos en tests
    return SystemMessage(content=[{
        "type": "text",
        "text": text,
        "cache_control": {"type": "ephemeral"},
    }])


# ── Context Cleaning — limpieza de feedback inter-agente ─────────────────────

def trim_agent_feedback(text: str, max_chars: int = 450) -> str:
    """
    Trunca entradas de historial de feedback para mantener el contexto compacto.

    Cuando el Editor o el Maquetador rechazan un capítulo, el reporte puede
    superar los 600-800 caracteres. Al acumular 2-3 rechazos en el historial,
    el prompt del Escritor recibe ~1500 caracteres de metadatos del agente anterior.
    Esta función mantiene los puntos más relevantes (inicio del reporte).

    Uso:
        entries = [trim_agent_feedback(e) for e in feedback_history]
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…[truncado]"


# ── Bloques de contenido para el maquetador ──────────────────────────────────
@dataclass
class TextBlock:
    content: str

@dataclass
class SubtitleBlock:
    text: str

@dataclass
class ImageBlock:
    description: str

ContentBlock = Union[TextBlock, SubtitleBlock, ImageBlock]


# ── Extracción robusta de JSON ────────────────────────────────────────────────
class JSONExtractionError(ValueError):
    pass


def extract_json(text: str) -> dict:
    """
    Extrae el primer objeto JSON válido de un texto que puede contener
    bloques markdown, texto previo o posterior.
    Intenta tres estrategias antes de lanzar JSONExtractionError.
    """
    # Estrategia 1: bloque ```json ... ```
    match = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Estrategia 2: cualquier bloque ``` ... ```
    match = re.search(r"```\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Estrategia 3: buscar {} balanceado más externo
    depth, start = 0, -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = -1  # reintentar con el siguiente {

    raise JSONExtractionError(
        f"No se encontró JSON válido en el texto: {text[:300]}…"
    )


# ── Validación de extensión de capítulo ──────────────────────────────────────
MINIMUM_WORD_RATIO = 0.70   # El capítulo debe tener al menos el 70% del objetivo


def get_genre_word_limits(genre: str) -> tuple[int, int]:
    """
    Retorna (min_palabras, max_palabras) recomendadas para el género.

    Usado por _validate_plan (architect), el Editor y el Maquetador.

    Rangos por categoría:
      Álbum ilustrado / infantil ilustrado : 200 –  900
      Infantil / juvenil (sin ilustrar)    : 500 – 1800
      Young adult (12+)                    : 1500 – 4000
      Ficción adulta                       : 2000 – 5000
      Académico / ensayo                   : 2000 – 4500
      No-ficción práctica (default)        : 1500 – 4000
    """
    g = genre.lower()

    # Álbum ilustrado / infantil ilustrado — muy corto por página
    if any(k in g for k in ["ilustrad", "álbum", "album", "picture"]):
        return (200, 900)

    # Young adult — más extenso que infantil pero menos que adulto
    if any(k in g for k in ["young adult", "ya ", " ya", "juvenil adulto"]):
        return (1500, 4000)

    # Infantil / juvenil general
    if any(k in g for k in ["infantil", "juvenil"]):
        return (500, 1800)

    # Ficción adulta — rango amplio
    if any(k in g for k in ["novela", "cuento", "thriller", "romance", "fantasía",
                             "ficción", "horror", "aventura", "misterio"]):
        return (2000, 5000)

    # Académico / ensayo
    if any(k in g for k in ["académico", "académica", "ensayo", "científico",
                             "histórico", "filosófico", "investigación", "divulgación"]):
        return (2000, 4500)

    # No-ficción práctica (default)
    return (1500, 4000)



def check_word_count(text: str, target: int) -> tuple[int, bool]:
    """
    Retorna (conteo_real, cumple_mínimo_70%).
    El conteo usa split() — suficientemente preciso para control editorial.
    """
    count = len(text.split())
    meets = count >= int(target * MINIMUM_WORD_RATIO)
    return count, meets


# ── Parser de texto formateado → bloques tipados ─────────────────────────────
def parse_formatted_text(text: str) -> list[ContentBlock]:
    """
    Convierte texto con marcadores [SUBTÍTULO: x] e [IMAGEN: x]
    en una lista de ContentBlock para create_chapter_docx.

    También limpia Markdown residual que el LLM de maquetación
    pueda haber generado (##, **, <br>, ---, `code`).
    """
    # Limpiar Markdown residual
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"^---+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)

    blocks: list[ContentBlock] = []
    pattern = re.compile(
        r"\[SUBTÍTULO:\s*(.*?)\]|\[IMAGEN:\s*(.*?)\]",
        re.IGNORECASE | re.DOTALL,
    )

    last_end = 0
    for match in pattern.finditer(text):
        before = text[last_end : match.start()].strip()
        if before:
            blocks.append(TextBlock(content=before))

        if match.group(1) is not None:
            blocks.append(SubtitleBlock(text=match.group(1).strip()))
        elif match.group(2) is not None:
            blocks.append(ImageBlock(description=match.group(2).strip()))

        last_end = match.end()

    remaining = text[last_end:].strip()
    if remaining:
        blocks.append(TextBlock(content=remaining))

    return blocks if blocks else [TextBlock(content=text)]


# ── Re-exportaciones de error_handler y retry ────────────────────────────────
# Permite importar todo desde backend.graph.utils en lugar de módulos separados.

from backend.graph.error_handler import handle_error, ErrorCategory, ErrorInfo  # noqa: E402
from backend.graph.retry import retry_llm_call, PermanentError, with_retry       # noqa: E402


def retry_llm_call_json(llm: Any, messages: list, context: str = "") -> dict:
    """
    Como retry_llm_call, pero también reintenta si la respuesta no contiene
    JSON válido (JSONExtractionError). Hasta 3 intentos en total.
    """
    ctx = context or "LLM/JSON"
    last_exc: Exception = JSONExtractionError("sin intentos")
    for attempt in range(3):
        response = retry_llm_call(llm, messages, context=ctx)
        try:
            return extract_json(response.content)
        except JSONExtractionError as exc:
            last_exc = exc
            if attempt < 2:
                logger.warning(
                    f"[{ctx}] JSON malformado (intento {attempt + 1}/3), reintentando…"
                )
                time.sleep(2 ** attempt)
    raise last_exc


__all__ = [
    # Logging
    "logger",
    # Constantes de ciclo
    "MAX_PLAN_REVISIONS", "MAX_CHAPTER_REVISIONS", "MAX_EDITOR_REJECTIONS",
    # Enum de agentes, router de modelos y helpers de optimización
    "AgentName", "_AGENT_MODEL_CONFIG", "get_llm_for_agent",
    "cached_system_message", "trim_agent_feedback",
    # Bloques de contenido
    "TextBlock", "SubtitleBlock", "ImageBlock", "ContentBlock",
    # JSON
    "extract_json", "JSONExtractionError", "retry_llm_call_json",
    # Validación
    "check_word_count", "get_genre_word_limits", "MINIMUM_WORD_RATIO",
    # Parser de formato
    "parse_formatted_text",
    # Errores y reintentos
    "handle_error", "ErrorCategory", "ErrorInfo",
    "retry_llm_call", "PermanentError", "with_retry",
]
