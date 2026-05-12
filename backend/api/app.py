"""
FastAPI application factory.
Mounts the WebSocket endpoint and REST endpoints for health/session info.
"""

import asyncio
import os
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, UploadFile, File, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.api.websocket import book_websocket_handler
from backend.api.session import session_manager

# ── Códigos de invitación válidos (backend-side, nunca en el bundle JS) ─────
_INVITE_CODES: set[str] = set(
    filter(None, os.getenv(
        "INVITE_CODES",
        "OBRA-ALPHA-001,OBRA-ALPHA-002,OBRA-ALPHA-003,OBRA-ALPHA-004,OBRA-ALPHA-005,"
        "OBRA-ALPHA-006,OBRA-ALPHA-007,OBRA-ALPHA-008,OBRA-ALPHA-009,OBRA-ALPHA-010",
    ).upper().split(","))
)

# ── Rate limiter in-memory para /api/verify-invite ───────────────────────────
_invite_attempts: dict[str, list[float]] = defaultdict(list)
_WS_connections:  dict[str, list[float]] = defaultdict(list)
_MAX_INVITE_ATTEMPTS = 5          # intentos por IP por ventana
_INVITE_WINDOW     = 3600.0       # 1 hora
_MAX_WS_PER_MIN    = 10           # conexiones WS por IP por minuto

def _rate_limit_invite(ip: str) -> bool:
    """Devuelve True si la IP puede intentar; False si superó el límite."""
    now = time.time()
    _invite_attempts[ip] = [t for t in _invite_attempts[ip] if now - t < _INVITE_WINDOW]
    if len(_invite_attempts[ip]) >= _MAX_INVITE_ATTEMPTS:
        return False
    _invite_attempts[ip].append(now)
    return True

def _rate_limit_ws(ip: str) -> bool:
    """Devuelve True si la IP puede abrir nueva conexión WS; False si superó el límite."""
    now = time.time()
    _WS_connections[ip] = [t for t in _WS_connections[ip] if now - t < 60.0]
    if len(_WS_connections[ip]) >= _MAX_WS_PER_MIN:
        return False
    _WS_connections[ip].append(now)
    return True


_OUTPUT_RETENTION_DAYS = int(os.getenv("OUTPUT_RETENTION_DAYS", "30"))

async def _session_cleanup_loop() -> None:
    """Background task: purge sessions idle longer than SESSION_TIMEOUT_SECONDS
    y elimina checkpoints/outputs con más de OUTPUT_RETENTION_DAYS días."""
    while True:
        await asyncio.sleep(60)
        await session_manager.cleanup_expired_sessions()
        _cleanup_old_outputs()


def _cleanup_old_outputs() -> None:
    """Elimina carpetas de sesiones en output/ con más de OUTPUT_RETENTION_DAYS días."""
    import logging, shutil
    logger = logging.getLogger("book-factory.retention")
    output_root = Path(os.getenv("OUTPUT_DIR", "output"))
    if not output_root.exists():
        return
    cutoff = time.time() - _OUTPUT_RETENTION_DAYS * 86400
    for session_dir in output_root.iterdir():
        if not session_dir.is_dir() or session_dir.name in ("references",):
            continue
        try:
            if session_dir.stat().st_mtime < cutoff:
                shutil.rmtree(session_dir, ignore_errors=True)
                logger.info(f"[Retention] Sesión eliminada por antigüedad: {session_dir.name}")
        except Exception:
            pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="Book Factory API",
        description="Sistema de generacion de libros con IA -- LangGraph + Claude",
        version="1.0.0",
    )

    # -- CORS ------------------------------------------------------------------
    # Allow the React dev server (Vite default: 5173) and same origin
    allowed_origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:3000,http://localhost:8000",
    ).split(",")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Headers de seguridad HTTP ---------------------------------------------
    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # -- Background session cleanup --------------------------------------------
    @app.on_event("startup")
    async def start_cleanup():
        asyncio.create_task(_session_cleanup_loop(), name="session-cleanup")
        # En Windows, el ProactorEventLoop lanza WinError 10013 al hacer shutdown()
        # de sockets ya cerrados. Interceptar aqui para que no propague ni mate
        # otras conexiones activas.
        def _ws_exception_handler(loop, context):
            exc = context.get("exception")
            if isinstance(exc, PermissionError) and getattr(exc, "winerror", None) == 10013:
                return  # ruido cosmetico de Windows -- ignorar silenciosamente
            loop.default_exception_handler(context)
        asyncio.get_event_loop().set_exception_handler(_ws_exception_handler)

    @app.on_event("shutdown")
    async def shutdown_executor():
        from backend.api.graph_runner import _executor
        _executor.shutdown(wait=False, cancel_futures=True)

    # -- WebSocket endpoint ----------------------------------------------------
    @app.websocket("/ws/book")
    async def book_ws(websocket: WebSocket):
        ip = websocket.client.host if websocket.client else "unknown"
        if not _rate_limit_ws(ip):
            await websocket.close(code=1008, reason="Demasiadas conexiones. Intenta en un minuto.")
            return
        await book_websocket_handler(websocket)

    # -- Verificación de código de invitación (backend-side) ------------------
    @app.post("/api/verify-invite")
    async def verify_invite(request: Request):
        ip = request.client.host if request.client else "unknown"
        if not _rate_limit_invite(ip):
            raise HTTPException(
                status_code=429,
                detail="Demasiados intentos. Espera una hora antes de volver a intentarlo.",
            )
        try:
            body = await request.json()
            code = str(body.get("code", "")).strip().upper()
        except Exception:
            raise HTTPException(status_code=400, detail="Petición mal formada.")
        if not code:
            raise HTTPException(status_code=400, detail="Código requerido.")
        if code in _INVITE_CODES:
            return {"valid": True}
        raise HTTPException(status_code=401, detail="Código no válido.")

    # -- REST endpoints --------------------------------------------------------
    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "book-factory"}

    @app.get("/api/output/{filepath:path}")
    async def download_output(filepath: str, token: str = Query(default="")):
        """Download a generated book file. Requires ?token= matching the session token."""
        output_root = Path(os.getenv("OUTPUT_DIR", "output")).resolve()
        full_path = (output_root / filepath).resolve()
        # Prevenir path traversal
        if not str(full_path).startswith(str(output_root)):
            raise HTTPException(status_code=400, detail="Ruta invalida")
        if not full_path.exists() or not full_path.is_file():
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
        # Validar token: el primer componente del path es el prefijo del session_id (8 chars)
        path_parts = filepath.split("/")
        if path_parts:
            output_dir_prefix = path_parts[0]
            if not session_manager.validate_download_token(token, output_dir_prefix):
                raise HTTPException(status_code=401, detail="Token de descarga requerido o invalido.")
        return FileResponse(
            path=str(full_path),
            filename=full_path.name,
            media_type="application/octet-stream",
        )

    @app.post("/api/upload-reference")
    async def upload_reference_image(file: UploadFile = File(...)):
        """
        Recibe una imagen de referencia visual del usuario.
        La guarda en output/references/ y devuelve la ruta del servidor.
        """
        _ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        _MAX_SIZE_MB = 10

        if file.content_type not in _ALLOWED_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo de archivo no permitido: {file.content_type}. Usa JPG, PNG o WebP.",
            )

        data = await file.read()
        if len(data) > _MAX_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"El archivo supera el limite de {_MAX_SIZE_MB} MB.",
            )

        ref_dir = Path(os.getenv("OUTPUT_DIR", "output")) / "references"
        ref_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(file.filename or "ref.jpg").suffix.lower() or ".jpg"
        filename = f"ref_{uuid.uuid4().hex[:12]}{ext}"
        dest = ref_dir / filename
        dest.write_bytes(data)

        return {"reference_image_path": str(dest)}

    @app.get("/api/output")
    async def list_output():
        """List all completed books across all session subdirectories."""
        output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
        if not output_dir.exists():
            return {"files": []}
        files = []
        for f in output_dir.rglob("LIBRO_FINAL_*.docx"):
            rel = f.relative_to(output_dir).as_posix()
            files.append({
                "name": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "url": f"/api/output/{rel}",
                "session": rel.split("/")[0] if "/" in rel else None,
                "modified": f.stat().st_mtime,
            })
        files.sort(key=lambda x: x["modified"], reverse=True)
        return {"files": files}

    @app.get("/api/biblioteca")
    async def list_biblioteca():
        """Lista todos los libros en la carpeta Biblioteca del proyecto."""
        base = Path(__file__).parent.parent.parent
        biblioteca = base / "Biblioteca"
        if not biblioteca.exists():
            return {"books": []}
        books = []
        for docx in sorted(biblioteca.rglob("*.docx"), key=lambda f: f.stat().st_mtime, reverse=True):
            folder = docx.parent.name   # ej: 2026-04-23_Mi-Libro
            parts = folder.split("_", 1)
            date_str = parts[0] if len(parts) == 2 else ""
            title = parts[1].replace("-", " ") if len(parts) == 2 else folder
            books.append({
                "name":     docx.name,
                "title":    title,
                "date":     date_str,
                "size_kb":  round(docx.stat().st_size / 1024, 1),
                "folder":   folder,
                "rel_path": f"{folder}/{docx.name}",
            })
        return {"books": books}

    @app.get("/api/biblioteca/{folder}/{filename}")
    async def download_biblioteca(folder: str, filename: str):
        """Descarga un libro de la Biblioteca."""
        base = Path(__file__).parent.parent.parent
        full_path = (base / "Biblioteca" / folder / filename).resolve()
        biblioteca_root = (base / "Biblioteca").resolve()
        if not str(full_path).startswith(str(biblioteca_root)):
            raise HTTPException(status_code=400, detail="Ruta invalida")
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Libro no encontrado")
        return FileResponse(
            path=str(full_path),
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    @app.post("/api/regenerate-images/{session_id}")
    async def regenerate_images(session_id: str):
        """Re-generate all images (cover + chapters) for a completed book and re-assemble the docx."""
        import asyncio
        loop = asyncio.get_event_loop()
        output_root = Path(os.getenv("OUTPUT_DIR", "output")).resolve()
        try:
            result = await loop.run_in_executor(None, _do_regenerate_images, session_id, output_root)
            return result
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # -- Serve React frontend (production build) --------------------------------
    frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            index = frontend_dist / "index.html"
            return FileResponse(str(index))

    return app


def _do_regenerate_images(session_id: str, output_root: Path) -> dict:
    """
    Runs in a thread executor.
    Loads the checkpoint for session_id, regenerates all chapter images and the cover,
    re-assembles the final docx, and returns the new download path.
    """
    import sqlite3
    from backend.graph.builder import build_graph
    from backend.graph.utils import parse_formatted_text
    from backend.tools.documents import create_chapter_docx, assemble_final_book
    from backend.tools.cover_generator import generate_cover

    db_path = os.getenv("CHECKPOINT_DB", "output/checkpoints.db")
    if not Path(db_path).exists():
        raise ValueError(f"No hay checkpoint disponible en '{db_path}'")

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id LIKE ?",
        (f"{session_id}%",),
    ).fetchall()
    conn.close()

    if not rows:
        raise ValueError(f"Sesion '{session_id}' no encontrada en el checkpoint")

    thread_id = rows[0][0]
    graph = build_graph()
    config = {"configurable": {"thread_id": thread_id}}
    state = graph.get_state(config)

    if not state or not state.values:
        raise ValueError("No se pudo leer el estado del checkpoint")

    v = state.values
    title             = v.get("title", "Libro")
    genre             = v.get("genre", "")
    visual_ctx        = v.get("visual_context", "")
    approved_chapters = v.get("approved_chapters", [])
    output_dir        = str(output_root / thread_id[:8])
    # No usar imagen de referencia en regeneracion -- el remix causa 500 con archivos locales
    ref_img           = ""

    # Regenerar imagenes de capitulos
    regen_chapters = []
    for ch in approved_chapters:
        content_blocks = parse_formatted_text(ch.get("formatted_content", ""))
        docx_path, _ = create_chapter_docx(
            output_dir=output_dir,
            book_title=title,
            chapter_index=ch["index"],
            chapter_title=ch["title"],
            content_blocks=content_blocks,
            genre=genre,
            reference_image_path=ref_img,
            visual_context=visual_ctx,
            chapter_content=ch.get("formatted_content", "")[:2000],
        )
        regen_chapters.append({**ch, "docx_path": docx_path})

    # Regenerar portada
    cover_path, _ = generate_cover(
        title=title,
        subtitle=v.get("subtitle", ""),
        author_name=v.get("author_name", ""),
        cover_description=v.get("cover_description", ""),
        output_dir=output_dir,
        genre=genre,
        reference_image_path=ref_img,
    )

    # Re-ensamblar libro completo
    final_path = assemble_final_book(
        output_dir=output_dir,
        title=title,
        subtitle=v.get("subtitle", ""),
        author_name=v.get("author_name", ""),
        genre=genre,
        prefacio=v.get("prefacio", ""),
        pagina_legal=v.get("pagina_legal", ""),
        agradecimientos=v.get("agradecimientos", ""),
        author_bio=v.get("sobre_el_autor") or v.get("author_bio", ""),
        chapters=regen_chapters,
        cover_image_path=cover_path,
        reference_image_path=ref_img,
        visual_context=visual_ctx,
    )

    rel_path = Path(final_path).relative_to(output_root).as_posix()
    return {"download_path": rel_path, "title": title, "session_id": session_id}
