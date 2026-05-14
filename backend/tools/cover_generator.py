"""
Cover generation tool  v4.0
Generador: Google Gemini Imagen 4 (imagen-4.0-generate-001 / imagen-4.0-fast-generate-001)

Cambios v4.0:
  - Eliminado Ideogram V2 completamente — Gemini es el único generador.
  - Requiere GOOGLE_API_KEY en .env.
  - Sin GOOGLE_API_KEY, las imágenes se omiten graciosamente.
"""

import logging
import os
import re
import unicodedata
from datetime import datetime
from typing import Optional

logger = logging.getLogger("editorial_system")

# ── Normalización de prompts ──────────────────────────────────────────────────

_STOP_PHRASES = [
    r"^chapter:\s*", r"^scene:\s*", r"^prompt:\s*", r"^image:\s*",
    r"^escena:\s*",  r"^descripción:\s*", r"^descripcion:\s*",
]
_NOISE_PATTERNS = [
    r"\bcap\d+(\.\d+)?\b", r"\bintento\s*\d+/\d+\b", r"\bmodo=\w+\b",
    r"\bstyle[_ -]?type\b", r"\bmagic[_ -]?prompt\b",
]


def _clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", text.replace("\n", " ").replace("\t", " ")).strip()


def _remove_noise(text: str) -> str:
    for p in _STOP_PHRASES:
        text = re.sub(p, "", text, flags=re.IGNORECASE)
    for p in _NOISE_PATTERNS:
        text = re.sub(p, "", text, flags=re.IGNORECASE)
    text = text.replace("\u201c", "").replace("\u201d", "").replace("\u2018", "").replace("\u2019", "")
    return re.sub(r"\s+", " ", text).strip(" ,.;:-")


def _extract_core_scene(text: str) -> str:
    text = _clean_text(text)
    text = _remove_noise(text)
    parts = re.split(r"(?i)\b(?:scene|escena|description|descripci[oó]n)\s*:\s*", text, maxsplit=1)
    if len(parts) == 2:
        text = parts[1].strip()
    return re.sub(r'^[\'"]|[\'"]$', "", text).strip()


def compact_ideogram_prompt(
    scene: str = "",
    style: str = "",
    extras: list | None = None,
    max_words: int = 120,
) -> str:
    """Builds a clean prompt: instructions in English, scene content as-is. Max ~120 words."""
    scene = _extract_core_scene(scene)
    bits = []
    if scene:
        bits.append(scene)
    if style:
        bits.append(style)
    if extras:
        cleaned = [_extract_core_scene(x) for x in extras if x]
        cleaned = [x for x in cleaned if x]
        if cleaned:
            bits.append(", ".join(cleaned))

    prompt = ". ".join(bits)
    prompt = re.sub(r"\s+", " ", prompt).strip(" .")
    words = prompt.split()
    if len(words) > max_words:
        prompt = " ".join(words[:max_words]).rstrip(" ,.;:-")
    return prompt


# ── Modelos Gemini ────────────────────────────────────────────────────────────

GEMINI_IMAGE_MODEL_COVER   = "imagen-4.0-generate-001"      # portadas — mejor calidad
GEMINI_IMAGE_MODEL_CHAPTER = "imagen-4.0-fast-generate-001" # capítulos — más rápido

# Aspect ratios válidos para Gemini Imagen
_GEMINI_ASPECT_RATIOS = {"1:1", "4:3", "3:4", "16:9", "9:16"}


# ── Gemini ────────────────────────────────────────────────────────────────────

def _call_gemini_image(
    prompt: str,
    output_path: str,
    aspect_ratio: str = "1:1",
    model: str = GEMINI_IMAGE_MODEL_CHAPTER,
) -> bool:
    """
    Genera una imagen con Gemini Imagen y la guarda en output_path.
    Retorna True si tuvo éxito, False si falló.
    """
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        return False

    ratio = aspect_ratio if aspect_ratio in _GEMINI_ASPECT_RATIOS else "1:1"

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        response = client.models.generate_images(
            model=model,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=ratio,
                output_mime_type="image/png",
            ),
        )
        if not response.generated_images:
            logger.warning("[Cover] Gemini no devolvió imágenes.")
            return False

        image_bytes = response.generated_images[0].image.image_bytes
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(image_bytes)
        logger.info(f"[Cover] Gemini: imagen guardada en {output_path}")
        return True

    except Exception as e:
        logger.warning(f"[Cover] Gemini falló: {e}")
        return False


# ── Helpers de estilo ─────────────────────────────────────────────────────────

_CHILDREN_KEYWORDS = {"infantil", "niños", "niñas", "children", "kids", "cuentos", "cuento"}


def _ascii_title(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("ascii")


def _is_children(genre: str) -> bool:
    return any(k in genre.lower() for k in _CHILDREN_KEYWORDS)






# ── Prompts ───────────────────────────────────────────────────────────────────

def _build_safe_cover_prompt(title: str, subtitle: str, author_name: str, genre: str) -> str:
    if _is_children(genre):
        style = "Colorful, cheerful children's book cover illustration, friendly characters, bright colors, safe for all ages."
    else:
        style = "Professional book cover design, clean and elegant, suitable for all audiences."
    t = _ascii_title(title)
    s = _ascii_title(subtitle) if subtitle else ""
    prompt = f'Book cover illustration. Title "{t}" in upper area, not touching top edge, fully visible.'
    if s:
        prompt += f' Subtitle "{s}" on a separate line below the title.'
    prompt += f' {style}'
    return prompt[:800]


def _build_cover_prompt(
    title: str,
    subtitle: str,
    author_name: str,
    cover_description: str,
    genre: str = "",
) -> str:
    import re as _re
    match = _re.search(
        r'\[IMAGE_PROMPT\](.*?)\[/IMAGE_PROMPT\]',
        cover_description,
        _re.DOTALL | _re.IGNORECASE,
    )
    t = _ascii_title(title)
    s = _ascii_title(subtitle) if subtitle else ""
    a = _ascii_title(author_name)

    if match:
        ideogram_prompt = match.group(1).strip()
        ideogram_prompt = _re.sub(r'^\(.*?\)\s*', '', ideogram_prompt, flags=_re.DOTALL)
        logger.info(f"[Cover] Prompt extraído del marcador ({len(ideogram_prompt)} chars)")
        prompt = f'Book cover illustration. Large bold title text "{t}" in the upper area, not touching the top edge, fully visible. '
        if s:
            prompt += f'Subtitle text "{s}" on a separate line directly below the title. '
        prompt += ideogram_prompt
        return prompt[:1000]

    logger.warning("[Cover] Marcadores [IMAGE_PROMPT] no encontrados — usando fallback.")
    concept_end = len(cover_description)
    for marker in ("PALETA", "TIPOGRAF", "COMPOSICI", "PROMPT PARA", "##", "---"):
        idx = cover_description.upper().find(marker)
        if idx != -1 and idx < concept_end:
            concept_end = idx
    visual_concept = cover_description[:concept_end].strip()[:200]
    prompt = f'Book cover illustration. Title "{t}" at top. {visual_concept}. Professional publishing quality, portrait format.'
    return prompt[:600]


def _parse_visual_context(visual_context: str) -> dict:
    """Parsea el visual_context en un dict con todos sus campos."""
    ctx = {}
    if not visual_context:
        return ctx
    for line in visual_context.strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            ctx[key.strip().lower()] = val.strip()
    return ctx


# ── Detección de modelo de imagen ─────────────────────────────────────────────

def _detect_image_model(genre: str) -> str:
    """
    Detecta el modelo de imagen apropiado para el género:
      'narrative'    — ficción / infantil / YA: escenas con personajes consistentes
      'conceptual'   — no-ficción práctica: ilustración metafórica/conceptual
      'infographic'  — académico / científico: infografía estilo diagrama

    NOTA: 'no-ficción' se evalúa ANTES que 'ficción' para evitar falso positivo
    por substring (la palabra "ficción" está contenida en "no-ficción").
    """
    g = genre.lower()
    # 1. No-ficción práctica (más específico — evaluar ANTES que ficción)
    if any(k in g for k in ["no-ficción", "no-ficcion", "no ficción", "no ficcion",
                              "autoayuda", "auto-ayuda", "negocios", "emprendimiento",
                              "salud", "bienestar", "finanzas", "liderazgo", "coaching",
                              "desarrollo personal", "motivacion", "motivación"]):
        return "conceptual"
    # 2. Ficción / narrativa (después de no-ficción)
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
    # 4. Default: conceptual (no-ficción genérica)
    return "conceptual"


def _finalize_prompt(parts: list[str], limit: int = 200) -> str:
    """Une las partes, limpia espacios y aplica límite de palabras."""
    prompt = ". ".join(p.strip(" .") for p in parts if p.strip())
    prompt = re.sub(r"\s+", " ", prompt).strip()
    words = prompt.split()
    if len(words) > limit:
        prompt = " ".join(words[:limit]).rstrip(" ,.;:-")
    return prompt


def _build_narrative_prompt(
    concept: str,
    genre: str,
    visual_context: str,
    chapter_title: str,
    content_excerpt: str,
) -> str:
    """Ficción / infantil / YA: ilustración narrativa con personajes consistentes."""
    g = genre.lower()
    is_children = _is_children(genre)

    if is_children:
        base_style = ("children's picture book illustration, gouache watercolor style, "
                      "vivid saturated colors, friendly expressive characters, bold outlines, "
                      "NOT photorealistic, NOT photograph, NOT 3D render")
    elif any(k in g for k in ["juvenil", "young adult", "ya"]):
        base_style = ("young adult graphic novel illustration, semi-realistic digital painting, "
                      "vibrant colors, expressive characters, NOT photorealistic, NOT photograph")
    elif any(k in g for k in ["fantasía", "fantasia", "fantasy"]):
        base_style = ("fantasy book illustration, detailed digital painting, rich colors, "
                      "dramatic lighting, NOT photograph, NOT 3D render")
    elif any(k in g for k in ["thriller", "terror", "horror", "ciencia ficción", "ciencia ficcion"]):
        base_style = ("thriller book illustration, dark atmospheric digital painting, "
                      "cinematic lighting, moody palette, NOT photograph, NOT photorealistic")
    elif any(k in g for k in ["romance"]):
        base_style = ("romance book illustration, warm painterly style, soft elegant composition, "
                      "NOT photograph, NOT photorealistic")
    else:
        base_style = ("editorial book illustration, professional painterly composition, "
                      "NOT photograph, NOT photorealistic, NOT 3D render")

    ctx        = _parse_visual_context(visual_context)
    personajes = ctx.get("personajes visuales clave", "")
    estilo_ctx = ctx.get("estilo artístico", ctx.get("estilo artistico", ""))
    paleta     = ctx.get("paleta y atmósfera", ctx.get("paleta y atmosfera", ""))
    epoca      = ctx.get("época y lugar", ctx.get("epoca y lugar", ""))
    prohib     = ctx.get("prohibiciones", "")

    # Si el visual_context tiene estilo, usarlo — asegurar negativos
    style = estilo_ctx if estilo_ctx else base_style
    if "not photo" not in style.lower() and "not photograph" not in style.lower():
        style += ", NOT photorealistic, NOT photograph"

    parts = []
    # POSICIÓN 1: Ancla de estilo — prioridad máxima para Gemini
    parts.append(f"FIXED ILLUSTRATION STYLE (never deviate from this): {style}")
    # Escena del capítulo
    core = _extract_core_scene(concept)
    if core:
        parts.append(core)
    # Personajes con descripción física exacta
    if personajes:
        parts.append(f"Characters (exact physical descriptions, maintain across all images): {personajes}")
    # Época y setting
    if epoca:
        parts.append(f"Setting: {epoca}")
    # Paleta/atmósfera
    if paleta:
        parts.append(f"Visual atmosphere: {paleta}")
    # Prohibiciones
    if prohib:
        parts.append(f"Do NOT include: {prohib}")
    parts.append("Professional book illustration quality. Consistent character appearance across all chapters.")

    prompt = _finalize_prompt(parts)
    logger.debug(f"[Cover] Prompt narrativo: {len(prompt.split())} palabras")
    return prompt


def _build_conceptual_prompt(
    concept: str,
    genre: str,
    visual_context: str,
    chapter_title: str,
    content_excerpt: str,
) -> str:
    """No-ficción práctica: ilustración metafórica/conceptual, sin personajes narrativos."""
    ctx    = _parse_visual_context(visual_context)
    paleta = ctx.get("paleta de marca", ctx.get("paleta y atmósfera", ctx.get("paleta y atmosfera", "")))
    estilo = ctx.get("estilo iconográfico", ctx.get("estilo artístico", ctx.get("estilo artistico", "")))
    prohib = ctx.get("prohibiciones", "")

    base_style = ("conceptual editorial illustration, flat design with depth, "
                  "clean modern professional style, NOT photorealistic, "
                  "NOT photograph, NOT fictional narrative characters")
    style = estilo if estilo else base_style

    parts = []
    parts.append(f"FIXED STYLE (never deviate): {style}")
    core = _extract_core_scene(concept)
    if core:
        parts.append(core)
    elif chapter_title:
        parts.append(f"Conceptual visual metaphor for: {chapter_title}")
    if paleta:
        parts.append(f"Color palette (apply consistently): {paleta}")
    combined_prohib = "fictional narrative characters with names, specific real people, photorealistic scenes"
    if prohib:
        combined_prohib += f", {prohib}"
    parts.append(f"Do NOT include: {combined_prohib}")
    parts.append("Professional non-fiction book interior illustration. Symbolic and universal imagery.")

    prompt = _finalize_prompt(parts)
    logger.debug(f"[Cover] Prompt conceptual: {len(prompt.split())} palabras")
    return prompt


def _build_infographic_prompt(
    concept: str,
    genre: str,
    visual_context: str,
    chapter_title: str,
    content_excerpt: str,
) -> str:
    """Académico / científico: infografía estilo diagrama, sin escenas narrativas."""
    ctx       = _parse_visual_context(visual_context)
    paleta    = ctx.get("paleta editorial", ctx.get("paleta de marca", "deep blue, slate grey, white, teal accent"))
    estilo    = ctx.get("estilo visual", ctx.get("estilo artístico", ctx.get("estilo artistico", "")))
    elementos = ctx.get("elementos permitidos", "arrows, geometric shapes, flow diagrams, data nodes, labels")
    prohib    = ctx.get("prohibiciones", "")

    base_style = ("clean scientific infographic illustration, Nature and Scientific American magazine style, "
                  "flat design with subtle depth, crisp typography-ready layout, "
                  "NOT photorealistic, NOT narrative scene, NOT fictional characters, NOT photograph")
    style = estilo if estilo else base_style

    core = _extract_core_scene(concept)
    subject = core if core else chapter_title

    parts = []
    parts.append(f"FIXED STYLE (never deviate): {style}")
    if subject:
        parts.append(f"Infographic visualizing: {subject}")
    parts.append(f"Visual elements to use: {elementos}")
    if paleta:
        parts.append(f"Color palette (apply consistently): {paleta}")
    combined_prohib = "people's faces, realistic photographs, narrative scenes, fictional characters, more than 4 simultaneous colors"
    if prohib:
        combined_prohib += f", {prohib}"
    parts.append(f"Do NOT include: {combined_prohib}")
    parts.append("Professional academic publication quality. Clean, readable, suitable for scientific book interior.")

    prompt = _finalize_prompt(parts)
    logger.debug(f"[Cover] Prompt infográfico: {len(prompt.split())} palabras")
    return prompt


def _build_chapter_prompt(
    concept: str,
    genre: str,
    visual_context: str = "",
    chapter_title: str = "",
    content_excerpt: str = "",
) -> str:
    """Delega al builder correcto según el modelo de imagen del género."""
    model = _detect_image_model(genre)
    if model == "narrative":
        return _build_narrative_prompt(concept, genre, visual_context, chapter_title, content_excerpt)
    elif model == "infographic":
        return _build_infographic_prompt(concept, genre, visual_context, chapter_title, content_excerpt)
    else:
        return _build_conceptual_prompt(concept, genre, visual_context, chapter_title, content_excerpt)


def _build_safe_chapter_prompt(genre: str) -> str:
    if _is_children(genre):
        return (
            "Children's picture book illustration, gouache painting style. "
            "VIVID saturated colors: bright red, sunny yellow, deep blue, lush green. "
            "Friendly cartoon animals or children with large expressive eyes, bold outlines. "
            "Simple cheerful background. Safe for all ages, no scary elements, no dark tones."
        )
    if "juvenil" in genre.lower() or "young adult" in genre.lower():
        return (
            "Young adult book illustration. Cinematic realistic painting, "
            "expressive characters, vibrant colors, dynamic scene. Safe for all ages."
        )
    return (
        "Book interior illustration. Abstract decorative design, professional editorial style, "
        "neutral and suitable for all audiences."
    )


# ── Funciones públicas ────────────────────────────────────────────────────────

def generate_cover(
    title: str,
    subtitle: str,
    author_name: str,
    cover_description: str,
    output_dir: str = "output",
    genre: str = "",
    reference_image_path: str = "",
) -> tuple[Optional[str], Optional[str]]:
    """Genera la portada del libro con Gemini Imagen 4."""
    google_api_key = os.getenv("GOOGLE_API_KEY", "")
    if not google_api_key:
        logger.info("[Cover] GOOGLE_API_KEY no configurada. Omitiendo portada.")
        return None, None

    os.makedirs(output_dir, exist_ok=True)
    prompts_to_try = [
        _build_cover_prompt(title, subtitle, author_name, cover_description, genre),
        _build_safe_cover_prompt(title, subtitle, author_name, genre),
    ]

    for attempt, prompt in enumerate(prompts_to_try, start=1):
        safe_title = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")[:30]
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename   = f"portada_{safe_title}_{timestamp}.png"
        filepath   = os.path.join(output_dir, filename)
        logger.info(f"[Cover] Gemini portada — intento {attempt}")
        if _call_gemini_image(prompt, filepath, aspect_ratio="3:4", model=GEMINI_IMAGE_MODEL_COVER):
            return filepath, None
        if attempt < len(prompts_to_try):
            logger.info("[Cover] Gemini portada falló — reintentando con prompt simplificado…")

    logger.warning("[Cover] Gemini portada falló en todos los intentos.")
    return None, "⚠️ Gemini no pudo generar la portada."


# Alias de compatibilidad para código que aún use el nombre anterior
generate_cover_with_ideogram = generate_cover


def generate_style_reference(
    title: str,
    genre: str,
    cover_description: str,
    output_dir: str = "output",
) -> Optional[str]:
    """Genera una imagen de referencia de estilo con Gemini."""
    google_api_key = os.getenv("GOOGLE_API_KEY", "")
    if not google_api_key:
        return None

    concept = cover_description.strip()[:400] if cover_description else ""
    if _is_children(genre):
        style_hint = "Colorful children's book illustration style, friendly cartoon, bright pastel colors."
    elif "thriller" in genre.lower() or "terror" in genre.lower() or "horror" in genre.lower():
        style_hint = "Dark atmospheric illustration, dramatic lighting, moody cinematic style."
    elif "romance" in genre.lower():
        style_hint = "Soft romantic illustration, warm colors, elegant painterly style."
    elif "fantasia" in genre.lower() or "fantasía" in genre.lower() or "fantasy" in genre.lower():
        style_hint = "Epic fantasy illustration, vivid magical colors, detailed digital art style."
    else:
        style_hint = "Professional editorial illustration, clean composition, sophisticated style."

    prompt = f"Visual style reference for book '{title}'. {style_hint} {concept[:200]}. No text, no titles, pure visual atmosphere."

    ref_dir = os.path.join(output_dir, "references")
    os.makedirs(ref_dir, exist_ok=True)
    filepath = os.path.join(ref_dir, "style_reference.png")

    ok = _call_gemini_image(prompt[:800], filepath, aspect_ratio="1:1", model=GEMINI_IMAGE_MODEL_CHAPTER)
    return filepath if ok else None


def generate_chapter_image(
    description: str,
    output_dir: str,
    chapter_index: int,
    image_index: int,
    book_title: str = "",
    genre: str = "",
    reference_image_path: str = "",
    visual_context: str = "",
    chapter_title: str = "",
    chapter_content: str = "",
) -> tuple[Optional[str], Optional[str]]:
    """
    Genera una imagen ilustrativa para un capítulo del libro.
    Primario: Gemini Imagen 4 Fast (imagen-4.0-fast-generate-001)
    Fallback:  Ideogram V2
    """
    google_api_key = os.getenv("GOOGLE_API_KEY", "")
    if not google_api_key:
        return None, None

    concept = description.strip()
    if len(concept) > 600:
        concept = concept[:600].rsplit(" ", 1)[0] + "…"

    content_excerpt = ""
    if chapter_content:
        words = chapter_content.split()
        content_excerpt = " ".join(words[:300])
        if len(words) > 300:
            content_excerpt += "…"

    prompts_to_try = [
        _build_chapter_prompt(
            concept, genre,
            visual_context=visual_context,
            chapter_title=chapter_title,
            content_excerpt=content_excerpt,
        ),
        _build_safe_chapter_prompt(genre),
    ]

    os.makedirs(output_dir, exist_ok=True)

    for attempt, prompt in enumerate(prompts_to_try, start=1):
        filepath = os.path.join(output_dir, f"img_cap{chapter_index:02d}_{image_index:02d}.png")
        logger.info(f"[Cover] Gemini cap{chapter_index}.{image_index} — intento {attempt}")
        if _call_gemini_image(prompt, filepath, aspect_ratio="1:1", model=GEMINI_IMAGE_MODEL_CHAPTER):
            return filepath, None
        if attempt < len(prompts_to_try):
            logger.info("[Cover] Gemini capítulo falló — reintentando con prompt simplificado…")

    logger.warning(f"[Cover] Gemini cap{chapter_index}.{image_index} falló en todos los intentos.")
    return None, "⚠️ Gemini no pudo generar la imagen del capítulo."
