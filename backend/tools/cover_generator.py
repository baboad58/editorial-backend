"""
Cover generation tool  v3.0
Primario: Google Gemini Imagen 4 (imagen-4.0-generate-001 / imagen-4.0-fast-generate-001)
Fallback: Ideogram V2

Cambios v3.0:
  - Gemini como generador primario para portadas e imágenes de capítulo.
  - _call_gemini_image(): genera imagen con google-genai SDK, guarda PNG localmente.
  - Ideogram V2 se mantiene como fallback ante fallos de Gemini.
  - generate_style_reference() usa Gemini cuando está disponible.
  - GOOGLE_API_KEY en .env activa Gemini; sin ella usa Ideogram V2.

Cambios v2.0:
  - Logging estándar en vez de print().
  - Timeout diferenciado: 60s para generación, 30s para descarga.
"""

import logging
import os
import re
import time
import unicodedata
from datetime import datetime
from typing import Optional

import requests

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


# ── Constantes de APIs ────────────────────────────────────────────────────────

IDEOGRAM_V2_API_URL = "https://api.ideogram.ai/generate"

# Modelos Gemini para imágenes
GEMINI_IMAGE_MODEL_COVER   = "imagen-4.0-generate-001"      # portadas — mejor calidad
GEMINI_IMAGE_MODEL_CHAPTER = "imagen-4.0-fast-generate-001" # capítulos — más rápido

# Aspect ratios válidos para Gemini Imagen
_GEMINI_ASPECT_RATIOS = {"1:1", "4:3", "3:4", "16:9", "9:16"}

# Rate limiter para Ideogram V2
_last_ideogram_call: float = 0.0
_MIN_REQUEST_INTERVAL = 20.0


def _rate_limit_wait() -> None:
    """Enforce minimum interval between Ideogram API calls."""
    global _last_ideogram_call
    elapsed = time.time() - _last_ideogram_call
    if elapsed < _MIN_REQUEST_INTERVAL and _last_ideogram_call > 0:
        wait = _MIN_REQUEST_INTERVAL - elapsed
        logger.info(f"[Cover] Rate limiter: esperando {wait:.1f}s antes de llamar a Ideogram…")
        time.sleep(wait)
    _last_ideogram_call = time.time()


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


# ── Ideogram V2 ───────────────────────────────────────────────────────────────

def _call_ideogram_v2(
    headers: dict,
    prompt: str,
    aspect_ratio: str,
    style_type: str,
    timeout: int = 60,
) -> requests.Response:
    """Llama al endpoint de generación de Ideogram V2."""
    ratio_map = {
        "1:1": "ASPECT_1_1", "2:3": "ASPECT_2_3", "3:2": "ASPECT_3_2",
        "1:2": "ASPECT_1_2", "2:1": "ASPECT_2_1", "9:16": "ASPECT_9_16",
        "16:9": "ASPECT_16_9", "3:4": "ASPECT_3_4", "4:3": "ASPECT_4_3",
        "1x1": "ASPECT_1_1", "2x3": "ASPECT_2_3", "3x2": "ASPECT_3_2",
    }
    style_map = {
        "GENERAL": "GENERAL", "REALISTIC": "REALISTIC", "DESIGN": "DESIGN",
        "FICTION": "GENERAL", "STYLIZED": "ANIME", "CUSTOM": "GENERAL", "AUTO": "AUTO",
    }
    payload = {
        "image_request": {
            "prompt":       prompt,
            "aspect_ratio": ratio_map.get(aspect_ratio, "ASPECT_1_1"),
            "model":        "V_2",
            "style_type":   style_map.get(style_type, "GENERAL"),
            "magic_prompt_option": "AUTO",
        }
    }
    logger.info(f"[Cover] Usando Ideogram V2 como fallback — aspect={ratio_map.get(aspect_ratio, 'ASPECT_1_1')}")
    return requests.post(
        IDEOGRAM_V2_API_URL,
        headers={**headers, "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )


# ── Helpers de estilo ─────────────────────────────────────────────────────────

_CHILDREN_KEYWORDS = {"infantil", "niños", "niñas", "children", "kids", "cuentos", "cuento"}


def _ascii_title(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("ascii")


def _is_children(genre: str) -> bool:
    return any(k in genre.lower() for k in _CHILDREN_KEYWORDS)


def _cover_style(genre: str) -> str:
    return "DESIGN"


def _chapter_style(genre: str) -> str:
    g = genre.lower()
    if any(k in g for k in ["infantil", "niños", "niñas", "children", "kids", "cuentos", "cuento", "álbum", "album"]):
        return "STYLIZED"
    if any(k in g for k in ["juvenil", "young adult", "ya"]):
        return "REALISTIC"
    if any(k in g for k in ["ficción", "ficcion", "fiction", "fantasía", "fantasia", "fantasy", "thriller", "terror", "horror", "romance", "leyenda", "mítica", "mitica"]):
        return "FICTION"
    return "GENERAL"


def _safe_json(response) -> dict:
    try:
        return response.json()
    except Exception:
        return {"message": response.text[:200]}


# ── Descarga de imágenes ──────────────────────────────────────────────────────

def _download_image(url: str, output_dir: str, title: str) -> Optional[str]:
    """Descarga la imagen de portada desde la URL y la guarda en output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        safe_title = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")[:30]
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename   = f"portada_{safe_title}_{timestamp}.png"
        filepath   = os.path.join(output_dir, filename)
        with open(filepath, "wb") as f:
            f.write(response.content)
        logger.info(f"[Cover] Imagen de portada guardada: {filepath}")
        return filepath
    except requests.exceptions.Timeout:
        logger.warning("[Cover] Timeout al descargar imagen de portada.")
        return None
    except Exception as e:
        logger.warning(f"[Cover] Error descargando imagen: {e}")
        return None


def _download_chapter_image(url: str, output_dir: str, chapter_index: int, image_index: int) -> Optional[str]:
    """Descarga la imagen de capítulo y la guarda en output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        filename = f"img_cap{chapter_index:02d}_{image_index:02d}.png"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "wb") as f:
            f.write(response.content)
        logger.info(f"[Cover] Imagen de capítulo guardada: {filepath}")
        return filepath
    except Exception as e:
        logger.warning(f"[Cover] Error descargando imagen de capítulo: {e}")
        return None


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
        r'\[IDEOGRAM_PROMPT\](.*?)\[/IDEOGRAM_PROMPT\]',
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

    logger.warning("[Cover] Marcadores [IDEOGRAM_PROMPT] no encontrados — usando fallback.")
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


def _build_chapter_prompt(
    concept: str,
    genre: str,
    visual_context: str = "",
    chapter_title: str = "",
    content_excerpt: str = "",
) -> str:
    is_children = _is_children(genre)
    g = genre.lower()

    # Estilo base por género — se puede sobreescribir con "estilo artístico" del visual_context
    if is_children:
        base_style = "children's picture book illustration, gouache watercolor style, vivid saturated colors, friendly characters, bold outlines"
    elif any(k in g for k in ["juvenil", "young adult", "ya"]):
        base_style = "young adult book illustration, semi-realistic digital painting, vibrant colors, expressive characters"
    elif any(k in g for k in ["fantasía", "fantasia", "fantasy"]):
        base_style = "fantasy book illustration, detailed digital art, rich colors, dramatic lighting"
    elif any(k in g for k in ["thriller", "terror", "horror", "ciencia ficción", "ciencia ficcion"]):
        base_style = "thriller book illustration, dark atmospheric, cinematic lighting, moody palette"
    elif any(k in g for k in ["romance"]):
        base_style = "romance book illustration, warm painterly style, soft elegant composition"
    else:
        base_style = "editorial book illustration, professional composition, sophisticated style"

    # Extraer TODOS los campos del visual_context
    ctx = _parse_visual_context(visual_context)
    epoca      = ctx.get("época y lugar", ctx.get("epoca y lugar", ""))
    personajes = ctx.get("personajes visuales clave", "")
    estilo_ctx = ctx.get("estilo artístico", ctx.get("estilo artistico", ""))
    paleta     = ctx.get("paleta y atmósfera", ctx.get("paleta y atmosfera", ""))
    prohib     = ctx.get("prohibiciones", "")

    # El estilo artístico del visual_context tiene prioridad si existe
    style = estilo_ctx if estilo_ctx else base_style

    # Construir el prompt en secciones con prioridad clara:
    # 1. Escena concreta (concept) — lo que ocurre en ESTA imagen
    # 2. Personajes con descripción física completa — para consistencia
    # 3. Época y lugar — para consistencia de setting
    # 4. Paleta/atmósfera — para consistencia visual
    # 5. Estilo artístico — para coherencia de técnica
    # 6. Prohibiciones — para evitar inconsistencias
    parts = []

    # Escena principal (descripción [IMAGEN:] generada por el Layouter)
    core_scene = _extract_core_scene(concept)
    if core_scene:
        parts.append(core_scene)

    # Personajes — campo más crítico para consistencia
    if personajes:
        parts.append(f"Characters (use exact physical descriptions): {personajes}")

    # Época y lugar
    if epoca:
        parts.append(f"Setting: {epoca}")

    # Paleta y atmósfera
    if paleta:
        parts.append(f"Visual atmosphere: {paleta}")

    # Estilo artístico
    if style:
        parts.append(style)

    # Prohibiciones — al final para no contaminar el inicio del prompt
    if prohib:
        parts.append(f"Do NOT include: {prohib}")

    parts.append("Professional book illustration quality, consistent character appearance.")

    prompt = ". ".join(p.strip(" .") for p in parts if p.strip())
    prompt = re.sub(r"\s+", " ", prompt).strip()

    # Límite generoso — Ideogram maneja hasta ~300 palabras bien
    words = prompt.split()
    if len(words) > 200:
        prompt = " ".join(words[:200]).rstrip(" ,.;:-")

    logger.debug(f"[Cover] Prompt capítulo: {len(prompt.split())} palabras, {len(prompt)} chars")
    return prompt


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

def generate_cover_with_ideogram(
    title: str,
    subtitle: str,
    author_name: str,
    cover_description: str,
    output_dir: str = "output",
    genre: str = "",
    reference_image_path: str = "",
) -> tuple[Optional[str], Optional[str]]:
    """
    Genera la portada del libro.
    Primario: Gemini Imagen 4 (imagen-4.0-generate-001)
    Fallback:  Ideogram V2
    """
    os.makedirs(output_dir, exist_ok=True)
    prompts_to_try = [
        _build_cover_prompt(title, subtitle, author_name, cover_description, genre),
        _build_safe_cover_prompt(title, subtitle, author_name, genre),
    ]

    # ── Primario: Gemini ─────────────────────────────────────────────────────
    google_api_key = os.getenv("GOOGLE_API_KEY", "")
    if google_api_key:
        for attempt, prompt in enumerate(prompts_to_try, start=1):
            safe_title = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")[:30]
            timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename   = f"portada_{safe_title}_{timestamp}.png"
            filepath   = os.path.join(output_dir, filename)
            logger.info(f"[Cover] Gemini portada — intento {attempt}")
            ok = _call_gemini_image(prompt, filepath, aspect_ratio="3:4", model=GEMINI_IMAGE_MODEL_COVER)
            if ok:
                return filepath, None
            if attempt < len(prompts_to_try):
                logger.info("[Cover] Gemini portada falló — reintentando con prompt simplificado…")
        logger.warning("[Cover] Gemini portada falló — usando Ideogram V2 como fallback")

    # ── Fallback: Ideogram V2 ────────────────────────────────────────────────
    ideogram_key = os.getenv("IDEOGRAM_API_KEY", "")
    if not ideogram_key or ideogram_key.startswith("tvly-placeholder"):
        logger.info("[Cover] Sin API keys configuradas. Omitiendo generación de portada.")
        return None, None

    headers = {"Api-Key": ideogram_key}
    for attempt, prompt in enumerate(prompts_to_try, start=1):
        try:
            _rate_limit_wait()
            resp = _call_ideogram_v2(headers, prompt, aspect_ratio="2x3", style_type=_cover_style(genre))
            if resp.status_code >= 400:
                body = _safe_json(resp)
                logger.warning(f"[Cover] Ideogram V2 portada {resp.status_code} (intento {attempt}): {body}")
                if attempt < len(prompts_to_try):
                    logger.info("[Cover] Reintentando portada con prompt simplificado…")
                    continue
                return None, f"⚠️ Ideogram V2 rechazó portada ({resp.status_code})"
            images = resp.json().get("data", [])
            if not images:
                return None, "⚠️ Ideogram V2 no devolvió imágenes."
            image_url = images[0].get("url", "")
            downloaded = _download_image(image_url, output_dir, title)
            return downloaded, None if downloaded else "⚠️ No se pudo descargar la portada."
        except Exception as e:
            logger.warning(f"[Cover] Ideogram V2 portada error: {e}")
            return None, f"⚠️ Error en fallback Ideogram V2: {e}"

    return None, "⚠️ Todos los intentos de generación de portada fallaron."


def generate_style_reference(
    title: str,
    genre: str,
    cover_description: str,
    output_dir: str = "output",
) -> Optional[str]:
    """
    Genera una imagen de referencia de estilo.
    Primario: Gemini. Fallback: Ideogram V2.
    """
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
    prompt = prompt[:800]

    ref_dir = os.path.join(output_dir, "references")
    os.makedirs(ref_dir, exist_ok=True)
    filepath = os.path.join(ref_dir, "style_reference.png")

    # ── Primario: Gemini ─────────────────────────────────────────────────────
    google_api_key = os.getenv("GOOGLE_API_KEY", "")
    if google_api_key:
        ok = _call_gemini_image(prompt, filepath, aspect_ratio="1:1", model=GEMINI_IMAGE_MODEL_CHAPTER)
        if ok:
            return filepath
        logger.warning("[Cover] Gemini referencia de estilo falló — usando Ideogram V2")

    # ── Fallback: Ideogram V2 ────────────────────────────────────────────────
    ideogram_key = os.getenv("IDEOGRAM_API_KEY", "")
    if not ideogram_key or ideogram_key.startswith("tvly-placeholder"):
        return None

    try:
        _rate_limit_wait()
        headers = {"Api-Key": ideogram_key}
        resp = _call_ideogram_v2(headers, prompt, aspect_ratio="1x1", style_type=_chapter_style(genre))
        if not resp.ok:
            logger.warning(f"[Cover] Ideogram V2 referencia de estilo falló: {resp.status_code}")
            return None
        images = resp.json().get("data", [])
        if not images:
            return None
        image_url = images[0].get("url", "")
        if not image_url:
            return None
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(img_response.content)
        logger.info(f"[Cover] Referencia de estilo (Ideogram V2) guardada: {filepath}")
        return filepath
    except Exception as e:
        logger.warning(f"[Cover] Error generando referencia de estilo: {e}")
        return None


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
    ideogram_key   = os.getenv("IDEOGRAM_API_KEY", "")

    if not google_api_key and (not ideogram_key or ideogram_key.startswith("tvly-placeholder")):
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

    # ── Primario: Gemini ─────────────────────────────────────────────────────
    if google_api_key:
        for attempt, prompt in enumerate(prompts_to_try, start=1):
            filepath = os.path.join(output_dir, f"img_cap{chapter_index:02d}_{image_index:02d}.png")
            logger.info(f"[Cover] Gemini cap{chapter_index}.{image_index} — intento {attempt}")
            ok = _call_gemini_image(prompt, filepath, aspect_ratio="1:1", model=GEMINI_IMAGE_MODEL_CHAPTER)
            if ok:
                return filepath, None
            if attempt < len(prompts_to_try):
                logger.info("[Cover] Gemini capítulo falló — reintentando con prompt simplificado…")
        logger.warning(f"[Cover] Gemini cap{chapter_index}.{image_index} falló — usando Ideogram V2")

    # ── Fallback: Ideogram V2 ────────────────────────────────────────────────
    if not ideogram_key or ideogram_key.startswith("tvly-placeholder"):
        return None, "⚠️ Gemini falló y no hay API key de Ideogram configurada."

    headers = {"Api-Key": ideogram_key}
    for attempt, prompt in enumerate(prompts_to_try, start=1):
        try:
            _rate_limit_wait()
            resp = _call_ideogram_v2(headers, prompt, aspect_ratio="1x1", style_type=_chapter_style(genre))
            if resp.status_code >= 400:
                body = _safe_json(resp)
                logger.warning(
                    f"[Cover] Ideogram V2 cap{chapter_index}.{image_index} {resp.status_code} "
                    f"(intento {attempt}): {body}"
                )
                if attempt < len(prompts_to_try):
                    logger.info("[Cover] Reintentando capítulo con prompt simplificado…")
                    continue
                return None, f"⚠️ Ideogram V2 rechazó imagen de capítulo ({resp.status_code})"
            images = resp.json().get("data", [])
            if not images:
                return None, "⚠️ Ideogram V2 no devolvió imagen para capítulo."
            image_url = images[0].get("url", "")
            if not image_url:
                return None, "⚠️ Ideogram V2 no incluyó URL de imagen."
            downloaded = _download_chapter_image(image_url, output_dir, chapter_index, image_index)
            return downloaded, None if downloaded else "⚠️ No se pudo descargar imagen de capítulo."
        except Exception as e:
            logger.warning(f"[Cover] Ideogram V2 cap{chapter_index}.{image_index} error: {e}")
            return None, f"⚠️ Error en fallback Ideogram V2: {e}"

    return None, "⚠️ Todos los intentos de imagen de capítulo fallaron."
