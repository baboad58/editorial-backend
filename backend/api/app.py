"""
FastAPI application factory.
Mounts the WebSocket endpoint and REST endpoints for health/session info.
"""

import asyncio
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.api.websocket import book_websocket_handler
from backend.api.session import session_manager


async def _session_cleanup_loop() -> None:
    """Background task: purge sessions idle longer than SESSION_TIMEOUT_SECONDS."""
    while True:
        await asyncio.sleep(60)   # check every minute
        await session_manager.cleanup_expired_sessions()


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
        await book_websocket_handler(websocket)

    # -- REST endpoints --------------------------------------------------------
    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "book-factory"}

    @app.get("/api/output/{filepath:path}")
    async def download_output(filepath: str):
        """Download a generated book file (supports session subdirectories)."""
        from fastapi import HTTPException
        output_root = Path(os.getenv("OUTPUT_DIR", "output")).resolve()
        full_path = (output_root / filepath).resolve()
        # Security: prevent path traversal outside output dir
        if not str(full_path).startswith(str(output_root)):
            raise HTTPException(status_code=400, detail="Ruta invalida")
        if not full_path.exists() or not full_path.is_file():
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
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

    @app.get("/api/validate-ideogram")
    async def validate_ideogram():
        """Test the Ideogram API key with a minimal request."""
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _test_ideogram_key)
        return result

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


def _test_ideogram_key() -> dict:
    """Makes a minimal Ideogram API call to validate the key and API status."""
    import requests as _req
    import backend.tools.cover_generator as _cg
    api_key = os.getenv("IDEOGRAM_API_KEY", "")
    if not api_key or api_key.startswith("tvly-placeholder"):
        return {"valid": False, "status": "no_key", "message": "IDEOGRAM_API_KEY no configurada"}

    try:
        _cg._rate_limit_wait()
        resp = _req.post(
            "https://api.ideogram.ai/v1/ideogram-v2/generate",
            headers={"Api-Key": api_key, "Content-Type": "application/json"},
            json={"prompt": "a blue circle", "aspect_ratio": "ASPECT_1_1", "style_type": "GENERAL", "expand_prompt": False},
            timeout=30,
        )
        import time as _t; _cg._last_ideogram_call = _t.time()
        if resp.status_code == 200:
            return {"valid": True, "status": "ok", "message": "API key valida y API funcionando correctamente"}
        if resp.status_code in (401, 403):
            return {"valid": False, "status": "invalid_key", "message": f"API key invalida o sin permisos ({resp.status_code})"}
        if resp.status_code == 429:
            return {"valid": True, "status": "rate_limited", "message": "API key valida pero limite de requests alcanzado (429)"}
        if resp.status_code == 402:
            return {"valid": True, "status": "no_credits", "message": "API key valida pero sin creditos (402)"}
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"raw": resp.text[:200]}
        return {"valid": None, "status": f"http_{resp.status_code}", "message": f"Respuesta inesperada ({resp.status_code}): {body}"}
    except Exception as e:
        return {"valid": None, "status": "error", "message": f"Error de red: {e}"}


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
    from backend.tools.cover_generator import generate_cover_with_ideogram

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
    cover_path, _ = generate_cover_with_ideogram(
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
