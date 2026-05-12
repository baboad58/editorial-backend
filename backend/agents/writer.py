"""
Agent 2 – El Escritor Investigador  v2.1
Role: Expert writer in the specific book niche.
Responsibility: Write chapter drafts and present them to the user for review.

DISEÑO DE INTERACCIÓN (único interrupt del agente):
─────────────────────────────────────────────────────────────────
El Escritor genera el borrador y lo presenta al usuario con UN SOLO interrupt.
El usuario tiene exactamente TRES opciones:

  1. APROBAR  → el borrador pasa al Editor tal como está (o con ediciones menores
               que el usuario hizo directamente en pantalla).

  2. EDITAR   → el usuario modifica el texto directamente en la interfaz y lo
               devuelve. El texto editado se acepta como versión final sin
               reescritura adicional del LLM.

  3. PEDIR CAMBIOS → el usuario describe qué quiere diferente. El Escritor
               reescribe el capítulo desde cero incorporando el feedback.

El interrupt devuelve el estado como JSON con este contrato:
  {
    "action":  "aprobar" | "editar" | "reescribir",
    "content": "<texto completo editado>",  # solo si action="editar"
    "feedback": "<instrucciones>"           # solo si action="reescribir"
  }

Compatibilidad: si la respuesta es texto plano (sin JSON), se interpreta como
"reescribir" con ese texto como feedback, o "aprobar" si contiene palabras clave.
También se aceptan los alias ingleses "approve"/"edit"/"rewrite" por retrocompatibilidad.

Cambios v2.1 vs v2.0:
  - Acción "editar" acepta el texto modificado por el usuario directamente,
    sin reenviar al LLM. Esto es lo que el usuario espera al editar en pantalla.
  - Acción renombrada "aprobar" (antes "accept") — normalizado a español.
  - Acción renombrada "reescribir" (antes "feedback") — normalizado a español.
  - hint del interrupt reescrito para ser instrucción clara al frontend.
  - Límite de reintentos aplica solo a "reescribir", no a "editar".
"""

import json
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from backend.graph.state import BookState
from backend.graph.utils import (
    retry_llm_call,
    PermanentError,
    AgentName,
    MAX_CHAPTER_REVISIONS,
    check_word_count,
    get_genre_word_limits,
    get_llm_for_agent,
    cached_system_message,
    trim_agent_feedback,
    logger,
)
from backend.tools.search import web_search

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres el Escritor Investigador: un escritor de élite con voz propia,
especializado en el nicho específico del libro que se está escribiendo.

## VOZ Y ESTILO

Tu escritura tiene tres compromisos fundamentales:

1. PRECISIÓN LÉXICA — cada palabra es la única palabra posible en esa posición.
   Nunca uses el primer verbo que aparezca. Si escribes "realizar", pregúntate:
   ¿es "hacer", "ejecutar", "consumar", "concretar"? El verbo exacto cambia el tono.
   Verbos que debes evitar activamente: realizar, llevar a cabo, implementar, desarrollar
   (en su uso genérico), generar, establecer, efectuar, proceder a, lograr (sin matiz).
   Adjetivos vacíos a eliminar: importante, fundamental, crucial, esencial, significativo,
   relevante, profundo (cuando no describe profundidad real), innegable, indudable.

2. RITMO VARIABLE — las frases no tienen todas el mismo largo.
   Alterna deliberadamente: frases cortas que golpean. Frases más largas que envuelven
   al lector en una idea y la desarrollan hasta que encuentra su propio peso y cierre.
   Una frase. Así.
   Y luego una que respira, que se extiende, que lleva al lector de la mano a través
   de un pensamiento complejo antes de soltarlo en la orilla.
   El ritmo monótono es la marca más reconocible del texto generado por IA.

3. APERTURA DE PÁRRAFO ÚNICA — nunca dos párrafos seguidos que empiecen igual.
   Varía: sujeto directo, complemento circunstancial, frase nominal, pregunta retórica,
   acción sin sujeto explícito, dato concreto, diálogo, descripción sensorial.
   Prohibido: empezar más de 2 párrafos seguidos con el mismo sujeto.

## ANTI-ROBOTIZACIÓN

Estas marcas delatan el texto de IA — evítalas activamente:

- Conectores de muleta: "sin embargo", "no obstante", "por otro lado", "en este sentido",
  "cabe destacar", "hay que tener en cuenta", "es importante señalar", "en conclusión".
  Úsalos solo cuando no exista otra forma — y si los usas, una vez por capítulo máximo.
- Estructura predictible: [sujeto] + [verbo genérico] + [complemento descriptivo].
  Rompe este patrón en al menos el 40% de las oraciones.
- Párrafos de introducción que anuncian lo que van a decir: nunca escribas
  "En este capítulo veremos...", "A continuación se describe...", "Como veremos...".
  Di directamente lo que tienes que decir.
- Cierre de párrafo con moraleja explícita: el lector no necesita que le expliques
  qué debe sentir. Muestra, no expliques. La emoción se genera, no se nombra.

## UNICIDAD DE CADA CAPÍTULO

Cada capítulo es una pieza única, no un molde repetido. Antes de escribir:
- ¿Qué imagen, metáfora o escena concreta define este capítulo y solo este?
- ¿Cuál es la oración más sorprendente que podrías escribir aquí?
- ¿Qué haría que el lector no pudiera parar al llegar a la mitad?

Siempre escribes en español a menos que el plan especifique otro idioma.
Cuando escribas un capítulo, incluye el contenido COMPLETO y final. No resumas ni abrevies."""

# ── Extensión de humanización (inyectada al SYSTEM_PROMPT si humanize_writing=True) ──
# Solo para ficción e infantil/juvenil. En no-ficción y académico no aplica.
HUMANIZE_ADDON = """

## IMPERFECCIÓN ACTIVA

La escritura humana no es escritura perfecta bien distribuida: es escritura
que sabe cuándo ser torpe. Aplica estas cinco reglas en cada capítulo:

1. UNA MALA DECISIÓN POR CAPÍTULO — el protagonista debe equivocarse en algo,
   aunque sea menor. No todo error tiene lección inmediata. A veces el personaje
   retrocede sin razón clara. Evita que cada acción conduzca limpiamente a la siguiente.

2. UNA FRASE FEA A PROPÓSITO — por cada 3 frases bien construidas, escribe una
   que sea directa, plana, sin imagen: 'Corrió. No sabía por qué. Solo corrió.'
   El contraste hace brillar las frases buenas; sin él, todas se anulan entre sí.

3. ASIMETRÍA EN LOS PERSONAJES — si dos personajes parecen complementarse
   perfectamente (uno/otro, fuerza/mente, valentía/prudencia), rómpelo al menos
   una vez: que el analítico actúe impulsivamente, que el valiente dude sin razón.
   La perfección complementaria constante es la señal más reconocible de IA.

4. AMBIGÜEDAD SIN RESOLVER — al menos una vez por capítulo, deja una motivación,
   acción o reacción sin explicar. La ambigüedad genera profundidad; la explicación
   la destruye. Ejemplo: muestra si el personaje ayuda por compasión o por
   necesidad de pertenecer de forma que ambas lecturas sean posibles.

5. DIÁLOGOS CON RUIDO — las personas se interrumpen, no terminan las frases,
   responden a lo que no se les preguntó. Al menos un diálogo por capítulo
   debe tener una respuesta incompleta o un silencio significativo.
   Ejemplo de tono (no copiar): '¿No deberíamos...? / Ya sé. Pero igual.'

## REFUERZO ANTI-SIMETRÍA

Vigila estos patrones estadísticamente detectables:

- Simetría binaria constante: 'Uno era X, el otro era Y' — úsala como máximo
  UNA VEZ por capítulo. El resto del tiempo describe cada elemento por separado,
  desde ángulos distintos, en momentos diferentes del texto.
- Estructuras repetidas: si usas 'No era X. Era Y.' más de dos veces en el
  capítulo, reescribe al menos dos instancias con estructura diferente.
- Densidad de metáforas: si un párrafo tiene más de una metáfora o comparación,
  elimina la más débil. Alterna imagen y lenguaje directo.

## VOZ VERNÁCULA

La diferencia entre prosa académica y prosa humana no está en la estructura —
está en cómo la gente realmente piensa y habla. Aplica estas reglas de registro:

**LÉXICO COTIDIANO SOBRE LÉXICO ELEVADO**
Usa siempre la palabra que diría el narrador en una conversación, no la más literaria.
  "De repente" no "súbitamente". "Raro" no "inusual". "Ver" no "percibir".
  "Mucha gente" no "numerosas personas". "Rápido" no "velozmente".
  "Asustado" no "atemorizado". "Empezar" no "comenzar a proceder".
Los sustantivos simples son válidos: "cosa", "momento", "lugar", "tipo", "gente"
funcionan cuando la precisión no añade nada. Vocabulario elevado sin propósito
específico es la marca más clara de texto de máquina.

**TIEMPOS VERBALES CON NATURALIDAD**
- Presente histórico para escenas de acción intensa: "Corre hacia la puerta.
  La abre de golpe. Nada. Solo oscuridad." Alterna con pasado en el mismo
  capítulo — el cambio de tiempo crea urgencia real.
- Evita el futuro simple en narración interna: "Va a ser complicado" suena
  a pensamiento; "Será complicado" suena a declaración oficial.
- En diálogos, los personajes usan el tiempo que usarían en la vida:
  el futuro coloquial ("te llamo", "voy y vengo"), el condicional informal
  ("si lo sabía, no venía"), la omisión del sujeto cuando el contexto lo da.

**SINTAXIS QUE ROMPE LA ACADEMIA**
- Una oración por página puede empezar con "Y", "Pero", "Porque" o "O".
  No es error — es voz que piensa en voz alta. Úsalo con intención.
- Frase nominal sin verbo cuando la situación lo permite: "Silencio absoluto.
  Tres segundos. Cuatro. Cinco." No necesita verbo para golpear.
- Pregunta genuina que el narrador deja flotando antes de responder — no
  retórica decorativa, sino duda real que cuelga en el aire dos párrafos.
- Construcciones informales con propósito: "La cosa es que...", "Lo que pasa
  es que...", "Fue entonces cuando..." — en narración o voz interior,
  suenan a persona real, no a manual de estilo.

**IMPRECISIÓN Y RUIDO HUMANO**
- Cuando el personaje no recuerda con exactitud: "fue... ¿martes? No, miércoles."
- Imprecisión temporal cuando la emoción importa más que el dato:
  "llevaba horas ahí, o minutos — ya no había diferencia."
- Repetición de la palabra exacta cuando no existe sinónimo natural. Un personaje
  puede "correr" tres veces en una escena. Forzar variación ("trotar", "precipitarse",
  "avanzar rápido") suena a tesauro, no a persona.
- Hipérbole cotidiana sin marca literaria: "se le heló el estómago",
  "el corazón le pegó un salto", "estaba muerto de cansancio" — son válidas
  cuando la situación las hace frescas, no decorativas."""

WRITE_PROMPT = """Escribe el CAPÍTULO COMPLETO con la siguiente especificación:

## CONTEXTO DEL LIBRO
- Título: {title}
- Género: {genre}
- Audiencia: {target_audience}
- Tono: {tone}
- Estilo: {writing_style}
- Arco del libro: {book_arc}

## CAPÍTULO A ESCRIBIR
- Número: {chapter_num} de {total_chapters}
- Título: {chapter_title}
- Rol en el arco del libro: {arc_role}
- Resumen: {chapter_summary}
- Puntos clave a cubrir: {key_points}
- Extensión: {word_count_instruction}

## CONTEXTO DE CAPÍTULOS ANTERIORES
{previous_context}

{research_section}

## VERACIDAD E INTEGRIDAD DE LA INFORMACIÓN

Estas reglas son INAPELABLES — no tienen excepciones:

Para NO-FICCIÓN PRÁCTICA (negocios, autoayuda, técnico, salud):
- Todo dato, estadística o caso real debe aparecer en AL MENOS 2 fuentes
  independientes de las provistas. Si solo aparece en una, omítelo.
- NO inventar, estimar ni completar datos con tu conocimiento de entrenamiento.
- Citar la fuente en el texto: (Fuente: [título], [URL]) inmediatamente después del dato.
- Si no tienes fuente verificada, usa lenguaje de probabilidad explícita:
  "según reportan algunas organizaciones del sector..." — nunca afirmar como hecho.

Para textos ACADÉMICOS / CIENTÍFICOS (ensayo, divulgación, histórico, científico):
- Todo dato factual requiere AL MENOS 4 fuentes independientes verificadas.
- Citar en formato académico completo: Autor(es). (Año). Título. Revista/Fuente,
  vol(num), pp. DOI o URL. Sin autor o año verificable → no usar la fuente.
- Distinguir entre: hecho probado (citar), consenso científico (indicar fuentes
  del consenso), hipótesis (indicar explícitamente que es hipótesis), opinión
  (atribuirla al autor con nombre).
- PROHIBIDO: extrapolar, inferir, asumir ni completar datos de fuentes.
  Si la fuente dice X, citar X exactamente. No "X implica Y".

Para FICCIÓN e INFANTIL/JUVENIL:
- No se usa investigación web. La imaginación y coherencia interna son la fuente.
- Si mencionas un dato del mundo real (fecha histórica, lugar, cifra),
  debe ser verificable. En caso de duda, ficcionaliza el dato.

## INSTRUCCIÓN DE APERTURA
{opening_instruction}

## ANTES DE ESCRIBIR — responde internamente estas preguntas (no las incluyas en el texto):
1. ¿Cuál es la imagen o escena más concreta y específica que define este capítulo?
2. ¿Cuál es la oración más inesperada o sorprendente que podría abrir o cerrar una sección?
3. ¿Qué variación de ritmo usaré — dónde las frases serán muy cortas y dónde muy largas?
{humanize_questions}
Ahora escribe el capítulo completo. Comienza directamente con el contenido,
sin encabezados meta como "Capítulo X:" (eso lo agrega el maquetador).
Escribe {word_count_instruction}."""

REWRITE_PROMPT = """El usuario ha solicitado cambios al borrador del capítulo.

## CONTEXTO DEL LIBRO (mantener siempre)
- Título: {title}
- Género: {genre}
- Tono: {tone}
- Estilo: {writing_style}
- Arco del libro: {book_arc}

## CAPÍTULO EN REVISIÓN
- Número: {chapter_num} de {total_chapters}
- Título: {chapter_title}
- Rol en el arco: {arc_role}

## HISTORIAL COMPLETO DE CAMBIOS SOLICITADOS (resolver TODOS, no solo el último):
{rewrite_history_block}

## BORRADOR ANTERIOR:
{previous_draft}

## INSTRUCCIÓN DE APERTURA (mantener en la reescritura)
{opening_instruction}

Reescribe el capítulo incorporando TODOS los cambios del historial.
Mantén el tono, estilo y arc_role — no cambies lo que el usuario no cuestionó.
Escribe el capítulo COMPLETO revisado ({word_count_instruction})."""

EDITOR_REWRITE_PROMPT = """El Editor rechazó este capítulo y requiere mejoras.

## CONTEXTO DEL LIBRO (mantener siempre)
- Título: {title}
- Género: {genre}
- Tono: {tone}
- Estilo: {writing_style}
- Arco del libro: {book_arc}

## CAPÍTULO EN CORRECCIÓN
- Número: {chapter_num} de {total_chapters}
- Título: {chapter_title}
- Rol en el arco: {arc_role}

## HISTORIAL COMPLETO DE RECHAZOS DEL EDITOR (resolver TODOS, no solo el último):
{editor_history_block}

## BORRADOR RECHAZADO:
{previous_draft}

## INSTRUCCIÓN DE APERTURA (mantener en la corrección)
{opening_instruction}

Aborda TODOS los problemas del historial — contenido Y prosa.
Si el Editor señaló texto robotizado, corrígelo además del contenido.
El contexto del libro es el ancla; el historial del editor es la guía.
Escribe el capítulo COMPLETO corregido ({word_count_instruction})."""


LAYOUTER_REWRITE_PROMPT = """El Maquetador editorial rechazó este capítulo por exceder el límite de extensión del género.

## CONTEXTO DEL LIBRO
- Título: {title}
- Género: {genre}
- Audiencia: {target_audience}
- Tono: {tone}
- Estilo: {writing_style}

## CAPÍTULO A REDUCIR
- Número: {chapter_num} de {total_chapters}
- Título: {chapter_title}
- Rol en el arco: {arc_role}

## ⚠️ INSTRUCCIÓN OBLIGATORIA DE EXTENSIÓN
El capítulo tiene {actual_words} palabras. El límite para el género '{genre}' es {max_words} palabras.
Debes reescribir con un MÁXIMO de {max_words} palabras — esta restricción no tiene excepción.
Estrategia: condensa escenas secundarias, elimina adjetivación redundante, prioriza acción y diálogo.
NO amplíes ni añadas nuevo contenido — solo reduce y condensa lo existente.

## FEEDBACK DEL MAQUETADOR:
{layouter_feedback}

## BORRADOR A REDUCIR:
{previous_draft}

Reescribe el capítulo completo con un máximo de {max_words} palabras.
Mantén los puntos clave del plan, la voz del libro y el arc_role '{arc_role}'."""


# ── Temperatura dinámica por género ──────────────────────────────────────────

# Mapa familia → temperatura óptima
_GENRE_TEMPERATURE: dict[str, float] = {
    "ficcion":           0.9,   # máxima creatividad, variedad léxica, sorpresa
    "infantil_juvenil":  0.7,   # creatividad con consistencia de voz
    "no_ficcion":        0.5,   # balance claridad / ejemplos frescos
    "academico_ensayo":  0.3,   # precisión y coherencia argumentativa
}

_DEFAULT_TEMPERATURE = 0.7


def _get_temperature(genre: str) -> float:
    """
    Retorna la temperatura óptima según la familia de género.
    Reutiliza las listas de _NO_RESEARCH_GENRES y _RESEARCH_GENRES
    para no duplicar la clasificación.
    """
    g = genre.lower()

    # Infantil / juvenil — evaluar ANTES de ficción adulta
    # ("novela de aventuras juvenil" debe dar 0.7, no 0.9)
    infantil_keywords = ["infantil", "juvenil", "young adult", "ya", "álbum"]
    if any(k in g for k in infantil_keywords):
        return _GENRE_TEMPERATURE["infantil_juvenil"]

    # Ficción adulta
    ficcion_keywords = [
        "novela", "cuento", "thriller", "romance", "ciencia ficción",
        "fantasía", "horror", "aventura", "misterio", "ficción", "narrativa",
    ]
    if any(k in g for k in ficcion_keywords):
        return _GENRE_TEMPERATURE["ficcion"]

    # Académico / ensayo
    academico_keywords = [
        "ensayo", "académico", "divulgación", "científico",
        "histórico", "filosófico", "político", "investigación",
    ]
    if any(k in g for k in academico_keywords):
        return _GENRE_TEMPERATURE["academico_ensayo"]

    # No-ficción práctica
    no_ficcion_keywords = [
        "autoayuda", "negocios", "liderazgo", "productividad", "finanzas",
        "técnico", "tecnología", "marketing", "guía", "manual", "salud",
    ]
    if any(k in g for k in no_ficcion_keywords):
        return _GENRE_TEMPERATURE["no_ficcion"]

    return _DEFAULT_TEMPERATURE


# ── LLM ──────────────────────────────────────────────────────────────────────

def _get_llm(genre: str = "") -> ChatAnthropic:
    temperature = _get_temperature(genre)
    logger.info(f"[Escritor] Temperatura seleccionada: {temperature} (género: '{genre}')")
    return get_llm_for_agent(AgentName.WRITER.value, temperature=temperature, max_tokens=8192)


# ── Helpers ───────────────────────────────────────────────────────────────────

# Géneros que se benefician de investigación web
_RESEARCH_GENRES = {
    "no_ficcion_practica": [
        "autoayuda", "negocios", "liderazgo", "productividad", "finanzas",
        "técnico", "tecnología", "marketing", "ventas", "emprendimiento",
        "salud", "nutrición", "educación", "guía", "manual", "how-to",
    ],
    "academico_ensayo": [
        "ensayo", "académico", "divulgación", "científico", "histórico",
        "filosófico", "político", "sociológico", "psicológico", "biográfico",
        "investigación", "análisis",
    ],
}

# Géneros donde la web no aporta — el LLM usa su conocimiento narrativo
_NO_RESEARCH_GENRES = [
    "novela", "cuento", "thriller", "romance", "ciencia ficción", "fantasía",
    "horror", "aventura", "misterio", "ficción", "narrativa",
    "infantil", "juvenil", "young adult", "ya", "álbum ilustrado", "picture book",
]


# Nivel de rigor en la investigación por familia de género
# NONE     → sin búsqueda (ficción, infantil)
# STANDARD → verificar en ≥2 fuentes independientes (no-ficción práctica)
# STRICT   → verificar en ≥4 fuentes, citar con formato académico (científico, académico)
_STRICT_GENRES = [
    "científico", "científica", "académico", "académica",
    "investigación", "estudio", "paper", "tesis",
    "histórico", "histórica", "médico", "médica",
    "jurídico", "jurídica", "económico", "económica",
    "psicológico", "psicológica", "sociológico", "sociológica",
]


def _research_level(genre: str) -> str:
    """
    Retorna el nivel de rigor requerido para la investigación:
      "NONE"     — sin búsqueda (ficción, infantil/juvenil)
      "STANDARD" — verificación en ≥2 fuentes (no-ficción práctica)
      "STRICT"   — verificación en ≥4 fuentes, cita académica (científico/académico)
    """
    if not _should_research(genre):
        return "NONE"
    g = genre.lower()
    if any(k in g for k in _STRICT_GENRES):
        return "STRICT"
    return "STANDARD"


def _should_research(genre: str) -> bool:
    """
    Determina si el capítulo se beneficia de búsqueda web.
    Ficción e infantil/juvenil no — la web aporta ruido, no valor narrativo.
    No-ficción práctica y académico/ensayo sí — datos y fuentes reales importan.
    """
    genre_lower = genre.lower()

    # Primero verificar si es explícitamente un género sin investigación
    for no_research in _NO_RESEARCH_GENRES:
        if no_research in genre_lower:
            return False

    # Luego verificar si es un género que sí se beneficia
    for research_list in _RESEARCH_GENRES.values():
        for keyword in research_list:
            if keyword in genre_lower:
                return True

    # Género desconocido → investigar por precaución
    return True


def _build_research_query(chapter_outline: dict, genre: str) -> str:
    """
    Construye una query de búsqueda limpia basada en el TEMA real del capítulo,
    sin contaminar con el título del libro.

    Para no-ficción práctica: enfocarse en datos, casos, estadísticas.
    Para académico/ensayo: enfocarse en fuentes, estudios, argumentos.
    """
    kp    = chapter_outline.get("key_points", [])
    title = chapter_outline.get("title", "")
    genre_lower = genre.lower()

    # Base: tema del capítulo (sin nombre del libro)
    query = title

    # Añadir key_points más relevantes como términos de búsqueda
    if kp:
        # Tomar los primeros 2 key_points, limpiar de verbos instructivos
        terms = []
        for kp_item in kp[:2]:
            # Limpiar frases tipo "Aprender X" → "X"
            clean = kp_item
            for prefix in ["aprender ", "entender ", "conocer ", "definir ",
                           "explicar ", "describir ", "analizar ", "presentar "]:
                if clean.lower().startswith(prefix):
                    clean = clean[len(prefix):]
                    break
            terms.append(clean.strip())
        query += " " + " ".join(terms)

    # Añadir calificador de tipo de resultado según género
    is_academic = any(k in genre_lower for k in
                      ["académico", "ensayo", "científico", "histórico", "filosófico"])
    if is_academic:
        query += " investigación estudio"
    else:
        query += " casos ejemplos datos"

    return query.strip()


def _do_research(chapter_outline: dict, book_title: str, genre: str = "") -> str:
    """
    Investigación web con nivel de rigor adaptativo.

    NONE     → sin búsqueda (ficción / infantil-juvenil)
    STANDARD → 1 query, 3 resultados, verificación cruzada en ≥2 fuentes
    STRICT   → 3 queries desde ángulos distintos, 5 resultados c/u,
               verificación en ≥4 fuentes independientes, cita académica
    """
    level = _research_level(genre)

    if level == "NONE":
        logger.info(
            f"[Escritor] Género '{genre}' — sin búsqueda web. "
            "Usando conocimiento narrativo del LLM."
        )
        return (
            "Este género no requiere investigación web. "
            "Usa tu conocimiento narrativo, imaginación y dominio del género. "
            "Prioriza la coherencia con los capítulos anteriores y el arco definido."
        )

    query_base = _build_research_query(chapter_outline, genre)
    kp         = chapter_outline.get("key_points", [])
    ch_title   = chapter_outline.get("title", "")

    try:
        if level == "STANDARD":
            # Una query, 3 resultados — verificación ≥2 fuentes
            results = web_search(query_base, max_results=3)
            logger.info(f"[Escritor] STANDARD: '{query_base}' → {len(results)} resultados")

            if not results:
                return "Sin resultados externos. Usa tu conocimiento experto verificado del dominio."

            block = _format_standard_results(results)
            return block

        else:  # STRICT
            # 3 queries desde ángulos distintos → mayor diversidad de fuentes
            queries = _build_strict_queries(ch_title, kp, genre)
            all_results = []
            seen_urls   = set()

            for q in queries:
                try:
                    r = web_search(q, max_results=5)
                    for item in r:
                        url = item.get("url", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append(item)
                    logger.info(f"[Escritor] STRICT query: '{q}' → {len(r)} resultados")
                except Exception as e:
                    logger.warning(f"[Escritor] Query '{q}' falló: {e}")

            if not all_results:
                return "Sin resultados externos. Usa únicamente conocimiento propio verificado."

            block = _format_strict_results(all_results)
            return block

    except Exception as e:
        logger.warning(f"[Escritor] Investigación web falló ({type(e).__name__}).")
        return "[Investigación no disponible. Continúa con conocimiento propio verificable.]"


def _build_strict_queries(ch_title: str, key_points: list, genre: str) -> list[str]:
    """
    Genera 3 queries independientes para el nivel STRICT,
    desde ángulos distintos para maximizar diversidad de fuentes.
    """
    kp0 = key_points[0] if len(key_points) > 0 else ch_title
    kp1 = key_points[1] if len(key_points) > 1 else ch_title

    # Limpiar verbos instructivos de los key_points
    for prefix in ["aprender ", "entender ", "conocer ", "definir ",
                   "explicar ", "describir ", "analizar ", "presentar "]:
        kp0 = kp0[len(prefix):] if kp0.lower().startswith(prefix) else kp0
        kp1 = kp1[len(prefix):] if kp1.lower().startswith(prefix) else kp1

    is_scientific = any(k in genre.lower() for k in
                        ["científico", "médico", "biológico", "físico", "químico"])

    if is_scientific:
        return [
            f"{ch_title} estudio científico peer review",
            f"{kp0.strip()} investigación evidencia",
            f"{kp1.strip()} metaanálisis revisión sistemática",
        ]
    else:
        return [
            f"{ch_title} investigación académica fuentes",
            f"{kp0.strip()} análisis datos verificados",
            f"{kp1.strip()} estudio evidencia",
        ]


def _format_standard_results(results: list) -> str:
    """
    Formatea resultados para nivel STANDARD con instrucciones de verificación cruzada.
    """
    lines = [
        "## FUENTES ENCONTRADAS — nivel STANDARD",
        "REGLA INAPELABLE: Solo incluir datos que aparezcan en AL MENOS 2 fuentes",
        "independientes de esta lista. Si un dato aparece en una sola fuente, NO lo uses.",
        "NO inventar, completar ni ampliar datos con conocimiento propio.",
        "",
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"[Fuente {i}]")
        lines.append(f"Título: {r.get('title', 'Sin título')}")
        lines.append(f"URL: {r.get('url', 'Sin URL')}")
        lines.append(f"Contenido: {r.get('content', '')[:500]}")
        lines.append("")

    lines += [
        "Al citar en el texto usa el formato:",
        '  "[dato] (Fuente: [título], [URL])"',
        "Si no puedes verificar un dato en ≥2 fuentes de esta lista, omítelo.",
    ]
    return "\n".join(lines)


def _format_strict_results(results: list) -> str:
    """
    Formatea resultados para nivel STRICT con instrucciones de citación académica.
    """
    lines = [
        "## FUENTES ENCONTRADAS — nivel STRICT (científico/académico)",
        "REGLA INAPELABLE: Solo incluir datos verificados en AL MENOS 4 fuentes",
        "independientes de esta lista. Si aparece en menos, NO lo uses.",
        "PROHIBIDO: inventar, estimar, completar, extrapolar o asumir datos.",
        "",
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"[Fuente {i}]")
        lines.append(f"Título: {r.get('title', 'Sin título')}")
        lines.append(f"URL: {r.get('url', 'Sin URL')}")
        lines.append(f"Contenido: {r.get('content', '')[:500]}")
        lines.append("")

    lines += [
        "FORMATO DE CITA OBLIGATORIO para textos académicos/científicos:",
        "  Cita en el texto: (Apellido, Año, p. XX) o [N]",
        "  Al pie o en sección de referencias:",
        "    Autor(es). (Año). Título del artículo. Nombre de la revista/fuente,",
        "    volumen(número), páginas. https://doi.org/XXXXX o URL verificada",
        "",
        "Si la fuente web no tiene autor, año o DOI verificable, NO la uses.",
        "Toda afirmación factual debe tener su cita. Sin excepción.",
    ]
    return "\n".join(lines)




def _build_previous_context(state: BookState) -> str:
    """
    Construye el contexto de capítulos anteriores relevantes.
    1. Si el capítulo tiene dependencies explícitas → traer esos capítulos.
    2. Si no → traer los últimos 2 (comportamiento clásico).
    """
    approved = state.get("approved_chapters", [])
    if not approved:
        return "Este es el primer capítulo del libro."

    chapter_index = state.get("current_chapter_index", 0)
    outlines      = state.get("chapter_outlines", [])

    # Dependencias declaradas del capítulo actual
    current_outline = outlines[chapter_index] if chapter_index < len(outlines) else {}
    declared_deps   = current_outline.get("dependencies", None)

    # Índice de capítulos aprobados por su posición original
    approved_by_index = {ch["index"]: ch for ch in approved}

    if declared_deps:
        relevant     = [approved_by_index[d] for d in declared_deps if d in approved_by_index]
        source_label = "Capítulos requeridos por este capítulo (según el plan)"
    else:
        relevant     = approved[-2:]
        source_label = "Capítulos anteriores aprobados (resumen)"

    if not relevant:
        return "No hay capítulos previos relevantes disponibles aún."

    summaries = []
    for ch in relevant:
        summaries.append(
            f"Capítulo {ch['index'] + 1} \u2013 {ch['title']}:\n"
            f"{ch['content'][:500]}\u2026"
        )
    return f"{source_label}:\n\n" + "\n\n".join(summaries)


def _parse_user_response(raw: str, fallback_draft: str) -> tuple[str, str, str]:
    """
    Parsea la respuesta del usuario al interrupt de revisión.

    Retorna: (action, draft_final, feedback_texto)
      action:       "aprobar" | "editar" | "reescribir"
      draft_final:  texto del capítulo a usar (editado por el usuario o el borrador original)
      feedback_texto: instrucciones para reescritura (solo si action="reescribir")
    """
    try:
        data     = json.loads(raw)
        action   = str(data.get("action", "")).lower().strip()

        if action in ("aprobar", "approve", "accept"):   # aliases inglés para retrocompatibilidad
            # El usuario aprueba el texto tal como está
            content = data.get("content") or fallback_draft
            return "aprobar", content, ""

        if action in ("editar", "edit"):
            # El usuario editó el texto directamente en pantalla
            # Se acepta su versión sin ninguna reescritura del LLM
            content = data.get("content") or fallback_draft
            if not content.strip():
                logger.warning("[Escritor] Acción 'editar' sin contenido. Usando borrador original.")
                content = fallback_draft
            return "editar", content, ""

        if action in ("reescribir", "rewrite"):
            # El usuario quiere que el LLM reescriba con nuevas instrucciones
            feedback = data.get("feedback", "").strip()
            if not feedback:
                feedback = "Mejora el capítulo en general."
            return "reescribir", fallback_draft, feedback

        # Acción desconocida → tratar como reescribir con el texto completo como feedback
        logger.warning(f"[Escritor] Acción desconocida '{action}'. Tratando como reescribir.")
        return "reescribir", fallback_draft, raw

    except (json.JSONDecodeError, TypeError):
        # Texto plano — compatibilidad con respuestas sin estructura JSON
        lower = raw.lower().strip()
        is_approval = any(w in lower for w in [
            "apruebo", "aprobado", "conforme", "sí", "si", "ok", "bien",
            "perfecto", "adelante", "listo", "yes", "genial", "excelente",
        ])
        if is_approval:
            return "aprobar", fallback_draft, ""
        else:
            # Cualquier otro texto se interpreta como instrucciones de reescritura
            return "reescribir", fallback_draft, raw


def _get_opening_instruction(arc_role: str, genre: str) -> str:
    """
    Retorna una instrucción específica de apertura según el arc_role del capítulo.
    El primer párrafo es lo que el Editor evalúa primero y lo que engancha al lector.
    La técnica varía según el rol del capítulo en el arco y el género.
    """
    role        = arc_role.lower()
    genre_lower = genre.lower()
    is_fiction  = any(k in genre_lower for k in [
        "novela", "cuento", "thriller", "romance", "fantasía", "ficción",
        "horror", "aventura", "infantil", "juvenil", "young adult",
    ])

    if any(k in role for k in ["presentación", "introducción", "apertura", "inicio"]):
        if is_fiction:
            return (
                "APERTURA — In medias res suave: muestra al personaje o al mundo en acción "
                "desde la primera línea, sin describir ni explicar. "
                "El lector debe estar dentro de la escena antes de saber dónde está. "
                'Evita presentaciones del tipo "Era una mañana de...".'
            )
        else:
            return (
                "APERTURA — Gancho inmediato: abre con un dato sorprendente, una paradoja "
                "o una pregunta que el lector no pueda ignorar. "
                "La primera oración debe crear una tensión o curiosidad que solo el capítulo resuelve."
            )

    if any(k in role for k in ["crisis", "clímax", "climax", "tensión", "conflicto", "peligro"]):
        return (
            "APERTURA — Alta tensión: la primera línea ya debe estar en el corazón del conflicto. "
            "Sin preámbulo, sin contexto previo — el lector entra al momento de máxima urgencia. "
            "Ritmo corto, fragmentado, como latidos acelerados. "
            'Ejemplo de tono (no copiar): "El suelo tembló antes de que escuchara el disparo."'
        )

    if any(k in role for k in ["resolución", "cierre", "final", "conclusión", "desenlace"]):
        if is_fiction:
            return (
                "APERTURA — Eco del viaje: la primera línea debe resonar con el inicio del libro "
                "o con un momento clave anterior, creando un círculo narrativo. "
                "El lector debe sentir que este capítulo cierra algo que quedó abierto. "
                "Tono más lento, más contemplativo que los capítulos anteriores."
            )
        else:
            return (
                "APERTURA — Síntesis poderosa: abre con la idea central que el libro ha construido, "
                "formulada de la manera más clara y memorable posible. "
                "Este es el momento en que el lector debe sentir que todo encaja."
            )

    if any(k in role for k in ["diagnóstico", "problema", "planteamiento", "tesis"]):
        return (
            "APERTURA — El dolor concreto: abre mostrando el problema en su máxima concreción, "
            "con un ejemplo real, un caso, una situación que el lector reconozca como propia. "
            "Primero el dolor, luego el análisis — nunca al revés. "
            'La primera oración debe hacer que el lector piense: "eso me pasa a mí".'
        )

    if any(k in role for k in ["obstáculo", "giro", "complicación", "quiebre"]):
        return (
            "APERTURA — In medias res duro: empieza en el instante exacto del obstáculo o giro, "
            "sin preparación. El lector no sabe qué pasó antes — lo descubre junto al personaje. "
            "Frases cortas, acción inmediata, sin adjetivos innecesarios."
        )

    if any(k in role for k in ["herramientas", "técnicas", "métodos", "estrategias"]):
        return (
            "APERTURA — Promesa de transformación: la primera oración debe decirle al lector "
            "exactamente qué va a poder hacer diferente al terminar este capítulo. "
            "Concreta, sin rodeos: no 'en este capítulo veremos', "
            "sino 'después de esto, nunca volverás a [problema] de la misma forma'."
        )

    if any(k in role for k in ["consolidación", "aprendizaje", "integración", "práctica"]):
        return (
            "APERTURA — Puente de sentido: conecta lo aprendido con lo que viene, "
            "usando una metáfora o imagen que encarne la transformación del lector hasta aquí. "
            "Tono más cálido, más cercano — el lector ya es un iniciado, trátalo como tal."
        )

    if any(k in role for k in ["evidencia", "argumentación", "demostración", "análisis"]):
        return (
            "APERTURA — Afirmación provocadora: abre con la tesis o hallazgo más sorprendente "
            "del capítulo, enunciado con total seguridad. "
            "La estructura es: afirmación audaz → el resto del capítulo la demuestra. "
            "Evita aperturas que anuncien lo que van a hacer — hazlo directamente."
        )

    if any(k in role for k in ["desarrollo", "avance", "progresión"]):
        if is_fiction:
            return (
                "APERTURA — Continuidad con tensión nueva: retoma el hilo del capítulo anterior "
                "pero añade un elemento nuevo en las primeras líneas que cambie el tono o dirección. "
                "El lector debe sentir que algo ha cambiado aunque no sepa exactamente qué."
            )
        else:
            return (
                "APERTURA — Gancho de profundidad: formula la pregunta específica que este capítulo "
                "responde, de forma que el lector sienta que necesita la respuesta. "
                "Diferente del planteamiento inicial — aquí ya hay contexto, el lector sabe más."
            )

    # Fallback
    return (
        "APERTURA — Primera línea memorable: la primera oración debe poder existir sola, "
        "sin el contexto del resto del capítulo. "
        "Evita empezar con 'En este capítulo', 'A continuación', 'Como vimos' "
        "o cualquier frase de transición. Entra directamente al contenido más importante."
    )


def _build_book_context_summary(state: BookState, chapter: dict) -> dict:
    """
    Construye el diccionario de contexto del libro reutilizable
    en los tres tipos de prompt (WRITE, REWRITE, EDITOR_REWRITE).
    Centraliza la extracción para que nunca falte contexto en reescrituras.
    """
    chapter_index = state.get("current_chapter_index", 0)
    arc_data      = state.get("book_arc", {})
    book_arc_summary = (
        f"Apertura: {arc_data.get('opening', '—')} | "
        f"Desarrollo: {arc_data.get('development', '—')} | "
        f"Resolución: {arc_data.get('resolution', '—')}"
    ) if arc_data else "Arco no definido"

    genre   = state.get("genre", "")
    arc_role = chapter.get("arc_role", "desarrollo")

    # Calcular target efectivo respetando límites del género
    word_count_target = chapter.get("word_count_target", 3500)
    genre_min, genre_max = get_genre_word_limits(genre)
    if genre_max and word_count_target > genre_max:
        effective_target = genre_max
        word_count_instruction = (
            f"entre {genre_min} y {genre_max} palabras "
            f"(límite del género — no superes {genre_max})"
        )
    else:
        effective_target = word_count_target
        word_count_instruction = f"al menos {effective_target} palabras"

    return {
        "title":                  state.get("title", "Sin título"),
        "genre":                  genre,
        "target_audience":        state.get("target_audience", ""),
        "tone":                   state.get("tone", ""),
        "writing_style":          state.get("writing_style", ""),
        "book_arc":               book_arc_summary,
        "chapter_num":            chapter_index + 1,
        "total_chapters":         state.get("num_chapters", 1),
        "chapter_title":          chapter["title"],
        "arc_role":               arc_role,
        "chapter_summary":        chapter.get("summary", ""),
        "key_points":             ", ".join(chapter.get("key_points", [])),
        "word_count":             effective_target,
        "word_count_instruction": word_count_instruction,
        "opening_instruction":    _get_opening_instruction(arc_role, genre),
    }


def _build_rewrite_history_block(history: list[str]) -> str:
    """
    Construye el bloque de historial de reescrituras para el REWRITE_PROMPT.
    Mismo patrón que _build_feedback_context() en architect.py.

    Con un solo feedback:
      [Reescritura 1] más diálogo entre los personajes

    Con múltiples:
      [Reescritura 1] más diálogo entre los personajes
      [Reescritura 2] acortar el primer párrafo
      [Reescritura 3] el tono es muy formal para el género
      Todos estos cambios deben estar presentes en la versión final.
    """
    if not history:
        return "Sin historial previo."

    lines = []
    for i, fb in enumerate(history, 1):
        lines.append(f"  [Reescritura {i}] {fb}")

    if len(history) > 1:
        lines.append(
            "  Todos estos cambios deben estar presentes en la versión final."
        )
    return "\n".join(lines)


def _build_editor_history_block(history: list[str]) -> str:
    """
    Construye el bloque de historial de rechazos del Editor para
    el EDITOR_REWRITE_PROMPT. Igual patrón que _build_rewrite_history_block.
    Usa solo los últimos 2 rechazos — el Escritor no necesita más para corregir.
    """
    if not history:
        return "Sin historial previo de rechazos del Editor."

    recent = history[-2:]
    lines = [f"El Editor ha rechazado {len(history)} versión(es) de este capítulo (mostrando los últimos {len(recent)}):"]
    for i, fb in enumerate(recent, len(history) - len(recent) + 1):
        # Truncar cada entrada para evitar que el historial acumulado infle el contexto
        lines.append(f"\n[Rechazo {i}]\n{trim_agent_feedback(fb)}")
    if len(recent) > 1:
        lines.append(
            "\nTodos los problemas anteriores deben estar resueltos en la nueva versión."
        )
    return "\n".join(lines)


# ── Nodo principal ────────────────────────────────────────────────────────────

def writer_node(state: BookState) -> dict:
    """
    Writer node — MODO AUTOMÁTICO (sin interrupt de usuario).

    Flujo:
      1. Genera el borrador (primera vez o reescritura por feedback del Editor).
      2. Envía automáticamente al Editor sin pasar por el usuario.
      El Editor revisa, rechaza con feedback → el Escritor reescribe automáticamente.
      Este ciclo continúa hasta que el Editor aprueba o se alcanza MAX_EDITOR_REJECTIONS.
    """
    genre         = state.get("genre", "")
    llm           = _get_llm(genre)
    chapter_index = state.get("current_chapter_index", 0)
    outlines      = state.get("chapter_outlines", [])
    chapter       = outlines[chapter_index]
    layouter_feedback = state.get("layouter_feedback", "")
    editor_feedback   = state.get("editor_feedback", "")
    previous_draft    = state.get("current_draft", "")
    draft_revision    = state.get("draft_revision", 0)
    rewrite_history   = state.get("chapter_rewrite_history", [])

    # ── Humanización: leer flag y preparar system prompt + preguntas ──────
    humanize = state.get("humanize_writing", False)
    effective_system = SYSTEM_PROMPT + HUMANIZE_ADDON if humanize else SYSTEM_PROMPT
    humanize_questions = (
        "4. ¿En qué momento el protagonista se equivoca, duda sin razón o retrocede?\n"
        "5. ¿Qué queda sin explicar — qué ambigüedad intencional dejo al lector?\n"
    ) if humanize else ""

    # ── 1. Generar borrador ────────────────────────────────────────────────
    ctx = _build_book_context_summary(state, chapter)
    editor_feedback_history = state.get("editor_feedback_history", [])

    if layouter_feedback and previous_draft:
        # El Maquetador rechazó por extensión — usar prompt con límite MÁXIMO
        _, genre_max = get_genre_word_limits(genre)
        actual_words = len(previous_draft.split())
        rejection_num = state.get("layouter_rejection_count", 1)
        prompt = LAYOUTER_REWRITE_PROMPT.format(
            title=ctx["title"],
            genre=genre,
            target_audience=ctx["target_audience"],
            tone=ctx["tone"],
            writing_style=ctx["writing_style"],
            chapter_num=ctx["chapter_num"],
            total_chapters=ctx["total_chapters"],
            chapter_title=ctx["chapter_title"],
            arc_role=ctx["arc_role"],
            actual_words=actual_words,
            max_words=genre_max or ctx["word_count"],
            layouter_feedback=layouter_feedback,
            previous_draft=previous_draft,
        )
        draft_note = (
            f"Reescritura por Maquetador "
            f"(intento {rejection_num}/{2})"
        )

    elif editor_feedback and previous_draft:
        # El Editor rechazó — reescritura automática con historial completo
        editor_history_block = _build_editor_history_block(editor_feedback_history)
        prompt = EDITOR_REWRITE_PROMPT.format(
            **ctx,
            editor_history_block=editor_history_block,
            previous_draft=previous_draft,
        )
        draft_note = (
            f"Reescritura automática por Editor "
            f"(rechazo #{len(editor_feedback_history)})"
        )

    else:
        # Primer borrador del capítulo
        research         = _do_research(chapter, state.get("title", ""), genre)
        previous_context = _build_previous_context(state)

        # Incluir el header solo cuando hay fuentes reales
        if _research_level(genre) == "NONE":
            research_section = ""
        else:
            research_section = f"## INSTRUCCIONES DE INVESTIGACIÓN\n{research}"

        prompt = WRITE_PROMPT.format(
            **ctx,
            previous_context=previous_context,
            research_section=research_section,
            humanize_questions=humanize_questions,
        )
        draft_note = "Primer borrador"

    response = retry_llm_call(
        llm,
        [
            cached_system_message(effective_system),
            HumanMessage(content=prompt),
        ],
        context="Escritor/borrador",
    )
    new_draft = response.content

    # ── 2. Validar extensión ───────────────────────────────────────────────
    word_target = ctx["word_count"]
    word_count, meets_minimum = check_word_count(new_draft, word_target)

    if not meets_minimum:
        logger.warning(
            f"[Escritor] Cap.{chapter_index + 1} — extensión insuficiente: "
            f"{word_count}/{word_target} palabras. El Editor evaluará."
        )
    else:
        logger.info(
            f"[Escritor] Cap.{chapter_index + 1} — {draft_note} | "
            f"{word_count}/{word_target} palabras. Enviando al Editor."
        )

    # ── 3. Revisión opcional por el usuario (solo primer borrador) ────────────
    # Si el usuario eligió revisar capítulos Y es el primer borrador del capítulo
    # (no una reescritura por feedback del editor o maquetador), presentar el capítulo.
    review_chapters = state.get("review_chapters", False)
    is_first_draft  = not editor_feedback and not layouter_feedback

    if review_chapters and is_first_draft:
        logger.info(
            f"[Escritor] Cap.{chapter_index + 1} — presentando al usuario para revisión."
        )
        raw_response = interrupt({
            "type":          "chapter_review",
            "agent":         "Escritor",
            "content":       new_draft,
            "chapter_title": chapter["title"],
            "chapter_num":   chapter_index + 1,
            "word_count":    word_count,
            "actions": {
                "aprobar":    "Aprobar el capítulo y continuar con el siguiente",
                "editar":     "Editar el texto directamente y enviarlo como contenido final",
                "reescribir": "Pedir al Escritor que reescriba con tus instrucciones",
            },
            "hint": (
                "{'action': 'aprobar'} para continuar, "
                "{'action': 'editar', 'content': '<texto>'} para editar directamente, "
                "{'action': 'reescribir', 'feedback': '<instrucciones>'} para reescritura."
            ),
        })

        action, final_draft, feedback_text = _parse_user_response(
            raw_response if isinstance(raw_response, str) else json.dumps(raw_response),
            new_draft,
        )

        if action == "aprobar":
            logger.info(f"[Escritor] Cap.{chapter_index + 1} aprobado por el usuario.")
            new_draft = final_draft

        elif action == "editar":
            logger.info(f"[Escritor] Cap.{chapter_index + 1} editado directamente por el usuario.")
            new_draft = final_draft
            # Ir directo al editor con el texto editado
            return {
                "current_draft":            new_draft,
                "current_chapter_title":    chapter["title"],
                "book_status":              "editing",
                "editor_approved":          False,
                "user_feedback_on_draft":   "",
                "editor_feedback":          "",
                "layouter_feedback":        "",
                "chapter_rewrite_history":  [],
                "editor_feedback_history":  [],
                "current_agent":            AgentName.EDITOR.value,
            }

        elif action == "reescribir":
            logger.info(
                f"[Escritor] Cap.{chapter_index + 1} — reescritura solicitada: "
                f"'{feedback_text[:60]}…'"
            )
            rewrite_history = rewrite_history + [feedback_text]
            return {
                "user_feedback_on_draft":  feedback_text,
                "draft_revision":          draft_revision + 1,
                "chapter_rewrite_history": rewrite_history,
                "current_agent":           AgentName.WRITER.value,
            }

    # ── 4. Envío al Editor ─────────────────────────────────────────────────────
    return {
        "current_draft":            new_draft,
        "current_chapter_title":    chapter["title"],
        "book_status":              "editing",
        "editor_approved":          False,
        "user_feedback_on_draft":   "",
        "editor_feedback":          "",
        "layouter_feedback":        "",   # limpiar después de usar
        "chapter_rewrite_history":  [],
        "editor_feedback_history":  [],
        "current_agent":            AgentName.EDITOR.value,
    }
