"""
Agent 3 – El Editor Implacable  v2.0
Role: Top bestseller editor. Brutal critique, no mercy.
Responsibility: Review chapter quality, consistency, audience fit, and tone.
No user interrupt — fully automated. Returns to writer if chapter fails.

Cambios v2.0:
  - Validación de extensión mínima en el prompt (WORD_COUNT_RULE)
  - El score se valida en código, no solo en el prompt del LLM
  - Límite de rechazos por capítulo (MAX_EDITOR_REJECTIONS = 3)
  - extract_json() centralizado
  - AgentName enum para current_agent
  - Logging de decisiones
"""

import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from backend.graph.state import BookState
from backend.graph.utils import (
    retry_llm_call,
    retry_llm_call_json,
    PermanentError,
    AgentName,
    MAX_EDITOR_REJECTIONS,
    extract_json,
    check_word_count,
    get_genre_word_limits,
    get_llm_for_agent,
    cached_system_message,
    logger,
)

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres el Editor Implacable: el editor más exigente del mundo editorial,
responsable de bestsellers en múltiples géneros. Tu trabajo es garantizar que cada capítulo
sea irreprochable en contenido, prosa y autenticidad.

## CRITERIOS DE CONTENIDO

Evalúas sin piedad:
- ¿El primer párrafo engancha al lector inmediatamente — sin preámbulos, sin contexto innecesario?
- ¿El capítulo cumple su ROL EN EL ARCO (arc_role)?
  Un capítulo de "crisis" debe generar tensión real; "consolidación" debe reforzar con claridad;
  "resolución" debe cerrar de forma satisfactoria — no solo declarar que cerró.
- ¿El capítulo es coherente con el ARCO GLOBAL del libro (book_arc)?
  Verifica que la apertura del capítulo conecta con el "opening" del arco global si es el primero,
  que el desarrollo no adelanta la "resolution" antes de tiempo,
  y que los capítulos de cierre efectivamente llevan al lector al estado declarado en "resolution".
  Un capítulo de "resolución" que no conecta con la resolution del book_arc es un fallo estructural.
- ¿El contenido cumple con TODOS los puntos clave prometidos en el plan?
- ¿El tono y estilo son consistentes con el plan maestro a lo largo de todo el capítulo?
- ¿La lógica y el flujo son impecables — cada párrafo lleva al siguiente con necesidad?
- ¿Hay partes aburridas, redundantes o que podrían eliminarse sin perder nada?
- (Capítulo 2+) ¿Es consistente con los capítulos anteriores en tono, voz y referencias?
- ¿La audiencia objetivo se va a identificar con este texto?

## CRITERIOS DE PROSA — DETECCIÓN DE TEXTO ROBOTIZADO

Un capítulo puede tener buen contenido y mala prosa. Ambos deben ser excelentes.
Evalúa específicamente estas marcas de texto generado por IA:

RITMO:
- ¿Las frases tienen todas extensión similar? El ritmo monótono es la marca más
  reconocible del texto de IA. Debe haber alternancia real entre frases cortas y largas.
- ¿Hay al menos una frase de 3 palabras o menos en el capítulo? ¿Y una de más de 40?

APERTURAS DE PÁRRAFO:
- ¿Hay más de 2 párrafos consecutivos que empiecen con el mismo sujeto?
  Ej: "Rayo se...", "Rayo miró...", "Rayo sintió..." — tres seguidos es inaceptable.
- ¿Algún párrafo abre con conectores de transición vacíos?
  ("En este capítulo...", "A continuación...", "Como vimos...", "Cabe destacar...")

VOCABULARIO:
- ¿Aparecen verbos genéricos de IA más de 2 veces en el capítulo?
  Lista de vigilancia: realizar, llevar a cabo, implementar, desarrollar (genérico),
  generar, establecer, efectuar, proceder a.
- ¿Aparecen adjetivos vacíos repetidos?
  Lista de vigilancia: importante, fundamental, crucial, esencial, significativo,
  profundo (sin profundidad real), innegable, indudable.
- ¿Los conectores de muleta aparecen más de 1 vez por capítulo?
  Lista de vigilancia: sin embargo, no obstante, por otro lado, en este sentido,
  cabe destacar, hay que tener en cuenta, es importante señalar, en conclusión.

AUTENTICIDAD:
- ¿El capítulo tiene una imagen, metáfora o escena que solo podría pertenecer a ESTE capítulo
  y no a cualquier otro libro del mismo género?
- ¿El cierre del capítulo explica lo que el lector debe sentir, o lo hace sentir directamente?
  (Mostrar > Explicar — "sintió tristeza" es IA; una escena que produce tristeza es escritura.)

## CRITERIOS DE VERACIDAD — INTEGRIDAD DE FUENTES

El nivel de rigor depende del género y viene indicado en la sección REGLA DE FUENTES
del prompt de revisión. Aplica el criterio correspondiente sin excepciones:

Para FICCIÓN e INFANTIL/JUVENIL (nivel NONE):
- Los datos del mundo real mencionados (fechas, lugares, cifras históricas) deben
  ser verosímiles. Un error factual burdo en una novela rompe la credibilidad.
- No se exigen citas — la imaginación es la fuente.

Para NO-FICCIÓN PRÁCTICA (nivel STANDARD):
- Todo dato, estadística o caso real debe tener atribución de fuente en el texto.
  Formato mínimo: "(Fuente: [nombre], [URL o referencia)"
- Un dato sin fuente en el texto es un dato que el lector no puede verificar.
- Si el capítulo presenta estadísticas sin fuente: critical_issue obligatorio.
- Si el 20%+ de los datos carecen de fuente: no puede aprobar con score > 7.

Para ACADÉMICO/CIENTÍFICO (nivel STRICT):
- Toda afirmación factual requiere cita completa: Autor, Año, Fuente, DOI/URL.
- El capítulo debe distinguir explícitamente entre:
    • Hecho probado: citado con fuente verificable
    • Consenso científico: indicado como tal con referencia al consenso
    • Hipótesis: marcada explícitamente como hipótesis
    • Opinión del autor: atribuida al autor con nombre
- PROHIBIDO: extrapolar, inferir o asumir datos más allá de lo que dice la fuente.
- Si hay afirmaciones sin cita, o citas incompletas: critical_issue obligatorio.
- Un capítulo STRICT sin citas completas NO puede aprobar (score máximo: 6).

## FORMATO DE RESPUESTA

Respondes SIEMPRE en español y en formato JSON exacto:
{
  "approved": true/false,
  "overall_score": <número 1-10>,
  "prose_score": <número 1-10, evalúa SOLO la calidad de la prosa>,
  "content_score": <número 1-10, evalúa SOLO el contenido y estructura>,
  "strengths": ["fortaleza específica 1", "fortaleza específica 2"],
  "critical_issues": ["problema crítico con ejemplo del texto 1", "problema 2"],
  "prose_issues": ["problema de prosa específico con cita del texto problemático"],
  "specific_improvements": ["mejora concreta y accionable 1", "mejora 2"],
  "verdict": "Un párrafo con veredicto final — qué cambiar o felicitación si aprueba"
}

REGLAS ABSOLUTAS:
- overall_score = promedio ponderado: content_score × 0.6 + prose_score × 0.4
- overall_score, prose_score y content_score: números enteros o decimales, NUNCA strings.
- Aprueba (approved: true) SOLO si overall_score >= 8 Y prose_score >= 7.
  Un capítulo con contenido perfecto (10) pero prosa robotizada (5) → overall=8, rechazar.
- critical_issues y prose_issues deben citar fragmentos reales del texto, no descripciones genéricas.
- specific_improvements: ordenar de mayor a menor impacto. El primer item debe ser
  la mejora que más acerca el capítulo a la aprobación. Máximo 5 mejoras.
- Si el texto es excelente, sé generoso. Si es mediocre, sé brutal y específico."""

REVIEW_PROMPT = """Revisa este capítulo con criterio editorial de bestseller:

## CONTEXTO DEL LIBRO
- Título: {title}
- Género: {genre}
- Audiencia: {target_audience}
- Tono: {tone}
- Estilo: {writing_style}
- Arco global: {book_arc}

## CAPÍTULO
- Número: {chapter_num} de {total_chapters}
- Título: {chapter_title}
- Rol en el arco del libro: {arc_role}
- Puntos clave prometidos: {key_points}
- Extensión objetivo: {word_count_target} palabras
- Extensión real del texto: {actual_words} palabras

## REGLA DE EXTENSIÓN
{word_count_rule}

## REGLA DE FUENTES
{source_rule}

## CONTEXTO DE CONSISTENCIA
{consistency_context}

## CRITERIOS DE GÉNERO
{genre_criteria}

## TEXTO DEL CAPÍTULO:
{chapter_text}

Analiza y devuelve ÚNICAMENTE el JSON de evaluación."""

WORD_COUNT_RULE_FAIL = """⚠️ EXTENSIÓN INSUFICIENTE: El capítulo tiene {actual_words} palabras pero el objetivo
es {word_count_target} (mínimo aceptable: {min_words} palabras = 70% del objetivo).
DEBES indicar approved:false y añadir en critical_issues:
"Extensión insuficiente: {actual_words} palabras de {word_count_target} requeridas."
No hay excepciones a esta regla sin importar la calidad de la prosa."""

WORD_COUNT_RULE_OK = """✅ Extensión correcta: {actual_words} palabras (objetivo: {word_count_target})."""

SOURCE_RULE_NONE = """Nivel NONE (ficción/infantil): verifica que los datos del mundo
real mencionados sean verosímiles. No se exigen citas formales."""

SOURCE_RULE_STANDARD = """Nivel STANDARD (no-ficción práctica): OBLIGATORIO que todo
dato, estadística o caso real tenga atribución de fuente en el texto.
Formato mínimo: (Fuente: [nombre], [referencia]).
Si hay datos sin fuente: añadir a critical_issues.
Si el 20%+ de datos carecen de fuente: score máximo 7, no aprobar."""

SOURCE_RULE_STRICT = """Nivel STRICT (académico/científico): OBLIGATORIO cita completa
para toda afirmación factual: Autor, Año, Fuente, DOI/URL.
El texto DEBE distinguir: hecho probado / consenso / hipótesis / opinión.
Citas incompletas o ausentes → critical_issue obligatorio.
Sin citas completas: score máximo 6, no puede aprobar."""


# ── Clasificador de nivel de rigor (espeja la lógica del Escritor) ──────────

_STRICT_GENRES_EDITOR = [
    "científico", "científica", "académico", "académica",
    "investigación", "histórico", "histórica", "médico", "médica",
    "jurídico", "jurídica", "psicológico", "psicológica",
    "sociológico", "sociológica", "económico", "económica",
]
_FICTION_GENRES_EDITOR = [
    "novela", "cuento", "thriller", "romance", "ciencia ficción", "fantasía",
    "horror", "aventura", "misterio", "ficción", "narrativa",
    "infantil", "juvenil", "young adult", "ya", "álbum",
]


def _source_rigor_level(genre: str) -> str:
    """
    Retorna el nivel de rigor de fuentes que el Editor debe verificar.
    Espeja _research_level() del Escritor para coherencia entre agentes.
      NONE     — ficción/infantil: datos del mundo real deben ser verosímiles
      STANDARD — no-ficción práctica: datos deben tener atribución de fuente
      STRICT   — académico/científico: citas completas, distinción hecho/hipótesis
    """
    g = genre.lower()
    if any(k in g for k in _FICTION_GENRES_EDITOR):
        return "NONE"
    if any(k in g for k in _STRICT_GENRES_EDITOR):
        return "STRICT"
    return "STANDARD"


# ── LLM ──────────────────────────────────────────────────────────────────────

def _get_llm() -> ChatAnthropic:
    return get_llm_for_agent(AgentName.EDITOR.value, temperature=0.3, max_tokens=4096)


# ── Contexto de consistencia ──────────────────────────────────────────────────

def _build_consistency_context(state: BookState) -> str:
    """
    Construye el contexto de consistencia para el Editor.
    Prioriza los capítulos declarados como dependencies del capítulo actual.
    Complementa con hasta 2 capítulos recientes si hay pocos deps declarados.
    """
    approved = state.get("approved_chapters", [])
    if not approved:
        return "Este es el primer capítulo — no hay capítulos anteriores para verificar consistencia."

    chapter_index = state.get("current_chapter_index", 0)
    outlines      = state.get("chapter_outlines", [])
    current_outline = outlines[chapter_index] if chapter_index < len(outlines) else {}
    declared_deps   = current_outline.get("dependencies", [])

    approved_by_index = {ch["index"]: ch for ch in approved}

    # Capítulos de dependencia declarada
    dep_chapters = [approved_by_index[d] for d in declared_deps if d in approved_by_index]

    # Complementar con recientes si hay pocos deps
    recent = [ch for ch in approved[-2:] if ch["index"] not in declared_deps]
    relevant = dep_chapters + recent

    context_parts = [
        f"Capítulos relevantes para verificar consistencia ({len(relevant)} cap.):"
    ]
    for ch in relevant:
        tag = " [dependencia declarada]" if ch["index"] in declared_deps else ""
        context_parts.append(
            f"\n• Cap.{ch['index'] + 1} '{ch['title']}'{tag} — "
            f"Resumen: {ch['content'][:300]}\u2026"
        )
    return "\n".join(context_parts)


# ── Validación del score en código ────────────────────────────────────────────

def _parse_score(raw) -> float:
    """Normaliza un score a float. Acepta 8, 8.5, "8", "8/10". Devuelve 0.0 si falla."""
    try:
        return float(str(raw).split("/")[0].strip())
    except (ValueError, TypeError):
        return 0.0


def _resolve_approval(review: dict) -> tuple[bool, float, float, float]:
    """
    Determina la aprobación real con validación en código.
    Retorna (aprobado, overall_score, content_score, prose_score).

    Lógica de aprobación:
    - overall_score >= 7.5 (tolerancia sobre el umbral de 8)
    - prose_score >= 7.0 (prosa robotizada rechaza aunque el contenido sea perfecto)
    - LLM también debe decir approved:true
    """
    overall  = _parse_score(review.get("overall_score", 0))
    content  = _parse_score(review.get("content_score", overall))   # fallback a overall
    prose    = _parse_score(review.get("prose_score", overall))     # fallback a overall

    # Recalcular overall en código si vienen los sub-scores
    if review.get("content_score") and review.get("prose_score"):
        computed = round(content * 0.6 + prose * 0.4, 1)
        # Usar el menor entre el declarado y el calculado (evitar inflación)
        overall = min(overall, computed) if overall > 0 else computed

    llm_approved     = bool(review.get("approved", False))
    score_approved   = overall >= 7.5 and prose >= 7.0
    actual_approved  = llm_approved and score_approved

    if llm_approved != actual_approved:
        logger.warning(
            f"[Editor] Aprobación corregida: LLM={llm_approved} → código={actual_approved} "
            f"(overall={overall}, content={content}, prose={prose})"
        )

    return actual_approved, overall, content, prose


# ── Criterios de calidad por género ─────────────────────────────────────────

def _get_genre_criteria(genre: str) -> str:
    """
    Retorna los criterios de calidad específicos para la familia de género.
    Se pasa al REVIEW_PROMPT como {genre_criteria} para que el Editor
    aplique el estándar correcto según el tipo de libro.
    """
    g = genre.lower()

    # Infantil / juvenil — ANTES de ficción adulta
    if any(k in g for k in ["infantil", "juvenil", "young adult", "ya", "álbum"]):
        return (
            "CRITERIOS ESPECÍFICOS — INFANTIL/JUVENIL:\n"
            "- LENGUAJE POR EDAD: ¿el vocabulario y la complejidad sintáctica son\n"
            "  apropiados para el rango de edad declarado? Un libro para 6-9 años\n"
            "  no puede tener construcciones subordinadas complejas.\n"
            "- PROTAGONISTA IDENTIFICABLE: ¿el lector de la edad objetivo puede\n"
            "  ponerse en el lugar del protagonista? ¿sus problemas son reconocibles?\n"
            "- MENSAJE CLARO: ¿el valor o aprendizaje central emerge naturalmente\n"
            "  de la historia, sin ser predicado ni explicado?\n"
            "- RITMO ÁGIL: ¿hay suficiente acción o cambio cada 2-3 páginas para\n"
            "  mantener la atención del lector joven? Los capítulos deben ser cortos.\n"
            "- AUSENCIA DE CONDESCENDENCIA: ¿el narrador trata al lector joven con\n"
            "  inteligencia, sin explicar lo que ya es obvio por la acción?"
        )

    # Ficción adulta
    if any(k in g for k in ["novela", "cuento", "thriller", "romance", "ciencia ficción",
                             "fantasía", "horror", "aventura", "misterio", "ficción"]):
        return (
            "CRITERIOS ESPECÍFICOS — FICCIÓN:\n"
            "- TENSIÓN SOSTENIDA: ¿hay una pregunta narrativa abierta que el lector\n"
            "  necesita responder antes de poder cerrar el capítulo?\n"
            "- VOZ CONSISTENTE: ¿el narrador mantiene la misma distancia, tono y\n"
            "  personalidad de los capítulos anteriores?\n"
            "- DIÁLOGO FUNCIONAL: ¿cada línea de diálogo revela carácter, avanza la\n"
            "  trama o añade tensión? El diálogo decorativo es un defecto grave.\n"
            "- MOSTRAR > EXPLICAR: ¿las emociones se generan a través de escenas y\n"
            "  acciones, o se nombran directamente? Nombrar la emoción es el recurso\n"
            "  del escritor inexperto.\n"
            "- GIROS CREÍBLES: si hay un giro o revelación, ¿estaba preparado por\n"
            "  pistas anteriores? El giro que sorprende sin haber sido sembrado es trampa."
        )

    # Académico / ensayo
    if any(k in g for k in ["académico", "académica", "ensayo", "científico", "científica",
                             "histórico", "histórica", "filosófico", "investigación",
                             "divulgación", "psicológico", "sociológico"]):
        return (
            "CRITERIOS ESPECÍFICOS — ACADÉMICO/ENSAYO:\n"
            "- PROGRESIÓN ARGUMENTAL: ¿cada párrafo construye sobre el anterior?\n"
            "  El argumento debe avanzar linealmente, sin saltos ni repeticiones.\n"
            "- DISTINCIÓN HECHO/HIPÓTESIS/OPINIÓN: ¿el texto marca claramente\n"
            "  cuándo afirma un hecho probado, cuándo propone una hipótesis y cuándo\n"
            "  expresa la opinión del autor? Mezclarlos sin señalarlo es deshonestidad\n"
            "  intelectual.\n"
            "- CONTRAPUNTO: ¿el texto reconoce las objeciones más serias a su tesis\n"
            "  y las responde? Un ensayo que ignora el contrapunto es débil.\n"
            "- DENSIDAD APROPIADA: ¿el texto es tan denso como debe ser — sin\n"
            "  relleno ni simplificación excesiva — para la audiencia declarada?\n"
            "- CONCLUSIÓN DERIVADA: ¿la conclusión del capítulo se deriva\n"
            "  necesariamente de lo argumentado, o es una afirmación externa?"
        )

    # No-ficción práctica (default para géneros no reconocidos también)
    return (
        "CRITERIOS ESPECÍFICOS — NO-FICCIÓN PRÁCTICA:\n"
        "- PROMESA CUMPLIDA: ¿el capítulo entrega exactamente lo que su título y\n"
        "  apertura prometieron al lector?\n"
        "- APLICABILIDAD INMEDIATA: ¿el lector puede implementar algo de este\n"
        "  capítulo hoy, sin necesitar leer el libro completo?\n"
        "- EJEMPLOS CONCRETOS: ¿los conceptos se ilustran con casos reales, datos\n"
        "  verificables o escenarios específicos? Los ejemplos genéricos no cuentan.\n"
        "- ESTRUCTURA ACCIONABLE: ¿hay pasos, principios o marcos claros que el\n"
        "  lector pueda recordar y usar? La teoría sin estructura práctica falla.\n"
        "- EVITAR LA OBVIEDAD: ¿el capítulo aporta algo que el lector no sabía\n"
        "  ya? Un capítulo que solo repite el sentido común no aporta valor."
    )


# ── Nodo principal ────────────────────────────────────────────────────────────

def editor_node(state: BookState) -> dict:
    """
    Editor node: revisión automatizada, sin interrupt de usuario.
    Aprueba → pasa al maquetador.
    Rechaza → devuelve feedback detallado al escritor.
    Límite: MAX_EDITOR_REJECTIONS rechazos antes de aprobar bajo reserva.
    """
    llm               = _get_llm()
    chapter_index     = state.get("current_chapter_index", 0)
    outlines          = state.get("chapter_outlines", [])
    chapter           = outlines[chapter_index]
    draft             = state.get("current_draft", "")
    rejection_count   = state.get("editor_rejection_count", 0)
    feedback_history  = state.get("editor_feedback_history", [])
    word_target       = chapter.get("word_count_target", 3500)

    genre      = state.get("genre", "")
    # Aplicar límite del género: para juvenil/infantil el target efectivo es 1500
    genre_min, genre_max = get_genre_word_limits(genre)
    if genre_max and word_target > genre_max:
        word_target = genre_max
    actual_words, meets_minimum = check_word_count(draft, word_target)
    min_words = int(word_target * 0.70)

    # Construir regla de fuentes según nivel de rigor del género
    rigor_level = _source_rigor_level(genre)
    if rigor_level == "NONE":
        source_rule = SOURCE_RULE_NONE
    elif rigor_level == "STRICT":
        source_rule = SOURCE_RULE_STRICT
    else:
        source_rule = SOURCE_RULE_STANDARD

    logger.info(f"[Editor] Cap.{chapter_index + 1} — nivel de rigor de fuentes: {rigor_level}")

    # Construir regla de extensión para el prompt
    if meets_minimum:
        word_count_rule = WORD_COUNT_RULE_OK.format(
            actual_words=actual_words,
            word_count_target=word_target,
        )
    else:
        word_count_rule = WORD_COUNT_RULE_FAIL.format(
            actual_words=actual_words,
            word_count_target=word_target,
            min_words=min_words,
        )

    consistency_context = _build_consistency_context(state)

    # Construir criterios de género y resumen del arco global
    genre_criteria = _get_genre_criteria(genre)
    arc_data = state.get("book_arc", {})
    book_arc_summary = (
        f"Apertura: {arc_data.get('opening', '—')} | "
        f"Desarrollo: {arc_data.get('development', '—')} | "
        f"Resolución: {arc_data.get('resolution', '—')}"
    ) if arc_data else "Arco no definido"

    prompt = REVIEW_PROMPT.format(
        title=state.get("title", "Sin título"),
        genre=genre,
        target_audience=state.get("target_audience", ""),
        tone=state.get("tone", ""),
        writing_style=state.get("writing_style", ""),
        book_arc=book_arc_summary,
        genre_criteria=genre_criteria,
        chapter_num=chapter_index + 1,
        total_chapters=state.get("num_chapters", 1),
        chapter_title=chapter["title"],
        arc_role=chapter.get("arc_role", "desarrollo"),
        key_points=", ".join(chapter.get("key_points", [])),
        word_count_target=word_target,
        actual_words=actual_words,
        word_count_rule=word_count_rule,
        source_rule=source_rule,
        consistency_context=consistency_context,
        chapter_text=draft,
    )

    review = retry_llm_call_json(
        llm,
        [
            cached_system_message(SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ],
        context="Editor/revisión",
    )
    approved, score, content_score, prose_score = _resolve_approval(review)

    logger.info(
        f"[Editor] Cap.{chapter_index + 1} | "
        f"Overall={score} Content={content_score} Prose={prose_score} | "
        f"Aprobado={approved} | Palabras={actual_words}/{word_target} | "
        f"Rechazo #{rejection_count}"
    )

    if approved:
        return {
            "editor_approved":        True,
            "editor_feedback":        "",
            "editor_feedback_history": [],   # reset al aprobar
            "editor_rejection_count":  0,
            "book_status":            "formatting",
            "current_agent":          AgentName.LAYOUTER.value,
        }

    # ── Capítulo rechazado ─────────────────────────────────────────────────
    if rejection_count >= MAX_EDITOR_REJECTIONS:
        logger.warning(
            f"[Editor] Cap.{chapter_index + 1} — límite de {MAX_EDITOR_REJECTIONS} "
            "rechazos alcanzado. Aprobando bajo reserva."
        )
        return {
            "editor_approved":        True,
            "editor_feedback":        "",
            "editor_feedback_history": [],   # reset al forzar aprobación
            "editor_rejection_count":  0,
            "book_status":            "formatting",
            "system_warning": (
                f"Capítulo {chapter_index + 1} aprobado bajo reserva tras "
                f"{MAX_EDITOR_REJECTIONS} rechazos (score final: {score})."
            ),
            "current_agent":          AgentName.LAYOUTER.value,
        }

    feedback = _format_rejection(review, chapter_index + 1, score, content_score, prose_score)
    updated_history = feedback_history + [feedback]

    return {
        "editor_approved":        False,
        "editor_feedback":        feedback,
        "editor_feedback_history": updated_history,
        "editor_rejection_count": rejection_count + 1,
        "book_status":            "writing",
        "current_agent":          AgentName.WRITER.value,
    }


# ── Helper de formato de rechazo ──────────────────────────────────────────────

def _prioritize_issues(
    critical_issues: list,
    prose_issues: list,
    content_score: float,
    prose_score: float,
) -> tuple[str, list, list]:
    """
    Determina el área de ataque principal y ordena los issues por impacto.

    Retorna (area_principal, critical_ordenados, prose_ordenados).

    Orden de impacto para critical_issues:
      1. Extensión insuficiente (bloquea aprobación inmediatamente)
      2. arc_role no cumplido (fallo estructural del capítulo)
      3. Puntos clave del plan no cubiertos (incumplimiento del plan)
      4. Consistencia con capítulos anteriores (coherencia del libro)
      5. Fuentes sin verificación (integridad de la información)
      6. Otros problemas de contenido
    """
    # Determinar área principal de ataque
    if content_score < 7.0 and prose_score < 7.0:
        area = (
            "ATENCION DUAL: Hay problemas serios en CONTENIDO y PROSA.\n"
            f"  Atacar primero: CONTENIDO (score {content_score}/10)"
            " — es mas dificil de corregir.\n"
            f"  Luego: PROSA (score {prose_score}/10)."
        )
    elif content_score < 7.0:
        area = (
            f"PRIORIDAD: CONTENIDO (score {content_score}/10).\n"
            "  Resuelto el contenido, revisar también los issues de prosa."
        )
    elif prose_score < 7.0:
        area = (
            f"PRIORIDAD: PROSA (score {prose_score}/10).\n"
            "  El contenido es sólido — enfocarse en eliminar marcas de texto robotizado."
        )
    else:
        area = "Problemas menores en ambas áreas — revisión de refinamiento."

    # Ordenar critical_issues por impacto
    priority_keywords = [
        ["extensión", "palabras", "word_count", "corto", "mínimo"],      # P1
        ["arc_role", "arco", "crisis", "clímax", "resolución", "tensión"], # P2
        ["punto clave", "key_point", "plan", "prometido", "incluir"],      # P3
        ["consistencia", "capítulo anterior", "dependencia", "contradice"], # P4
        ["fuente", "cita", "verificar", "dato", "estadística"],             # P5
    ]

    def get_priority(issue_text: str) -> int:
        lower = issue_text.lower()
        for i, keywords in enumerate(priority_keywords):
            if any(k in lower for k in keywords):
                return i
        return len(priority_keywords)  # Otros al final

    ordered_critical = sorted(critical_issues, key=get_priority)
    # Prose issues: ordenar por severidad (repetición > vocabulario > ritmo)
    prose_priority = [
        ["párrafo", "consecutivo", "mismo sujeto", "apertura repetida"],
        ["verbo", "realizar", "llevar a cabo", "implementar", "genérico"],
        ["conector", "sin embargo", "no obstante", "muleta"],
        ["ritmo", "extensión", "monótono", "uniforme"],
    ]

    def get_prose_priority(issue_text: str) -> int:
        lower = issue_text.lower()
        for i, keywords in enumerate(prose_priority):
            if any(k in lower for k in keywords):
                return i
        return len(prose_priority)

    ordered_prose = sorted(prose_issues, key=get_prose_priority)
    return area, ordered_critical, ordered_prose


def _format_rejection(
    review: dict,
    chapter_num: int,
    score: float,
    content_score: float = 0.0,
    prose_score: float = 0.0,
) -> str:
    """
    Formatea el reporte de rechazo del Editor con problemas priorizados por impacto.
    El Escritor recibe: qué área atacar primero + issues en orden de impacto.
    """
    critical    = review.get("critical_issues", [])
    prose_issues = review.get("prose_issues", [])

    area, ordered_critical, ordered_prose = _prioritize_issues(
        critical, prose_issues, content_score, prose_score
    )

    lines = [
        f"🔴 REPORTE DEL EDITOR — Capítulo {chapter_num}",
        f"Puntuación total: {score}/10  "
        f"(Contenido: {content_score}/10 | Prosa: {prose_score}/10)",
        "",
        area,
        "",
        "✅ FORTALEZAS:",
    ]
    for s in review.get("strengths", []):
        lines.append(f"  • {s}")

    if ordered_critical:
        lines.append("")
        lines.append("❌ PROBLEMAS DE CONTENIDO (ordenados por impacto):")
        for i, p in enumerate(ordered_critical, 1):
            lines.append(f"  [{i}] {p}")

    if ordered_prose:
        lines.append("")
        lines.append("✍️  PROBLEMAS DE PROSA (ordenados por impacto):")
        for i, p in enumerate(ordered_prose, 1):
            lines.append(f"  [{i}] {p}")

    improvements = review.get("specific_improvements", [])
    if improvements:
        lines.append("")
        lines.append("🔧 MEJORAS REQUERIDAS (en orden de prioridad):")
        for i, m in enumerate(improvements, 1):
            lines.append(f"  [{i}] {m}")

    lines.append("")
    lines.append(f"📋 VEREDICTO: {review.get('verdict', '')}")
    return "\n".join(lines)
