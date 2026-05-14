"""
Agent 4 – El Especialista en Maquetación e Impresión  v2.0
Role: 10-year editorial specialist in accessibility and design.
Responsibility: Format chapter for print/ebook, generate .docx, flag legibility issues.

Cambios v2.0 (CORRECCIÓN CRÍTICA):
  - parse_formatted_text(): convierte marcadores [SUBTÍTULO:] e [IMAGEN:] en bloques
    tipados (SubtitleBlock, ImageBlock, TextBlock) y limpia Markdown residual.
    Esto elimina los artefactos #, **, <br> que aparecían en el docx.
  - create_chapter_docx() ahora recibe content_blocks (lista tipada), no texto plano.
  - Defaults de formato aplicados autónomamente (sin interrupt al usuario).
  - Notificación al usuario de preferencias de formato aplicadas.
  - extract_json() centralizado.
  - AgentName enum para current_agent.
  - Logging de decisiones.
"""

import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from backend.graph.state import BookState
from backend.tools.documents import create_chapter_docx
from backend.graph.utils import (
    retry_llm_call,
    PermanentError,
    AgentName,
    extract_json,
    JSONExtractionError,
    parse_formatted_text,
    logger,
)

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres el Especialista en Maquetación e Impresión: un experto editorial
con 10 años de experiencia en diseño de libros impresos y digitales (e-Readers, EPUB, PDF).

Tu especialidad es la accesibilidad y el diseño editorial. Evalúas:
- Longitud óptima de párrafos según género y audiencia
- Ritmo de lectura (alternancia de párrafos cortos y largos)
- Necesidad de subtítulos internos para orientar al lector
- Dónde colocar imágenes, gráficos o cuadros de texto destacados
- Problemas de legibilidad que requieran reestructurar oraciones

REGLA CRÍTICA DE FORMATO:
- USA ÚNICAMENTE marcadores de texto plano: [SUBTÍTULO: texto] e [IMAGEN: descripción]
- NUNCA uses Markdown (##, **, *, <br>, ---, ```). El sistema de maquetación no lo acepta.
- Los marcadores serán convertidos automáticamente a formato Word profesional.
- EXCEPCIÓN CRÍTICA: el contenido dentro de [IMAGEN: ...] debe estar SIEMPRE EN INGLÉS,
  ya que se envía directamente a un generador de imágenes IA (Ideogram).
  El resto del texto continúa en español.

Respondes siempre en español, EXCEPTO las descripciones [IMAGEN:] que van en inglés."""

# Separador entre la sección JSON y el texto formateado en la respuesta combinada
_COMBINED_SEPARATOR = "===TEXTO==="

LAYOUT_COMBINED_PROMPT = """Analiza y formatea este capítulo en una sola respuesta con DOS secciones.

## CONTEXTO
- Título: {title} | Género: {genre} | Audiencia: {target_audience}
- Capítulo: {chapter_num} de {total_chapters} — "{chapter_title}"
- Rol en el arco: {arc_role}

## REGLAS DE FORMATO PARA ESTE GÉNERO
{genre_format_rules}

## RITMO TIPOGRÁFICO SEGÚN ROL EN EL ARCO
{arc_rhythm}
{visual_section}
## TEXTO DEL CAPÍTULO:
{chapter_text}

## INSTRUCCIONES DE RESPUESTA

Tu respuesta tiene DOS secciones separadas por la línea exacta ===TEXTO===

**SECCIÓN 1 — JSON de análisis** (antes de ===TEXTO===):
```json
{{
  "needs_structural_rewrite": false,
  "structural_issues": "descripción si aplica, o cadena vacía",
  "formatting_notes": "notas breves de formato aplicado",
  "image_placements": [{{"after_paragraph": 3, "description": "descripción"}}],
  "subsections": [{{"after_paragraph": 5, "subtitle": "subtítulo"}}]
}}
```

Si needs_structural_rewrite=true: devuelve SOLO el JSON (sin ===TEXTO=== ni sección 2).

===TEXTO===

**SECCIÓN 2 — Texto formateado** (después de ===TEXTO===):
El texto del capítulo con los marcadores [SUBTÍTULO: texto] e [IMAGEN: descripción] insertados,
aplicando las reglas del género y el ritmo tipográfico.

Reglas ESTRICTAS:
- NUNCA uses Markdown: sin ##, sin **, sin *, sin <br>, sin ---, sin ```
- NUNCA repitas el título del capítulo al inicio del texto — ya aparece en el encabezado del libro
- Respeta el tamaño de párrafo indicado en las REGLAS DE FORMATO DEL GÉNERO
- Devuelve SOLO el texto con marcadores, sin explicaciones ni comentarios adicionales"""


# ── Prompts de contexto visual por familia de género ─────────────────────────

VISUAL_CONTEXT_PROMPT_NARRATIVE = """Analiza estos datos del libro y genera un CONTEXTO VISUAL DETALLADO
para que todas las ilustraciones narrativas sean coherentes entre sí a lo largo de los capítulos.
Las descripciones de personajes deben ser lo suficientemente detalladas para que un
generador de imágenes pueda recrear exactamente el mismo personaje en cada capítulo.

DATOS DEL LIBRO:
- Género: {genre}
- Tono: {tone}
- Estilo de escritura: {writing_style}
- Arco del libro: {book_arc}

PRIMER CAPÍTULO:
- Resumen: {first_chapter_summary}
- Puntos clave: {first_chapter_key_points}

Genera exactamente estas cinco líneas, sin encabezados ni formato adicional:

Época y lugar: [específico: país/región, período histórico o año aproximado, ambiente predominante (urbano/rural/submarino/etc.)]
Personajes visuales clave: [por cada personaje: NOMBRE + edad aproximada + complexión + color y largo de cabello + rasgos faciales distintivos + ropa típica + un detalle visual único. Separar personajes con " | "]
Estilo artístico: [técnica de ilustración + paleta de 3-4 colores hex o descriptivos + referentes visuales concretos + OBLIGATORIO incluir: "NOT photorealistic, NOT photograph, NOT 3D render"]
Paleta y atmósfera: [colores predominantes, tipo de iluminación, ambiente visual constante en todos los capítulos]
Prohibiciones: [elementos que NO deben aparecer — estilos incompatibles, anacronismos, elementos fuera de tono]

Responde SOLO con las cinco líneas. Sin explicaciones ni texto adicional."""

VISUAL_CONTEXT_PROMPT_CONCEPTUAL = """Analiza estos datos del libro y genera un CONTEXTO VISUAL
para que las ilustraciones conceptuales sean coherentes en estilo a lo largo de los capítulos.
Este libro de no-ficción práctica usa ilustraciones metafóricas y conceptuales, NO escenas narrativas.

DATOS DEL LIBRO:
- Género: {genre}
- Tono: {tone}
- Estilo de escritura: {writing_style}
- Arco del libro: {book_arc}

PRIMER CAPÍTULO:
- Resumen: {first_chapter_summary}
- Puntos clave: {first_chapter_key_points}

Genera exactamente estas tres líneas, sin encabezados ni formato adicional:

Paleta de marca: [3-4 colores hex o descriptivos que definen la identidad visual del libro — deben ser consistentes en todas las imágenes]
Estilo iconográfico: [técnica visual: flat design / editorial moderno / acuarela conceptual / etc. + referentes: estilo similar a Harvard Business Review / TED / etc. + OBLIGATORIO: "NOT photorealistic, NOT fictional narrative characters"]
Prohibiciones: [elementos que NO deben aparecer — personas ficticias con nombres, escenas narrativas, fotografías realistas, elementos incompatibles con el tono profesional]

Responde SOLO con las tres líneas. Sin explicaciones ni texto adicional."""

VISUAL_CONTEXT_PROMPT_INFOGRAPHIC = """Analiza estos datos del libro y genera un CONTEXTO VISUAL
para que las infografías sean coherentes en estilo a lo largo de los capítulos.
Este libro académico/científico usa infografías y diagramas, NO ilustraciones narrativas.

DATOS DEL LIBRO:
- Género: {genre}
- Tono: {tone}
- Estilo de escritura: {writing_style}
- Arco del libro: {book_arc}

PRIMER CAPÍTULO:
- Resumen: {first_chapter_summary}
- Puntos clave: {first_chapter_key_points}

Genera exactamente estas cuatro líneas, sin encabezados ni formato adicional:

Paleta editorial: [2-3 colores sobrios hex o descriptivos — azul académico, gris slate, blanco, con 1 color de acento — consistentes en todas las infografías]
Estilo visual: [tipo de infografía: diagrama de flujo / mapa conceptual / visualización de datos / etc. + referentes: estilo similar a Nature / Scientific American / The Economist + OBLIGATORIO: "NOT photorealistic, NOT narrative scene, NOT fictional characters"]
Elementos permitidos: [elementos gráficos válidos para este libro — flechas, formas geométricas, nodos, tablas, iconos, líneas de tiempo, etc.]
Prohibiciones: [elementos que NO deben aparecer — personas reales, escenas ficticias, fondos complejos, más de 4 colores simultáneos]

Responde SOLO con las cuatro líneas. Sin explicaciones ni texto adicional."""


def _detect_image_model(genre: str) -> str:
    """
    Detecta el modelo de imagen apropiado para el género.
    Retorna: 'narrative' | 'conceptual' | 'infographic'

    NOTA: 'no-ficción' se evalúa ANTES que 'ficción' para evitar falso positivo
    por substring (la palabra "ficción" está contenida en "no-ficción").
    """
    g = genre.lower()
    # 1. No-ficción práctica (más específico — ANTES que ficción)
    if any(k in g for k in ["no-ficción", "no-ficcion", "no ficción", "no ficcion",
                              "autoayuda", "auto-ayuda", "negocios", "emprendimiento",
                              "salud", "bienestar", "finanzas", "liderazgo", "coaching",
                              "desarrollo personal", "motivacion", "motivación"]):
        return "conceptual"
    # 2. Ficción / narrativa
    if any(k in g for k in ["novela", "cuento", "thriller", "romance", "ciencia ficción",
                              "ciencia ficcion", "fantasía", "fantasia", "fantasy", "horror",
                              "terror", "aventura", "misterio", "ficción", "ficcion",
                              "infantil", "niños", "niñas", "children", "kids", "cuentos",
                              "juvenil", "young adult", "ya"]):
        return "narrative"
    # 3. Académico / científico
    if any(k in g for k in ["académico", "academico", "científico", "cientifico",
                              "histórico", "historico", "investigación", "investigacion",
                              "ensayo", "filosófico", "filosofico", "médico", "medico",
                              "psicológico", "psicologico", "sociológico", "sociologico",
                              "económico", "economico", "jurídico", "juridico"]):
        return "infographic"
    # 4. Default: conceptual
    return "conceptual"


# ── Reglas de formato por género ────────────────────────────────────────────

MAX_LAYOUTER_REJECTIONS = 2   # tras este límite el Maquetador trunca en lugar de rechazar

_FICTION_GENRES_LAYOUT    = ["novela", "cuento", "thriller", "romance", "ciencia ficción",
                             "fantasía", "horror", "aventura", "misterio", "ficción"]
_CHILDREN_GENRES_LAYOUT   = ["infantil", "juvenil", "young adult", "ya", "álbum"]
_ACADEMIC_GENRES_LAYOUT   = ["académico", "académica", "ensayo", "científico", "histórico",
                             "filosófico", "investigación", "divulgación", "psicológico"]


def _get_genre_format_rules(genre: str) -> str:
    """
    Retorna las reglas de formato editorial específicas para la familia de género.
    Usado en el análisis y en las preferencias de formato aplicadas.
    """
    g = genre.lower()

    # Infantil/juvenil — evaluar ANTES de ficción
    if any(k in g for k in _CHILDREN_GENRES_LAYOUT):
        return (
            "REGLAS DE FORMATO — INFANTIL/JUVENIL:\n"
            "- Párrafos: máximo 3-4 líneas. El lector joven abandona párrafos largos.\n"
            "- Subtítulos: solo si hay cambio de escena o tiempo. Nunca decorativos.\n"
            "- Imágenes: coloca UNA imagen AL INICIO del capítulo, ANTES del primer párrafo,\n"
            "  describiendo la escena que el lector está a punto de leer (anticipa, no revela).\n"
            "  Si el capítulo supera 800 palabras, añade UNA segunda imagen en el punto medio.\n"
            "  MÁXIMO 2 imágenes por capítulo. NUNCA más.\n"
            "- Ritmo: preferir oraciones cortas y directas. Evitar subordinadas largas.\n"
            "- Diálogos: cada intervención en su propio párrafo, sin excepciones.\n"
            "- Capítulos cortos: máx. 1500 palabras. Si supera esa extensión,\n"
            "  marcar needs_structural_rewrite=true con sugerencia de división."
        )

    # Ficción adulta
    if any(k in g for k in _FICTION_GENRES_LAYOUT):
        return (
            "REGLAS DE FORMATO — FICCIÓN:\n"
            "- Párrafos: 4-6 líneas en promedio, con VARIACIÓN INTENCIONAL.\n"
            "  Párrafos de 1 línea para impacto. Párrafos de 10+ para tensión sostenida.\n"
            "- Subtítulos internos: PROHIBIDOS en ficción narrativa. Rompen el flujo.\n"
            "  Excepción: si el libro usa divisiones de Parte I / Parte II por estructura.\n"
            "- Imágenes: coloca como máximo UNA imagen, AL FINAL del capítulo, DESPUÉS del\n"
            "  último párrafo. Solo si el final del capítulo contiene una escena visualmente\n"
            "  impactante que funcione como gancho hacia el siguiente capítulo.\n"
            "  Si el final no es visual o es reflexivo, NO incluir imagen.\n"
            "  NUNCA imágenes en medio del capítulo — interrumpen el flujo narrativo.\n"
            "- Diálogos: cada intervención en su propio párrafo.\n"
            "- Escenas de acción: párrafos muy cortos (1-2 líneas). Aceleran el ritmo.\n"
            "- Escenas de reflexión: párrafos más largos (6-8 líneas) están bien."
        )

    # Académico / ensayo
    if any(k in g for k in _ACADEMIC_GENRES_LAYOUT):
        return (
            "REGLAS DE FORMATO — ACADÉMICO/ENSAYO:\n"
            "- Párrafos: 8-12 líneas son aceptables para argumentación densa.\n"
            "  Nunca superar 15 líneas sin una pausa visual.\n"
            "- Subtítulos: solo para secciones mayores del argumento.\n"
            "  Mínimo 3-4 páginas de contenido entre subtítulos.\n"
            "- Imágenes: tablas y gráficos con datos son bienvenidos y funcionales.\n"
            "  Describir con precisión el dato que ilustran.\n"
            "- Citas largas (más de 40 palabras): sugerir bloque de cita indentado\n"
            "  usando [SUBTÍTULO: Cita:] seguido del texto. No inline.\n"
            "- Densidad: este género puede ser denso. No dividir párrafos\n"
            "  argumentales solo por longitud — respetar la unidad de pensamiento."
        )

    # No-ficción práctica (default)
    return (
        "REGLAS DE FORMATO — NO-FICCIÓN PRÁCTICA:\n"
        "- Párrafos: 5-7 líneas. Preferir párrafos cortos y directos.\n"
        "- Subtítulos: cada 2-3 páginas estimadas para orientar al lector.\n"
        "  Los subtítulos deben describir el contenido, no solo decorar.\n"
        "- Imágenes: diagramas, esquemas y listas visuales son muy bienvenidos.\n"
        "- Listas: si hay 3+ elementos en una enumeración, sugerir lista visual\n"
        "  usando [SUBTÍTULO: Puntos clave:] antes de los elementos.\n"
        "- Cajas destacadas: para consejos, advertencias o resúmenes clave,\n"
        "  sugerir [IMAGEN: Recuadro destacado: texto del consejo]."
    )


def _get_arc_role_rhythm(arc_role: str, genre: str) -> str:
    """
    Traduce el arc_role del capítulo a una instrucción tipográfica concreta.
    Solo relevante para ficción — en no-ficción el ritmo lo dicta la estructura
    argumental, no la tensión narrativa.
    """
    g    = genre.lower()
    role = arc_role.lower()

    is_fiction = any(k in g for k in [
        "novela", "cuento", "thriller", "romance", "fantasía", "ficción",
        "horror", "aventura", "misterio", "infantil", "juvenil", "young adult",
    ])

    if not is_fiction:
        return (
            "Ritmo tipográfico: aplicar las reglas del género sin modificación "
            "por arc_role — en no-ficción el ritmo lo dicta la estructura argumental."
        )

    if any(k in role for k in ["crisis", "clímax", "climax", "tensión", "conflicto", "peligro"]):
        return (
            "RITMO ARC — CRISIS/CLÍMAX: Este capítulo debe acelerar visualmente.\n"
            "- Párrafos cada vez más cortos conforme avanza el capítulo.\n"
            "- En el punto de mayor tensión: párrafos de 1-2 líneas o incluso 1 sola oración.\n"
            "- Nunca un párrafo de más de 6 líneas en la segunda mitad del capítulo.\n"
            "- Sin subtítulos — la tensión no puede interrumpirse con pausas visuales.\n"
            "- Diálogos muy cortos, intercalados con acción breve."
        )

    if any(k in role for k in ["resolución", "cierre", "desenlace", "final"]):
        return (
            "RITMO ARC — RESOLUCIÓN/CIERRE: Este capítulo debe desacelerar gradualmente.\n"
            "- Párrafos más amplios que los anteriores (6-8 líneas), contemplativos.\n"
            "- Permitir oraciones largas que envuelvan al lector en la conclusión.\n"
            "- El último párrafo del capítulo debe ser especialmente cuidado:\n"
            "  no dividirlo aunque sea largo — debe leerse como un cierre.\n"
            "- Sin subtítulos en los últimos 2 párrafos del capítulo."
        )

    if any(k in role for k in ["presentación", "introducción", "apertura", "inicio"]):
        return (
            "RITMO ARC — PRESENTACIÓN/APERTURA: Ritmo moderado, invitador.\n"
            "- Párrafos medianos (4-6 líneas), ni muy cortos ni muy largos.\n"
            "- El primer párrafo nunca debe dividirse — es la primera impresión.\n"
            "- Permitir una pausa visual (subtítulo o espacio) a mitad del capítulo\n"
            "  si el capítulo presenta múltiples elementos (personajes, escenarios)."
        )

    if any(k in role for k in ["obstáculo", "giro", "quiebre", "complicación"]):
        return (
            "RITMO ARC — OBSTÁCULO/GIRO: Ritmo que oscila entre calma y ruptura.\n"
            "- Párrafos normales (4-5 líneas) en la primera mitad.\n"
            "- El momento del giro: 1-2 párrafos muy cortos (1-3 líneas) para impacto.\n"
            "- Después del giro: párrafos algo más largos que procesan la consecuencia.\n"
            "- Sin subtítulos en el momento del giro ni inmediatamente después."
        )

    if any(k in role for k in ["consolidación", "aprendizaje", "integración"]):
        return (
            "RITMO ARC — CONSOLIDACIÓN: Ritmo reflexivo y espacioso.\n"
            "- Párrafos de 5-7 líneas, sostenidos y deliberados.\n"
            "- Permitir subtítulos que ayuden a estructurar los aprendizajes.\n"
            "- Evitar párrafos de 1-2 líneas salvo para énfasis muy puntual."
        )

    # Fallback: desarrollo / avance
    return (
        "RITMO ARC — DESARROLLO: Ritmo equilibrado y sostenido.\n"
        "- Párrafos de 4-6 líneas con variación natural.\n"
        "- Permitir subtítulos si el capítulo cubre varios temas distintos.\n"
        "- Alternar ocasionalmente con párrafos cortos para evitar monotonía."
    )


# ── Truncado automático por límite de género ─────────────────────────────────

def _truncate_draft(draft: str, genre: str) -> str:
    """
    Trunca el borrador en el límite de palabras del género cuando el Maquetador
    agota sus intentos de reestructuración. Solo aplica límite estricto en
    infantil/juvenil; en otros géneros devuelve el texto sin cambios porque
    el problema estructural puede ser de otro tipo (párrafos, subtítulos, etc.).
    """
    g = genre.lower()
    is_children = any(k in g for k in ["infantil", "juvenil", "young adult", "ya", "álbum"])
    if not is_children:
        return draft

    word_limit = 1500
    paragraphs = [p for p in draft.split("\n\n") if p.strip()]
    result, word_count = [], 0

    for para in paragraphs:
        para_words = len(para.split())
        if word_count + para_words > word_limit:
            break
        result.append(para)
        word_count += para_words

    if not result:
        return draft   # fallback: no truncar si el primer párrafo ya supera el límite

    logger.info(
        f"[Maquetador] Borrador truncado a {word_count} palabras "
        f"(límite {word_limit} para género '{genre}')."
    )
    return "\n\n".join(result)


# ── LLM ──────────────────────────────────────────────────────────────────────

def _get_llm() -> ChatAnthropic:
    return ChatAnthropic(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        temperature=0.2,
        max_tokens=8192,
    )


# ── Contexto visual del libro ────────────────────────────────────────────────

def _build_visual_context(state: BookState) -> str:
    """
    Genera UNA SOLA VEZ el contexto visual del libro para que todos los [IMAGEN:]
    sean coherentes entre capítulos. El prompt varía según el modelo de imagen:
      - narrative:    5 campos con personajes + estilo artístico bloqueado
      - conceptual:   3 campos con paleta de marca + estilo iconográfico
      - infographic:  4 campos con paleta editorial + elementos de diagrama

    Se llama únicamente cuando visual_context no existe en el estado (capítulo 1).
    Temperatura 0.1 — la inferencia visual debe ser precisa y determinista.
    Retorna "" si falla para no interrumpir el pipeline.
    """
    outlines = state.get("chapter_outlines", [])
    if not outlines:
        logger.warning("[Maquetador] Sin chapter_outlines — contexto visual omitido.")
        return ""

    genre    = state.get("genre", "")
    model    = _detect_image_model(genre)
    first_ch = outlines[0]
    arc_data = state.get("book_arc", {})
    book_arc_summary = (
        f"Apertura: {arc_data.get('opening', '—')} | "
        f"Desarrollo: {arc_data.get('development', '—')} | "
        f"Resolución: {arc_data.get('resolution', '—')}"
    ) if arc_data else "Arco no definido"

    template = {
        "narrative":   VISUAL_CONTEXT_PROMPT_NARRATIVE,
        "conceptual":  VISUAL_CONTEXT_PROMPT_CONCEPTUAL,
        "infographic": VISUAL_CONTEXT_PROMPT_INFOGRAPHIC,
    }[model]

    prompt = template.format(
        genre=genre,
        tone=state.get("tone", ""),
        writing_style=state.get("writing_style", ""),
        book_arc=book_arc_summary,
        first_chapter_summary=first_ch.get("summary", ""),
        first_chapter_key_points=", ".join(first_ch.get("key_points", [])),
    )
    logger.info(f"[Maquetador] Modelo de imagen detectado: '{model}' para género: '{genre}'")

    try:
        llm_visual = ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            temperature=0.1,
            max_tokens=512,
        )
        response = retry_llm_call(
            llm_visual,
            [
                SystemMessage(
                    content=(
                        "Eres un analista visual especializado en coherencia estética de libros. "
                        "Respondes siempre en español con precisión y brevedad."
                    )
                ),
                HumanMessage(content=prompt),
            ],
            context="Maquetador/contexto-visual",
        )
        result = response.content.strip()
        logger.info(
            f"[Maquetador] Contexto visual generado ({len(result)} chars): "
            f"{result[:80]}…"
        )
        return result
    except Exception as e:
        logger.warning(
            f"[Maquetador] Contexto visual falló ({type(e).__name__}: {e}). "
            "Continuando sin contexto visual."
        )
        return ""


# ── Filtro de subtítulos por género y arc_role ───────────────────────────────

def _filter_subsections(
    subsections: list,
    genre: str,
    arc_role: str,
    chapter_text: str,
) -> list:
    """
    Garantiza en código que los subtítulos internos solo aparecen donde
    corresponde, independientemente de lo que el LLM devuelva.

    Es la última línea de defensa — el prompt instruye al LLM,
    esta función garantiza el resultado.
    """
    if not subsections:
        return []

    g    = genre.lower()
    role = arc_role.lower()

    # Contar párrafos del capítulo para decisiones de densidad
    paragraph_count = len([p for p in chapter_text.split("\n\n") if p.strip()])

    # ── Reglas por familia de género ──────────────────────────────────────

    # Ficción adulta
    is_adult_fiction = any(k in g for k in [
        "novela", "cuento", "thriller", "romance", "ciencia ficción",
        "fantasía", "horror", "aventura", "misterio", "ficción",
    ])
    if is_adult_fiction:
        # Crisis, clímax, obstáculo, giro → cero subtítulos
        arc_blocks_subtitles = any(k in role for k in [
            "crisis", "clímax", "climax", "tensión", "conflicto",
            "obstáculo", "giro", "quiebre", "peligro",
        ])
        if arc_blocks_subtitles:
            logger.info(
                f"[Maquetador] Subtítulos eliminados — arc_role '{arc_role}' "
                "no permite pausas visuales en ficción."
            )
            return []
        # Otros arc_roles en ficción: máx 1 subtítulo, solo en capítulos largos
        if paragraph_count < 15:
            logger.info(
                f"[Maquetador] Subtítulos eliminados — capítulo de ficción "
                f"con solo {paragraph_count} párrafos no los necesita."
            )
            return []
        # Permitir máx 1 subtítulo en capítulos muy largos
        if len(subsections) > 1:
            logger.info(
                "[Maquetador] Subtítulos reducidos a 1 — ficción adulta."
            )
            return subsections[:1]
        return subsections

    # Infantil / juvenil
    is_children = any(k in g for k in [
        "infantil", "juvenil", "young adult", "ya", "álbum",
    ])
    if is_children:
        # Solo permitir si el subtítulo indica cambio de escena/tiempo
        # Heurística: el subtitle contiene palabras de transición temporal/espacial
        scene_change_words = [
            "después", "más tarde", "al día siguiente", "mientras tanto",
            "en otro lugar", "horas después", "parte", "capítulo",
        ]
        filtered = [
            s for s in subsections
            if any(w in s.get("subtitle", "").lower() for w in scene_change_words)
        ]
        if len(subsections) != len(filtered):
            logger.info(
                f"[Maquetador] Subtítulos filtrados en infantil/juvenil: "
                f"{len(subsections)} → {len(filtered)} (solo cambios de escena)."
            )
        return filtered[:2]  # máx 2 en infantil/juvenil

    # Académico / ensayo
    is_academic = any(k in g for k in [
        "académico", "académica", "ensayo", "científico", "histórico",
        "filosófico", "investigación", "divulgación", "psicológico",
    ])
    if is_academic:
        # Máx 3 subtítulos, bien espaciados (mín 5 párrafos entre ellos)
        limited = subsections[:3]
        # Verificar espaciado mínimo
        validated = []
        last_position = -5
        for s in limited:
            pos = s.get("after_paragraph", 0)
            if pos - last_position >= 5:
                validated.append(s)
                last_position = pos
        return validated

    # No-ficción práctica — sin filtro restrictivo
    return subsections[:4]  # límite razonable: máx 4 subtítulos por capítulo


# ── Filtro de imágenes ────────────────────────────────────────────────────────

def _filter_image_blocks(content_blocks: list, genre: str, images_per_chapter: int = -1) -> list:
    """
    Garantiza en código la posición y cantidad de imágenes por capítulo,
    respetando la preferencia del usuario (images_per_chapter) por encima
    de cualquier heurística de género.

    images_per_chapter:
      -1  → no definido por el usuario → usar heurística de género
       0  → sin imágenes interiores (eliminar todas)
       1  → máximo 1 imagen por capítulo
       2  → máximo 2 imágenes por capítulo

    Heurística de género (cuando images_per_chapter == -1):
      - Infantil  → 2 imágenes (inicio + mitad)
      - Juvenil   → 1 imagen (punto de mayor impacto visual)
      - Ficción adulta / Académico → 0 imágenes (solo portada)
      - No-ficción práctica → 1 imagen (al inicio del capítulo)
    """
    from backend.graph.utils import ImageBlock

    g = genre.lower()
    is_children      = any(k in g for k in _CHILDREN_GENRES_LAYOUT)
    is_youth         = any(k in g for k in ["juvenil", "young adult", "ya"]) and not is_children
    is_adult_fiction = any(k in g for k in _FICTION_GENRES_LAYOUT) and not is_children and not is_youth
    is_academic      = any(k in g for k in _ACADEMIC_GENRES_LAYOUT)

    # Determinar límite efectivo
    if images_per_chapter >= 0:
        # El usuario eligió explícitamente
        max_images = images_per_chapter
    elif is_children:
        max_images = 2
    elif is_youth:
        max_images = 1
    elif is_adult_fiction or is_academic:
        max_images = 0
    else:
        # No-ficción práctica → 1 por defecto
        max_images = 1

    image_blocks = [b for b in content_blocks if isinstance(b, ImageBlock)]
    other_blocks  = [b for b in content_blocks if not isinstance(b, ImageBlock)]

    if not image_blocks:
        return content_blocks

    # Sin imágenes interiores
    if max_images == 0:
        if image_blocks:
            logger.info(f"[Maquetador] Filtro imágenes: eliminadas {len(image_blocks)} imagen(es) — images_per_chapter=0.")
        return other_blocks

    # 1 imagen — colocar en el punto de mayor impacto visual
    if max_images == 1:
        images = image_blocks[:1]
        removed = len(image_blocks) - 1
        if removed > 0:
            logger.info(f"[Maquetador] Filtro imágenes: {len(image_blocks)} → 1 (máx 1 por capítulo).")

        if is_children:
            # Infantil con 1 imagen: al inicio
            result = [images[0]] + other_blocks
        elif is_youth or is_adult_fiction:
            # Juvenil/adulto: al final del capítulo (gancho visual hacia el siguiente)
            result = other_blocks + [images[0]]
        else:
            # No-ficción: al inicio del capítulo
            result = [images[0]] + other_blocks
        return result

    # 2 imágenes — primera al inicio, segunda a mitad
    images = image_blocks[:2]
    removed = len(image_blocks) - len(images)
    if removed > 0:
        logger.info(f"[Maquetador] Filtro imágenes: {len(image_blocks)} → 2 (máx 2 por capítulo).")

    if len(images) == 1:
        result = [images[0]] + other_blocks
    else:
        mid = max(1, len(other_blocks) // 2)
        result = [images[0]] + other_blocks[:mid] + [images[1]] + other_blocks[mid:]
    return result


# ── Nodo principal ────────────────────────────────────────────────────────────

def layouter_node(state: BookState) -> dict:
    """
    Layouter node:
    - Analiza y formatea el capítulo aprobado
    - Si hay problemas estructurales → devuelve al escritor
    - Aplica defaults de formato autónomamente (sin interrupt)
    - Convierte texto con marcadores a bloques tipados antes de crear el docx
    - Guarda capítulo aprobado y avanza al siguiente o al publicador
    """
    llm           = _get_llm()
    chapter_index = state.get("current_chapter_index", 0)
    outlines      = state.get("chapter_outlines", [])
    chapter       = outlines[chapter_index]
    draft         = state.get("current_draft", "")
    output_dir    = state.get("output_dir", "output")
    genre             = state.get("genre", "")

    genre_format_rules = _get_genre_format_rules(genre)
    arc_role           = chapter.get("arc_role", "desarrollo")
    arc_rhythm         = _get_arc_role_rhythm(arc_role, genre)

    # ── Contexto visual: generar una vez, reutilizar en todos los capítulos ─
    visual_context = state.get("visual_context", "")
    if not visual_context:
        logger.info("[Maquetador] visual_context vacío — generando contexto visual del libro.")
        visual_context = _build_visual_context(state)

    # Sección condicional: instrucción de [IMAGEN:] varía por modelo de imagen
    image_model = _detect_image_model(genre)
    if not visual_context:
        visual_section = ""
    elif image_model == "narrative":
        visual_section = (
            f"\n## VISUAL CONTEXT (MANDATORY — apply to every [IMAGEN:])\n{visual_context}\n\n"
            "RULE FOR EACH [IMAGEN:]: Write IN ENGLISH — sent directly to Gemini image generator.\n"
            "MUST include ALL of these:\n"
            "1. CONCRETE ACTION: the most visually striking moment of this specific chapter scene\n"
            "2. PHYSICAL CHARACTERS: exact names + physical attributes from visual context above\n"
            "3. SETTING: specific location, time of day, weather, background details from this chapter\n"
            "4. EMOTION matching the arc_role of this chapter (e.g. 'horror clímax' → extreme dread)\n"
            "Example CORRECT: [IMAGEN: Valeria, 16, dark curly hair, torn wetsuit, grips a glowing blue stone "
            "with both hands. She stands on a rocky seafloor in dim green light. Her eyes are wide with terror "
            "as a massive shadow moves behind her. Oppressive deep-sea atmosphere, claustrophobic.]\n"
            "Example WRONG: [IMAGEN: The important moment of the chapter]\n"
            "NEVER use character names without physical description. NEVER use anachronistic elements.\n"
        )
    elif image_model == "infographic":
        visual_section = (
            f"\n## VISUAL CONTEXT (MANDATORY — apply to every [IMAGEN:])\n{visual_context}\n\n"
            "RULE FOR EACH [IMAGEN:]: Write IN ENGLISH — sent directly to Gemini image generator.\n"
            "Each [IMAGEN:] must describe a SCIENTIFIC INFOGRAPHIC, not a narrative scene.\n"
            "MUST include:\n"
            "1. INFOGRAPHIC TYPE: flow diagram / concept map / timeline / comparison chart / process diagram\n"
            "2. SUBJECT: the key concept, process, or relationship this chapter explains\n"
            "3. VISUAL STRUCTURE: how elements connect (arrows, nodes, sections, labels)\n"
            "4. COLOR PALETTE: from the visual context above\n"
            "Example CORRECT: [IMAGEN: Scientific infographic showing the carbon cycle as a circular flow diagram. "
            "Arrows connect: atmosphere, ocean, soil, and plants. Deep blue and slate grey palette with teal accents. "
            "Clean labels, geometric shapes, white background. Nature magazine style.]\n"
            "Example WRONG: [IMAGEN: A scientist in a lab studying carbon]\n"
            "NEVER include people, faces, or narrative scenes in infographic descriptions.\n"
        )
    else:  # conceptual
        visual_section = (
            f"\n## VISUAL CONTEXT (MANDATORY — apply to every [IMAGEN:])\n{visual_context}\n\n"
            "RULE FOR EACH [IMAGEN:]: Write IN ENGLISH — sent directly to Gemini image generator.\n"
            "Each [IMAGEN:] must describe a CONCEPTUAL/METAPHORICAL illustration, not a narrative scene.\n"
            "MUST include:\n"
            "1. CENTRAL METAPHOR: what object, abstract composition, or symbol represents the chapter's main idea\n"
            "2. VISUAL COMPOSITION: how the metaphor is rendered (geometric, organic, minimalist, etc.)\n"
            "3. COLOR PALETTE: from the visual context above (brand consistency)\n"
            "4. MOOD/TONE: professional, inspiring, thought-provoking, etc.\n"
            "Example CORRECT: [IMAGEN: Conceptual illustration of a single small plant growing through a concrete crack. "
            "Flat design style, clean lines. Color palette: deep green, warm grey, white. "
            "Represents resilience and growth. Minimalist editorial composition.]\n"
            "Example WRONG: [IMAGEN: A businessperson named John making a decision]\n"
            "NEVER include specific fictional characters. Use universal symbolic imagery.\n"
        )

    logger.info(
        f"[Maquetador] Iniciando formato del capítulo {chapter_index + 1}: "
        f"'{chapter['title']}' | género: '{genre}' | arc_role: '{arc_role}'"
    )

    # ── Llamada única: análisis + formateo en un solo round-trip ─────────
    combined_prompt = LAYOUT_COMBINED_PROMPT.format(
        title=state.get("title", "Sin título"),
        genre=genre,
        target_audience=state.get("target_audience", ""),
        chapter_num=chapter_index + 1,
        total_chapters=state.get("num_chapters", 1),
        chapter_title=chapter["title"],
        arc_role=arc_role,
        genre_format_rules=genre_format_rules,
        arc_rhythm=arc_rhythm,
        visual_section=visual_section,
        chapter_text=draft,
    )

    layout_data: dict = {}
    formatted_text = None
    _last_json_exc: Exception = JSONExtractionError("sin intentos")
    for _attempt in range(3):
        combined_response = retry_llm_call(
            llm,
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=combined_prompt),
            ],
            context="Maquetador/análisis+formato",
        )
        raw_response = combined_response.content
        # ── Separar JSON y texto formateado ──────────────────────────────
        try:
            if _COMBINED_SEPARATOR in raw_response:
                json_part, formatted_text = raw_response.split(_COMBINED_SEPARATOR, 1)
                formatted_text = formatted_text.strip() or draft
                layout_data = extract_json(json_part)
            else:
                # Solo JSON → needs_structural_rewrite=True o fallo de separador
                layout_data = extract_json(raw_response)
                formatted_text = None
            break  # JSON extraído correctamente
        except JSONExtractionError as exc:
            _last_json_exc = exc
            if _attempt < 2:
                logger.warning(
                    f"[Maquetador] JSON malformado (intento {_attempt + 1}/3), reintentando…"
                )
            else:
                raise _last_json_exc

    # ── Verificar si necesita reescritura estructural ─────────────────────
    if layout_data.get("needs_structural_rewrite", False) or formatted_text is None:
        issues = layout_data.get("structural_issues", "Problemas de legibilidad detectados.")
        logger.warning(f"[Maquetador] Cap.{chapter_index + 1} requiere reestructuración: {issues[:80]}")

        rejection_count = state.get("layouter_rejection_count", 0) + 1

        if rejection_count > MAX_LAYOUTER_REJECTIONS:
            logger.warning(
                f"[Maquetador] Cap.{chapter_index + 1} — límite de reestructuraciones "
                f"({MAX_LAYOUTER_REJECTIONS}) alcanzado. Aplicando truncado automático."
            )
            draft = _truncate_draft(draft, genre)
            # Continuar con el draft truncado — generar texto formateado desde el draft
            formatted_text = draft
        else:
            actual_word_count = len(draft.split())
            return {
                "layouter_rejection_count": rejection_count,
                "book_status":              "writing",
                "editor_approved":          False,
                "visual_context":           visual_context,
                "layouter_feedback": (
                    f"RECHAZO POR EXTENSIÓN (intento {rejection_count}/{MAX_LAYOUTER_REJECTIONS}): "
                    f"El capítulo tiene {actual_word_count} palabras. "
                    f"El límite para el género es 1500 palabras. "
                    f"Problema detectado: {issues}"
                ),
                "editor_feedback":          "",
                "current_agent":            AgentName.WRITER.value,
            }

    # ── Preferencias de formato (registro para capítulos futuros) ─────────
    existing_preferences = state.get("format_preferences", "")
    new_format_preferences = existing_preferences
    if not existing_preferences:
        new_format_preferences = (
            f"Formato adaptado al género '{genre}': " + genre_format_rules
        )
        logger.info(f"[Maquetador] Preferencias de formato registradas para género: '{genre}'")

    # ── Filtrar subsections en código (garantía independiente del LLM) ────
    raw_subsections   = layout_data.get("subsections", [])
    image_placements  = layout_data.get("image_placements", [])
    subsections       = _filter_subsections(raw_subsections, genre, arc_role, draft)

    # ── Parsear marcadores → bloques tipados ──────────────────────────────
    content_blocks = parse_formatted_text(formatted_text)

    # ── Filtrar imágenes: posición y cantidad según género ─────────────────
    images_per_chapter = int(state.get("images_per_chapter", -1))
    content_blocks = _filter_image_blocks(content_blocks, genre, images_per_chapter)

    logger.info(
        f"[Maquetador] Cap.{chapter_index + 1} — "
        f"{len(content_blocks)} bloques de contenido parseados "
        f"({sum(1 for b in content_blocks if b.__class__.__name__ == 'SubtitleBlock')} subtítulos, "
        f"{sum(1 for b in content_blocks if b.__class__.__name__ == 'ImageBlock')} imágenes)."
    )

    # ── Crear docx con bloques tipados ────────────────────────────────────
    docx_path, img_warning = create_chapter_docx(
        output_dir=output_dir,
        book_title=state.get("title", "libro"),
        chapter_index=chapter_index,
        chapter_title=chapter["title"],
        content_blocks=content_blocks,
        image_placements=image_placements,
        subsections=subsections,
        genre=genre,
        reference_image_path=state.get("reference_image_path", ""),
        visual_context=visual_context,
        chapter_content=chapter.get("content", ""),
    )

    # ── Guardar .md en área temporal ──────────────────────────────────────
    temp_dir = os.path.join(output_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    safe_title = (
        chapter["title"][:40]
        .replace(" ", "_")
        .replace("/", "-")
        .replace("\\", "-")
    )
    md_path = os.path.join(temp_dir, f"chapter_{chapter_index + 1:02d}_{safe_title}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {chapter['title']}\n\n{formatted_text}\n")

    # ── Registrar capítulo aprobado ───────────────────────────────────────
    approved_chapters = list(state.get("approved_chapters", []))
    approved_chapters.append({
        "index":             chapter_index,
        "title":             chapter["title"],
        # Solo primeras 500 chars — suficiente para contexto del Editor.
        # formatted_content es el campo completo usado por el Publicador.
        "content":           draft[:500],
        "formatted_content": formatted_text,
        "docx_path":         docx_path,
        "layout_notes":      layout_data.get("formatting_notes", ""),
    })

    next_index = chapter_index + 1
    total      = state.get("num_chapters", 1)

    if next_index >= total:
        logger.info(
            f"[Maquetador] Todos los capítulos ({total}) formateados. "
            "Pasando al Publicador."
        )
        return {
            "approved_chapters":        approved_chapters,
            "format_preferences":       new_format_preferences,
            "layouter_rejection_count": 0,
            "visual_context":           visual_context,
            "book_status":              "publishing",
            "current_agent":            AgentName.PUBLISHER.value,
            "system_warning":           img_warning or "",
        }

    logger.info(
        f"[Maquetador] Cap.{chapter_index + 1} listo. "
        f"Avanzando al capítulo {next_index + 1}."
    )
    return {
        "approved_chapters":        approved_chapters,
        "format_preferences":       new_format_preferences,
        "current_chapter_index":    next_index,
        "draft_revision":           0,
        "current_draft":            "",
        "editor_approved":          False,
        "editor_feedback":          "",
        "user_feedback_on_draft":   "",
        "editor_rejection_count":   0,
        "layouter_rejection_count": 0,
        # Resetear historiales del capítulo anterior — v2.2
        "chapter_rewrite_history":  [],
        "editor_feedback_history":  [],
        "layouter_feedback":        "",
        # Persistir el contexto visual generado en el capítulo 1 — v2.3
        "visual_context":           visual_context,
        "book_status":              "writing",
        "current_agent":            AgentName.WRITER.value,
        "system_warning":           img_warning or "",
    }
