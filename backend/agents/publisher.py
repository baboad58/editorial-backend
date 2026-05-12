"""
Agent 5 – El Publicador  v2.0
Role: Cover creator and legal/publishing specialist.
Responsibility: Assemble all chapters, generate front/back matter, create final master file.

Cambios v2.0 (CORRECCIONES CRÍTICAS):
  - _extract_author_data(): parsea la respuesta libre del usuario con un LLM extractor
    antes de usar los datos. Elimina el bug donde "1. Claudio\\n2. Bio\\n3. No\\n4. sorprendeme"
    aparecía literalmente en la portada del libro.
  - cover_description se guarda como archivo separado (brief_portada.txt) y NO
    se pasa a assemble_final_book. Elimina el bug donde el brief de portada
    aparecía dentro del libro.
  - try/except alrededor de generate_cover_with_ideogram (fallback sin imagen).
  - AgentName enum para current_agent.
  - Logging de decisiones.
"""

import os
import re
import shutil
from datetime import datetime

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import interrupt  # conservado para compatibilidad futura

from backend.graph.state import BookState
from backend.tools.documents import assemble_final_book
from backend.tools.cover_generator import generate_cover_with_ideogram, generate_style_reference
from backend.graph.utils import (
    retry_llm_call,
    retry_llm_call_json,
    PermanentError,
    AgentName,
    extract_json,
    get_llm_for_agent,
    cached_system_message,
    logger,
)

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres el Publicador: especialista en aspectos legales, portadas y cierre editorial
de libros. Eres el último eslabón en la cadena de producción del libro.

Tu responsabilidad es:
1. Escribir el PREFACIO del libro (presentación emotiva, por qué este libro, a quién va dirigido)
2. Escribir la PÁGINA LEGAL (copyright, derechos reservados, datos del autor)
3. Escribir los AGRADECIMIENTOS (cálido y personal, invitando al lector a conectar)
4. Generar la descripción detallada de la PORTADA para un diseñador o IA generativa de imágenes
5. Escribir una BIO del autor (basada en lo que el usuario comparte)
6. Ensamblar el libro completo en orden correcto

Siempre respondes en español. Tu texto es cálido, profesional y memorable."""

AUTHOR_EXTRACT_PROMPT = """El usuario respondió a una entrevista de publicación con este texto:

"{raw_response}"

Extrae los datos y devuelve ÚNICAMENTE este JSON (usa null para campos no proporcionados):
{{
  "author_name": "nombre completo del autor, o null",
  "email": "correo electrónico si el usuario lo menciona, o null",
  "bio": "bio de 2-3 oraciones, o null",
  "acknowledgment_context": "contexto para los agradecimientos, o null",
  "cover_preferences": "preferencias de portada, o null"
}}

Reglas de extracción:
- Si el texto tiene formato numerado "1. Nombre\\n2. Bio..." extrae cada campo por número.
- Si el usuario solo dio su nombre sin estructura, ponlo en author_name.
- La bio puede incluir profesión, logros, experiencia mencionados por el usuario.
- Si menciona un correo electrónico, extraerlo en el campo email.
- No inventes información que el usuario no haya proporcionado.
- Devuelve SOLO el JSON, sin texto adicional."""

PREFACIO_PROMPT = """Escribe el PREFACIO del libro "{title}" por {author_name}.

## CONTEXTO COMPLETO DEL LIBRO
- Género: {genre}
- Audiencia: {target_audience}
- Tono: {tone}
- Arco del libro: {book_arc}
{bio_context}

## ESTRUCTURA NARRATIVA DEL LIBRO
{chapters_summary}

## INSTRUCCIONES SEGÚN GÉNERO
{genre_prefacio_rules}

## REQUISITOS GENERALES DEL PREFACIO
- Contar POR QUÉ se escribió este libro y qué lo hace único
- Hablar directamente al lector ideal usando el tono del libro
- Crear expectativa conectando con el arco del libro
- Terminar con una invitación a comenzar la lectura
- La extensión está indicada en las INSTRUCCIONES SEGÚN GÉNERO arriba

Escribe SOLO el texto del prefacio, sin encabezados meta."""

LEGAL_PROMPT = """Escribe la PÁGINA LEGAL del libro "{title}".

Datos del libro:
- Título: {title}
- Autor: {author_name}
- Año: {year}
- Género: {genre}
- Audiencia: {target_audience}
- Contacto del autor: {author_contact}

Usa esta PLANTILLA como base y adáptala al libro específico:

IMPORTANTE — DERECHOS DE USO

Este [libro / manual / guía / obra] es propiedad intelectual de [autor] y ha sido creado como
[contexto adaptado al género: "material de consulta profesional" para no-ficción, "obra literaria"
para ficción, "recurso educativo" para académico, "obra de entretenimiento" para infantil].
Queda prohibida su reproducción, distribución o uso comercial sin autorización expresa
por escrito del autor.

El contenido [adaptar al género: para no-ficción o académico: "no reemplaza normativa vigente
ni asesoría profesional especializada"; para ficción: "es una obra de ficción — cualquier
semejanza con personas o eventos reales es coincidencia"; para infantil: "ha sido diseñado
para ser apropiado para el rango de edad indicado"].

Contacto: {author_contact}  |  {copyright_line}

REGLAS DE ADAPTACIÓN:
- Reemplaza los corchetes con el texto específico del libro
- Tono: más formal para académico/técnico, más cálido para infantil/juvenil
- Escribe SOLO el texto legal final, sin corchetes, sin instrucciones, sin Markdown
- Extensión: 80-150 palabras, conciso y preciso"""

AGRADECIMIENTOS_PROMPT = """Escribe los AGRADECIMIENTOS del libro "{title}".

## CONTEXTO DEL LIBRO
- Género: {genre}
- Audiencia: {target_audience}
- Tono del libro: {tone}

## CONTEXTO DEL AUTOR
{acknowledgment_context}

## REGISTRO SEGÚN GÉNERO
{genre_agradecimientos_register}

## REQUISITOS
- Cálidos y auténticos — que el lector sienta la gratitud real del autor
- Mencionar categorías naturales de personas según el contexto del autor
- Terminar con una nota de gratitud al lector (quien también forma parte del libro)
- Extensión: 200-350 palabras

Escribe SOLO el texto de agradecimientos, sin encabezados meta."""

SOBRE_EL_AUTOR_PROMPT = """Escribe la sección "Sobre el Autor" del libro "{title}".

Datos del autor:
- Nombre: {author_name}
- Bio proporcionada: {author_bio}
- Género del libro: {genre}
- Audiencia del libro: {target_audience}

Usa esta PLANTILLA como base y adáptala con los datos reales del autor:

---
Sobre el Autor

[Nombre completo] es [título profesional o descripción], [institución o contexto],
con [años] de experiencia en [área principal].

Cuenta con [formación académica relevante], [certificaciones si las hay],
y [experiencia destacada en el área del libro].

Su enfoque en [tema del libro] es [característica distintiva]: [descripción breve
de su filosofía o metodología de trabajo]. Ha [logros o actividades relevantes].

Este libro [conectar el libro con la trayectoria del autor — por qué este autor
está especialmente calificado para escribir este libro].
---

INSTRUCCIONES:
1. Reemplaza los corchetes con información real del autor
2. Si la bio proporcionada es escasa, elabora con dignidad lo que hay
3. Conecta al autor con el tema del libro de forma natural
4. Tono: profesional pero cercano, en tercera persona
5. Extensión: 150-250 palabras
6. Escribe SOLO el texto final, sin corchetes, sin instrucciones, sin Markdown
7. Empieza directamente con el nombre del autor"""


def _build_cover_prompt_template(genre: str) -> str:
    """
    Retorna el prompt de diseño de portada adaptado al género.
    Los libros infantiles/juveniles necesitan instrucciones de estilo visual
    específicas para que Ideogram no genere imágenes realistas o adultas.
    """
    g = genre.lower()
    is_children = any(k in g for k in ["infantil", "niños", "niñas", "children", "kids", "cuentos", "cuento", "álbum"])
    is_youth = any(k in g for k in ["juvenil", "young adult", "ya"])

    if is_children:
        style_guide = """
## GUÍA DE ESTILO VISUAL — LIBRO INFANTIL
El prompt para Ideogram DEBE seguir estas reglas de estilo sin excepción:
- Estilo: gouache o acuarela digital con trazos expresivos. NUNCA fotorrealismo ni flat design frío.
- Colores: VIVOS y SATURADOS obligatoriamente — rojos profundos, amarillos solares, azules eléctricos,
  verdes exuberantes. SIN tonos pastel suaves, SIN paleta apagada, SIN grises.
- Personajes: redondeados, expresivos, ojos grandes y amigables. Sin rasgos angulosos ni adultos.
- Composición: personaje principal grande y centrado, fondo simple con colores planos y brillantes.
- Prohibido: sombras dramáticas, perspectivas complejas, texturas fotorrealistas,
  elementos de terror, violencia, o contenido adulto de cualquier tipo.
- Referentes visuales: Patito Feo ilustrado, Elmer el elefante, cuentos de Roald Dahl ilustrados."""
        ideogram_instruction = (
            "prompt en inglés, 80-120 palabras, OBLIGATORIAMENTE en estilo gouache o acuarela digital infantil. "
            "Incluir: VIVID SATURATED COLORS (deep red, sunny yellow, electric blue, lush green), "
            "friendly rounded characters with large expressive eyes, bold outlines, "
            "simple joyful background with flat color fills. NO pastel tones, NO muted palette. "
            'Terminar siempre con: "Children\'s picture book cover, gouache illustration style, '
            'vivid saturated colors, professional publishing quality, portrait 2:3 format"'
        )
    elif is_youth:
        style_guide = """
## GUÍA DE ESTILO VISUAL — LIBRO JUVENIL
El prompt para Ideogram DEBE seguir estas reglas de estilo:
- Estilo: ilustración digital semi-realista o pintura digital expresiva.
- Colores: paleta vibrante con contraste. Pueden usarse tonos más profundos que en infantil.
- Personajes: jóvenes (10-17 años), expresivos, dinámicos.
- Composición: dramática, con profundidad. El personaje principal domina la portada.
- Prohibido: contenido adulto, violencia explícita, imágenes aterradoras."""
        ideogram_instruction = (
            "prompt en inglés, 80-120 palabras, estilo ilustración digital para jóvenes. "
            "Incluir: personaje joven expresivo, composición dinámica, colores vibrantes, "
            "atmósfera acorde al tono del libro. "
            'Terminar siempre con: "Young adult book cover, digital illustration style, '
            'vibrant colors, professional publishing quality, portrait 2:3 format"'
        )
    else:
        style_guide = ""
        ideogram_instruction = (
            "prompt en inglés, 80-120 palabras, optimizado para IA generativa de imágenes. "
            "Incluir: estilo visual, composición, colores, atmósfera, personajes/elementos. "
            'Terminar siempre con: "Book cover design, professional publishing quality, portrait 2:3 format"'
        )

    return f"""Diseña la portada del libro con dos secciones bien separadas:

## DATOS DEL LIBRO
- Título: {{title}}
- Subtítulo: {{subtitle}}
- Género: {{genre}}
- Audiencia: {{target_audience}}
- Tono: {{tone}}
{{cover_pref_context}}{style_guide}

## PARTE 1 — BRIEF PARA EL DISEÑADOR
Escribe con estos encabezados exactos:

CONCEPTO VISUAL:
(imagen central, atmósfera, elementos visuales principales — coherente con el estilo del género)

PALETA DE COLORES:
(3-4 colores con código hex exacto)

TIPOGRAFÍA:
(estilo para título y subtítulo — apropiado para el género)

COMPOSICIÓN:
(posición de cada elemento en la portada)

## PARTE 2 — PROMPT PARA IDEOGRAM (OBLIGATORIO)
Al final del brief, escribe EXACTAMENTE este bloque con los marcadores:

[IDEOGRAM_PROMPT]
({ideogram_instruction})
[/IDEOGRAM_PROMPT]

IMPORTANTE: Los marcadores [IDEOGRAM_PROMPT] y [/IDEOGRAM_PROMPT] son obligatorios.
Esta descripción se guardará como brief para el diseñador. NO es parte del libro."""


# ── LLM ──────────────────────────────────────────────────────────────────────

def _get_llm() -> ChatAnthropic:
    return get_llm_for_agent(AgentName.PUBLISHER.value, temperature=0.7, max_tokens=4096)


# ── Parser de respuesta del usuario ──────────────────────────────────────────

def _extract_author_data(llm: ChatAnthropic, raw_response: str) -> dict:
    """
    Parsea la respuesta libre del usuario a campos estructurados usando un LLM extractor.
    Nunca falla: siempre retorna un dict con al menos author_name.
    """
    try:
        _EXTRACTOR_SYSTEM = "Eres un extractor de datos preciso. Responde solo con JSON válido."
        data = retry_llm_call_json(
            llm,
            [
                cached_system_message(_EXTRACTOR_SYSTEM),
                HumanMessage(content=AUTHOR_EXTRACT_PROMPT.format(raw_response=raw_response)),
            ],
            context="Publicador/extracción-autor",
        )

        # Validar y limpiar author_name
        if not data.get("author_name"):
            data["author_name"] = _fallback_author_name(raw_response)

        return data

    except Exception as e:
        logger.warning(f"[Publicador] Extracción de datos del autor falló ({e}). Usando fallback.")
        return {
            "author_name":            _fallback_author_name(raw_response),
            "bio":                    None,
            "acknowledgment_context": None,
            "cover_preferences":      None,
        }


def _fallback_author_name(raw: str) -> str:
    """Extrae el nombre del autor de la primera línea legible del texto."""
    for line in raw.split("\n"):
        line = line.strip()
        if line:
            # Quitar numeración "1. Nombre" → "Nombre"
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", line)
            if cleaned:
                return cleaned[:80]
    return "El Autor"


# ── Helpers del Publicador ──────────────────────────────────────────────────

def _get_genre_prefacio_rules(genre: str) -> str:
    """
    Instrucciones de tono y estructura del prefacio según familia de género.
    """
    g = genre.lower()

    if any(k in g for k in ["infantil", "juvenil", "young adult", "ya", "álbum"]):
        return (
            "Prefacio para libro INFANTIL/JUVENIL:\n"
            "- Tono cálido, invitador, cercano al lector joven\n"
            "- Puede dirigirse tanto al niño/joven como a padres o educadores\n"
            "- Contar qué aventura o aprendizaje les espera\n"
            "- Lenguaje simple y entusiasta — sin condescendencia\n"
            "- Extensión inferior: 300-400 palabras es suficiente"
        )

    if any(k in g for k in ["novela", "cuento", "thriller", "romance", "fantasía",
                             "ficción", "horror", "aventura", "misterio"]):
        return (
            "Prefacio para FICCIÓN:\n"
            "- Tono misterioso o emotivo, según el género específico\n"
            "- NO revelar plot twists ni el final\n"
            "- Contar la génesis de la historia: cuándo nació en la mente del autor\n"
            "- Crear intriga sobre los personajes o el mundo sin spoilers\n"
            "- Terminar invitando al lector a entrar al mundo de la historia\n"
            "- Extensión: 350-500 palabras"
        )

    if any(k in g for k in ["académico", "académica", "ensayo", "científico",
                             "histórico", "filosófico", "investigación", "divulgación"]):
        return (
            "Prefacio para texto ACADÉMICO/ENSAYO:\n"
            "- Tono riguroso pero accesible\n"
            "- Declarar la tesis o pregunta central que el libro responde\n"
            "- Contextualizar la relevancia del tema en el momento actual\n"
            "- Indicar a qué perfil de lector está dirigido y qué conocimiento previo requiere\n"
            "- Mencionar la metodología o enfoque del libro brevemente\n"
            "- Extensión: 500-700 palabras — el lector académico aprecia el rigor"
        )

    # No-ficción práctica (default)
    return (
        "Prefacio para NO-FICCIÓN PRÁCTICA:\n"
        "- Tono directo y empático — hablar del problema que el lector tiene\n"
        "- Mostrar que el autor entiende la frustración o necesidad del lector\n"
        "- Prometer concretamente qué va a cambiar en la vida del lector\n"
        "- Contar brevemente la credibilidad del autor para tratar este tema\n"
        "- Terminar con un llamado a la acción: empezar a leer ya\n"
        "- Extensión: 400-600 palabras"
    )


def _get_genre_agradecimientos_register(genre: str) -> str:
    """
    Instrucciones de registro y tono para los agradecimientos según género.
    """
    g = genre.lower()

    if any(k in g for k in ["infantil", "juvenil", "young adult", "ya", "álbum"]):
        return (
            "Registro INFANTIL/JUVENIL: cálido, tierno, con humor suave.\n"
            "Mencionar naturalmente: niños o jóvenes que inspiraron la historia,\n"
            "padres o educadores que apoyaron el proyecto, quienes creyeron\n"
            "en la importancia de leer para las nuevas generaciones.\n"
            "Lenguaje simple — como si los propios niños pudieran leerlo."
        )

    if any(k in g for k in ["novela", "cuento", "thriller", "romance", "fantasía",
                             "ficción", "horror", "aventura", "misterio"]):
        return (
            "Registro FICCIÓN: emotivo, con personalidad propia del género.\n"
            "Para thriller/horror: puede tener humor oscuro o ironía.\n"
            "Para romance: cálido y evocador. Para fantasía/aventura: épico y agradecido.\n"
            "Mencionar naturalmente: quienes soportaron las largas horas de escritura,\n"
            "primeros lectores que dieron feedback honesto, fuentes de inspiración.\n"
            "Puede ser más personal e íntimo que en no-ficción."
        )

    if any(k in g for k in ["académico", "académica", "ensayo", "científico",
                             "histórico", "filosófico", "investigación", "divulgación"]):
        return (
            "Registro ACADÉMICO/ENSAYO: sobrio, preciso, profesional.\n"
            "Mencionar naturalmente: colegas que revisaron el manuscrito,\n"
            "instituciones que apoyaron la investigación, debates académicos\n"
            "que nutrieron el pensamiento, fuentes bibliográficas clave.\n"
            "Tono más formal — los agradecimientos académicos son también parte\n"
            "del rigor intelectual del texto."
        )

    # No-ficción práctica (default)
    return (
        "Registro NO-FICCIÓN PRÁCTICA: directo, sincero, orientado a resultados.\n"
        "Mencionar naturalmente: expertos que validaron el contenido,\n"
        "personas que aplicaron las ideas y dieron feedback real,\n"
        "quienes creyeron en el proyecto cuando era solo una idea.\n"
        "El agradecimiento al lector debe conectar con el problema que el libro resuelve."
    )


def _build_chapters_summary(approved_chapters: list, chapter_outlines: list) -> str:
    """
    Construye un resumen enriquecido de los capítulos combinando:
    - Los summaries del plan (chapter_outlines) — describen el propósito
    - El arc_role de cada capítulo — describe su función en el arco
    Mucho más informativo que solo los títulos.
    """
    # Crear índice de outlines por posición
    outline_by_index = {o["index"]: o for o in chapter_outlines}

    lines = []
    for ch in approved_chapters:
        idx     = ch["index"]
        outline = outline_by_index.get(idx, {})
        arc_role = outline.get("arc_role", "")
        summary  = outline.get("summary", "")

        line = f"Cap.{idx + 1}: {ch['title']}"
        if arc_role:
            line += f" [{arc_role}]"
        if summary:
            # Tomar solo la primera oración del summary para no sobrecargar el prompt
            first_sentence = summary.split(".")[0].strip()
            if first_sentence:
                line += f" — {first_sentence}."
        lines.append(line)

    return "\n".join(lines)


# ── Nodo principal ────────────────────────────────────────────────────────────

def publisher_node(state: BookState) -> dict:
    """
    Publisher node:
    - Pregunta datos del autor (único interrupt de usuario)
    - Parsea la respuesta libre con _extract_author_data() antes de usar los datos
    - Genera front/back matter autónomamente
    - Guarda cover_description como archivo separado (NO dentro del libro)
    - Ensambla el docx final
    """
    llm               = _get_llm()
    approved_chapters = state.get("approved_chapters", [])
    title             = state.get("title", "Mi Libro")
    subtitle          = state.get("subtitle", "")
    output_dir        = state.get("output_dir", "output")
    year              = datetime.now().year

    logger.info(
        f"[Publicador] Iniciando publicación de '{title}' "
        f"({len(approved_chapters)} capítulos aprobados)."
    )

    # ── Leer datos del autor del estado (recopilados por el Arquitecto) ────
    # No hay interrupt — los datos se obtuvieron al inicio del proceso
    raw_author_info = (
        f"Nombre: {state.get('author_name', '')}\n"
        f"Bio: {state.get('author_bio', '')}\n"
        f"Email: {state.get('author_email', '')}\n"
        f"Agradecimientos: {state.get('author_acknowledgment_context', '')}\n"
        f"Portada: {state.get('author_cover_preferences', '')}"
    )

    # Usar _extract_author_data para normalizar (por compatibilidad con el parser)
    author_data = _extract_author_data(llm, raw_author_info)

    # Usar directamente los campos del estado (ya fueron extraídos por el Arquitecto)
    author_name            = state.get("author_name") or author_data.get("author_name") or "El Autor"
    author_bio             = state.get("author_bio") or author_data.get("bio") or ""
    acknowledgment_context = state.get("author_acknowledgment_context") or author_data.get("acknowledgment_context") or raw_author_info
    cover_preferences      = state.get("author_cover_preferences") or author_data.get("cover_preferences") or ""

    logger.info(
        f"[Publicador] Datos del autor extraídos — "
        f"Nombre: '{author_name}' | Bio: {'sí' if author_bio else 'no'} | "
        f"Preferencias portada: {'sí' if cover_preferences else 'no'}"
    )

    chapters_summary = _build_chapters_summary(
        approved_chapters,
        state.get("chapter_outlines", []),
    )

    # Arco del libro para el prefacio
    arc_data = state.get("book_arc", {})
    book_arc_summary = (
        f"Apertura: {arc_data.get('opening', '—')} | "
        f"Desarrollo: {arc_data.get('development', '—')} | "
        f"Resolución: {arc_data.get('resolution', '—')}"
    ) if arc_data else "Arco no definido"

    genre              = state.get("genre", "")
    genre_prefacio_rules = _get_genre_prefacio_rules(genre)

    bio_context = f"\nBio del autor: {author_bio}" if author_bio else ""
    cover_pref_context = f"\nPreferencias del autor: {cover_preferences}" if cover_preferences else ""

    # ── Generar contenido del libro (autónomo, sin más interrupts) ────────

    _cached_pub_system = cached_system_message(SYSTEM_PROMPT)

    prefacio = retry_llm_call(
        llm,
        [
            _cached_pub_system,
            HumanMessage(content=PREFACIO_PROMPT.format(
                title=title,
                author_name=author_name,
                genre=genre,
                target_audience=state.get("target_audience", ""),
                tone=state.get("tone", ""),
                book_arc=book_arc_summary,
                chapters_summary=chapters_summary,
                genre_prefacio_rules=genre_prefacio_rules,
                bio_context=bio_context,
            )),
        ],
        context="Publicador/prefacio",
    ).content

    # Construir campos legales
    author_contact  = author_data.get("email") or f"contacto@{author_name.split()[-1].lower()}.cl"
    copyright_line  = f"© {year} {author_name}. Todos los derechos reservados."

    pagina_legal = retry_llm_call(
        llm,
        [
            _cached_pub_system,
            HumanMessage(content=LEGAL_PROMPT.format(
                title=title,
                author_name=author_name,
                year=year,
                genre=genre,
                target_audience=state.get("target_audience", ""),
                author_contact=author_contact,
                copyright_line=copyright_line,
            )),
        ],
        context="Publicador/legal",
    ).content

    agradecimientos = retry_llm_call(
        llm,
        [
            _cached_pub_system,
            HumanMessage(content=AGRADECIMIENTOS_PROMPT.format(
                title=title,
                genre=genre,
                target_audience=state.get("target_audience", ""),
                tone=state.get("tone", ""),
                acknowledgment_context=acknowledgment_context,
                genre_agradecimientos_register=_get_genre_agradecimientos_register(genre),
            )),
        ],
        context="Publicador/agradecimientos",
    ).content

    # Generar sección "Sobre el Autor" estructurada desde la plantilla
    sobre_el_autor = retry_llm_call(
        llm,
        [
            _cached_pub_system,
            HumanMessage(content=SOBRE_EL_AUTOR_PROMPT.format(
                title=title,
                author_name=author_name,
                author_bio=author_bio or "El autor prefirió no compartir detalles adicionales.",
                genre=genre,
                target_audience=state.get("target_audience", ""),
            )),
        ],
        context="Publicador/sobre-el-autor",
    ).content

    cover_description = retry_llm_call(
        llm,
        [
            _cached_pub_system,
            HumanMessage(content=_build_cover_prompt_template(genre).format(
                title=title,
                subtitle=subtitle,
                genre=genre,
                target_audience=state.get("target_audience", ""),
                tone=state.get("tone", ""),
                cover_pref_context=cover_pref_context,
            )),
        ],
        context="Publicador/portada",
    ).content

    # ── CORRECCIÓN CRÍTICA: cover_description → archivo separado ──────────
    # NO se pasa a assemble_final_book. Se guarda como brief para el diseñador.
    os.makedirs(output_dir, exist_ok=True)
    cover_brief_path = os.path.join(output_dir, "brief_portada.txt")
    with open(cover_brief_path, "w", encoding="utf-8") as f:
        f.write(
            f"BRIEF DE DISEÑO DE PORTADA\n"
            f"Libro: {title}\n"
            f"Autor: {author_name}\n"
            f"{'=' * 60}\n\n"
            f"{cover_description}"
        )
    logger.info(f"[Publicador] Brief de portada guardado en: {cover_brief_path}")

    # ── Resolver imagen de referencia visual ──────────────────────────────
    # Si el usuario subió una imagen se usa directamente.
    # Si no, se genera una imagen base a partir de la trama del libro para
    # que portada e ilustraciones de capítulo compartan el mismo estilo visual.
    reference_image_path = state.get("reference_image_path", "")
    if not reference_image_path:
        logger.info("[Publicador] Sin imagen de referencia del usuario — generando referencia de estilo.")
        reference_image_path = generate_style_reference(
            title=title,
            genre=genre,
            cover_description=cover_description,
            output_dir=output_dir,
        ) or ""
        if reference_image_path:
            logger.info(f"[Publicador] Referencia de estilo generada: {reference_image_path}")
        else:
            logger.info("[Publicador] No se pudo generar referencia de estilo — imágenes sin coherencia forzada.")

    # ── Generar imagen de portada ──────────────────────────────────────────
    cover_image_path = None
    cover_warning = None
    try:
        cover_image_path, cover_warning = generate_cover_with_ideogram(
            title=title,
            subtitle=subtitle,
            author_name=author_name,
            cover_description=cover_description,
            output_dir=output_dir,
            genre=genre,
            reference_image_path=reference_image_path,
        )
        logger.info(f"[Publicador] Imagen de portada generada: {cover_image_path}")
    except Exception as e:
        logger.warning(
            f"[Publicador] Generación de portada falló ({type(e).__name__}: {e}). "
            "Continuando sin imagen de portada."
        )
        cover_warning = "⚠️ Error inesperado al generar la portada. El libro se generó sin portada."

    # ── Ensamblar libro final ──────────────────────────────────────────────
    final_path = assemble_final_book(
        output_dir=output_dir,
        title=title,
        subtitle=subtitle,
        author_name=author_name,
        author_bio=sobre_el_autor,    # sección editorial completa, no bio cruda
        genre=genre,
        prefacio=prefacio,
        pagina_legal=pagina_legal,
        agradecimientos=agradecimientos,
        # cover_description NO se pasa — va en brief_portada.txt
        cover_image_path=cover_image_path,
        chapters=approved_chapters,
        reference_image_path=reference_image_path,
        visual_context=state.get("visual_context", ""),
    )

    logger.info(f"[Publicador] Libro ensamblado: {final_path}")

    # ── Copiar a Biblioteca ───────────────────────────────────────────────
    try:
        base_project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        biblioteca_dir   = os.path.join(base_project_dir, "Biblioteca")
        fecha            = datetime.now().strftime("%Y-%m-%d")
        safe_title       = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "-")[:50]
        libro_dir        = os.path.join(biblioteca_dir, f"{fecha}_{safe_title}")
        os.makedirs(libro_dir, exist_ok=True)
        dest_path = os.path.join(libro_dir, os.path.basename(final_path))
        shutil.copy2(final_path, dest_path)
        logger.info(f"[Publicador] Libro copiado a Biblioteca: {dest_path}")
    except Exception as e:
        logger.warning(f"[Publicador] No se pudo copiar a Biblioteca (ignorado): {e}")

    # ── Limpiar directorio temporal ───────────────────────────────────────
    temp_dir = os.path.join(output_dir, "temp")
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"[Publicador] Directorio temporal limpiado: {temp_dir}")
        except Exception as e:
            logger.warning(f"[Publicador] No se pudo limpiar temp (ignorado): {e}")

    return {
        "book_status":      "complete",
        "final_book_path":  final_path,
        "cover_brief_path": cover_brief_path,
        "current_agent":    AgentName.COMPLETE.value,
        "system_warning":   cover_warning or "",
        "prefacio":         prefacio,
        "pagina_legal":     pagina_legal,
        "agradecimientos":  agradecimientos,
        "sobre_el_autor":   sobre_el_autor,
    }
