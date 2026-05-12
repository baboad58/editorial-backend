"""
WebSocket endpoint handler.
Manages the full lifecycle of a book session over a single WebSocket connection.

Reconnection strategy:
- On any disconnect the graph task keeps running in background.
- Session is preserved in SessionManager for SESSION_TIMEOUT_SECONDS (15 min).
- When client reconnects with the same session_id the handler reattaches:
    - If runner is still computing: just read from interrupt_queue normally.
    - If runner is waiting for user input: pending_interrupt is re-queued so
      the client receives the question again without re-running the graph.
- Session is only removed on: book complete, irrecoverable error, or expiry.
"""

import asyncio
import json
import logging
import time

from fastapi import WebSocket, WebSocketDisconnect

from backend.api.session import session_manager, BookSession
from backend.api.graph_runner import run_book_session, _MAX_IDEA_CHARS, _MAX_RESUME_CHARS
from backend.api.models import SecurityRejectedMessage
from backend.api.models import (
    SessionCreatedMessage,
    InterruptMessage,
    AgentStatusMessage,
    BookCompleteMessage,
    ErrorMessage,
    PongMessage,
)

logger = logging.getLogger(__name__)

INTERRUPT_AGENT_MAP = {
    "interview":              "Arquitecto",
    "interview_confirmation": "Arquitecto",
    "plan_approval":          "Arquitecto",
    "chapter_review":         "Escritor",
    "author_info":            "Publicador",
    "final_approval":         "Publicador",
}


async def _send(ws: WebSocket, data: dict) -> None:
    """Send JSON message to client, ignoring disconnects."""
    try:
        await ws.send_json(data)
    except Exception:
        pass


async def book_websocket_handler(websocket: WebSocket) -> None:
    """
    Full WebSocket lifecycle for one book session.

    Flow (new session):
      1. Client connects -> receives {type: start, idea: ...}
      2. Server creates session, sends session_created
      3. Starts graph runner as background task
      4. Loop: read interrupt_queue -> send to client -> wait for resume -> response_queue

    Flow (reconnect):
      1. Client connects -> receives {type: start, session_id: <existing>}
      2. Server finds live session, reattaches without restarting runner
      3. Re-sends pending interrupt if client had not yet responded
      4. Continues the same interrupt/resume loop

    Terminal cleanup (remove session + cancel task) happens only on:
      - Book complete
      - Irrecoverable error
      - All reconnect attempts exhausted (client calls onDisconnect -> stops sending)
    """
    await websocket.accept()

    session: BookSession | None = None
    should_cleanup = False

    try:
        # Step 1: Wait for start message
        raw = await websocket.receive_text()
        msg = json.loads(raw)

        if msg.get("type") == "ping":
            await _send(websocket, PongMessage().model_dump())
            return

        if msg.get("type") != "start":
            await _send(websocket, ErrorMessage(
                message="Primera mensaje debe ser {type: 'start', idea: '...'}",
                recoverable=False,
            ).model_dump())
            return

        idea = msg.get("idea", "").strip()
        existing_session_id = msg.get("session_id")
        reference_image_path = msg.get("reference_image_path", "")

        if len(idea) > _MAX_IDEA_CHARS:
            await _send(websocket, SecurityRejectedMessage(
                message=(
                    f"Tu idea supera el limite de {_MAX_IDEA_CHARS} caracteres "
                    f"({len(idea)} recibidos)."
                ),
                code="input_too_long",
                suggestion="Resume tu idea en una o dos oraciones e intenta de nuevo.",
            ).model_dump())
            return

        if not idea and not existing_session_id:
            await _send(websocket, ErrorMessage(
                message="El campo 'idea' no puede estar vacio.",
                recoverable=False,
            ).model_dump())
            return

        auto_mode = bool(msg.get("auto", False))

        # Step 2: New session or reconnect
        existing = (
            session_manager.get_session(existing_session_id)
            if existing_session_id else None
        )

        runner_is_alive = (
            existing is not None
            and existing.graph_task is not None
            and not existing.graph_task.done()
        )

        if runner_is_alive:
            # RECONNECT: reattach to the running session
            session = existing
            session.connected = True
            session.last_active = time.time()
            logger.info(f"[WS] Reconexion a sesion viva {session.session_id[:8]}...")

            # Indicar al frontend que es reconexion (no resetear estado de UI)
            await _send(websocket, {
                **SessionCreatedMessage(session_id=session.session_id).model_dump(),
                "reconnected": True,
            })

            # Informar el agente activo antes de re-entregar el interrupt
            if session.current_agent:
                await _send(websocket, AgentStatusMessage(
                    agent=session.current_agent,
                    status="working",
                ).model_dump())

            # Re-queue pending interrupt so client receives the question again
            if session.pending_interrupt is not None:
                logger.info("[WS] Re-enviando interrupt pendiente al cliente")
                await session.interrupt_queue.put(session.pending_interrupt)
                session.pending_interrupt = None

        else:
            # NEW SESSION (or dead session -- start fresh)
            session = session_manager.create_session(existing_session_id)
            session.connected = True
            session.cancel_event.clear()
            logger.info(f"[WS] Nueva sesion {session.session_id[:8]}...")

            await _send(websocket, SessionCreatedMessage(
                session_id=session.session_id,
            ).model_dump())

            graph_task = asyncio.create_task(
                run_book_session(
                    session, idea,
                    resume=bool(existing_session_id),
                    auto_mode=auto_mode,
                    reference_image_path=reference_image_path,
                ),
                name=f"book-session-{session.session_id}",
            )
            session.graph_task = graph_task

        # Step 3: Interrupt / resume loop
        while True:
            try:
                interrupt_value = await _wait_for_interrupt(
                    session.interrupt_queue, websocket, timeout=600
                )
            except asyncio.TimeoutError:
                logger.info("[WS] Timeout esperando al runner -- sesion preservada para reconexion")
                session.connected = False
                session.last_active = time.time()
                return

            iv_type = interrupt_value.get("type") if isinstance(interrupt_value, dict) else None

            # Runner signals: forward as status updates, don't ask user

            if iv_type == "__agent_working__":
                agent_name = interrupt_value.get("agent", "Sistema")
                session.current_agent = agent_name  # guardar para informar al reconectar
                await _send(websocket, AgentStatusMessage(
                    agent=agent_name,
                    status="working",
                ).model_dump())
                continue

            if iv_type == "__heartbeat__":
                await _send(websocket, {"type": "ping"})
                continue

            if iv_type == "__system_warning__":
                await _send(websocket, {
                    "type":    "system_warning",
                    "message": interrupt_value.get("message", ""),
                })
                continue

            if iv_type == "__done__":
                break

            if iv_type == "security_rejected":
                await _send(websocket, interrupt_value)
                should_cleanup = True
                break

            if iv_type == "__complete__":
                await _send(websocket, BookCompleteMessage(
                    title=interrupt_value.get("title", ""),
                    final_path=interrupt_value.get("final_path", ""),
                    download_path=interrupt_value.get("download_path", ""),
                    output_dir=interrupt_value.get("output_dir", "output"),
                    chapters_count=interrupt_value.get("chapters_count", 0),
                ).model_dump())
                should_cleanup = True
                break

            if iv_type == "__error__":
                recoverable = interrupt_value.get("recoverable", False)
                await _send(websocket, ErrorMessage(
                    message=interrupt_value.get("message", "Error desconocido"),
                    recoverable=recoverable,
                    category=interrupt_value.get("category"),
                ).model_dump())
                if not recoverable:
                    should_cleanup = True
                break

            # Normal interrupt: requires user response

            interrupt_type = interrupt_value.get("type", "generic")
            agent = interrupt_value.get("agent", INTERRUPT_AGENT_MAP.get(interrupt_type, "Sistema"))

            await _send(websocket, AgentStatusMessage(
                agent=agent,
                status="waiting",
                chapter_num=interrupt_value.get("chapter_num"),
                total_chapters=interrupt_value.get("total_chapters"),
            ).model_dump())

            # Save before sending so reconnect can re-deliver if client drops
            session.pending_interrupt = interrupt_value

            await _send(websocket, InterruptMessage(
                interrupt_type=interrupt_type,
                agent=agent,
                data=interrupt_value,
            ).model_dump())

            user_response = await _receive_user_response(websocket)

            if user_response is None:
                logger.info("[WS] Cliente desconectado esperando respuesta -- sesion preservada")
                session.connected = False
                session.last_active = time.time()
                return

            session.pending_interrupt = None
            await session.response_queue.put(user_response)

    except WebSocketDisconnect:
        logger.info("[WS] WebSocket desconectado")
        if session:
            session.connected = False
            session.last_active = time.time()
        return

    except asyncio.CancelledError:
        logger.info("[WS] Handler cancelado por el servidor -- sesion preservada para reconexion")
        if session:
            session.connected = False
            session.last_active = time.time()
        raise

    except Exception as e:
        logger.exception("[WS] Error en WebSocket handler")
        try:
            await _send(websocket, ErrorMessage(message=str(e)).model_dump())
        except Exception:
            pass
        should_cleanup = True

    finally:
        if session:
            session.connected = False
            session.last_active = time.time()
            if should_cleanup:
                session.is_active = False
                session_manager.remove_session(session.session_id)
                if session.graph_task and not session.graph_task.done():
                    session.graph_task.cancel()
                    try:
                        await session.graph_task
                    except (asyncio.CancelledError, Exception):
                        pass


async def _wait_for_interrupt(
    queue: asyncio.Queue,
    websocket: WebSocket,
    timeout: float = 600,
) -> dict:
    """
    Wait for the next item in the interrupt queue.

    Timeout se renueva con cada item recibido (heartbeat, agent_working, etc.)
    para que un LLM lento no provoque corte mientras el runner siga activo.

    Raises asyncio.TimeoutError si pasan `timeout` segundos sin ninguna senal.
    Raises WebSocketDisconnect si falla el ping (cliente desconectado).
    """
    PING_INTERVAL = 25
    last_activity = asyncio.get_event_loop().time()
    get_task = asyncio.ensure_future(queue.get())

    try:
        while True:
            elapsed_since_activity = asyncio.get_event_loop().time() - last_activity
            remaining = timeout - elapsed_since_activity
            if remaining <= 0:
                raise asyncio.TimeoutError

            done, _ = await asyncio.wait(
                {get_task},
                timeout=min(remaining, PING_INTERVAL),
            )

            if get_task in done:
                last_activity = asyncio.get_event_loop().time()
                return get_task.result()

            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                raise WebSocketDisconnect(code=1006)
    except BaseException:
        if not get_task.done():
            get_task.cancel()
        raise


async def _receive_user_response(websocket: WebSocket) -> str | None:
    """
    Wait for a resume message from the client.
    Returns the response string, or None on disconnect.
    """
    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            if msg.get("type") == "ping":
                await _send(websocket, PongMessage().model_dump())
                continue

            if msg.get("type") == "resume":
                response_text = msg.get("response", "")
                if len(response_text) > _MAX_RESUME_CHARS:
                    logger.warning(
                        "[WS] Respuesta de usuario truncada: "
                        f"{len(response_text)} -> {_MAX_RESUME_CHARS} chars"
                    )
                    response_text = response_text[:_MAX_RESUME_CHARS]
                return response_text

            if msg.get("type") == "start":
                logger.info("[WS] 'start' recibido en espera de resume -- cediendo al nuevo handler")
                return None

            logger.warning("[WS] Mensaje inesperado ignorado: %s", msg.get("type"))

    except (WebSocketDisconnect, Exception):
        return None
