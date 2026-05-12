"""
Session manager: one LangGraph instance per book project.
Manages thread IDs, graph state, and active WebSocket connections.
"""

import asyncio
import logging
import threading
import time
import uuid
from typing import Dict, Optional
from dataclasses import dataclass, field
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)

# Sessions idle (disconnected) more than this are garbage-collected
SESSION_TIMEOUT_SECONDS = 1800   # 30 minutes

# Tasks en fase autonoma se preservan hasta este limite
AUTONOMOUS_TIMEOUT_SECONDS = 10800  # 3 horas


@dataclass
class BookSession:
    session_id: str
    thread_id: str
    # Token secreto generado al crear la sesión. El cliente debe enviarlo
    # en cada reconexión para evitar secuestro de sesión.
    session_token: str = field(default_factory=lambda: uuid.uuid4().hex)
    interrupt_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    response_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    is_active: bool = True
    graph_task: Optional[asyncio.Task] = None
    last_active: float = field(default_factory=time.time)
    pending_interrupt: Optional[dict] = None
    connected: bool = False
    cancel_event: threading.Event = field(default_factory=threading.Event)
    # Nombre del agente activo (para informar al cliente al reconectar)
    current_agent: str = ""
    # Credenciales de invitación — para marcar como 'used' al completar el libro
    invite_code:  str = ""
    invite_email: str = ""


class SessionManager:
    """Singleton that manages all active book sessions."""

    def __init__(self):
        self._sessions: Dict[str, BookSession] = {}
        self.checkpointer = MemorySaver()
        # Tokens de sesiones completadas: token -> session_id[:8] (prefijo del output_dir)
        # Persisten en memoria para autorizar descargas después de que la sesión se elimine.
        self._download_tokens: Dict[str, str] = {}

    def create_session(self, session_id: Optional[str] = None) -> BookSession:
        sid = session_id or str(uuid.uuid4())
        session = BookSession(
            session_id=sid,
            thread_id=sid,
        )
        self._sessions[sid] = session
        return session

    def get_session(self, session_id: str) -> Optional[BookSession]:
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def register_download_token(self, session: "BookSession") -> None:
        """Registra el token de una sesión para autorizar descargas post-completado."""
        self._download_tokens[session.session_token] = session.session_id

    def validate_download_token(self, token: str, output_dir_prefix: str) -> bool:
        """True si el token autoriza acceso al directorio output_dir_prefix."""
        if not token:
            return False
        owner_session_id = self._download_tokens.get(token)
        if owner_session_id is None:
            # También aceptar token de sesión aún activa
            for s in self._sessions.values():
                if s.session_token == token and s.session_id.startswith(output_dir_prefix):
                    return True
            return False
        return owner_session_id.startswith(output_dir_prefix)

    def get_langgraph_config(self, session: BookSession) -> dict:
        return {"configurable": {"thread_id": session.thread_id}}

    async def cleanup_expired_sessions(self) -> None:
        """Remove sessions disconnected longer than SESSION_TIMEOUT_SECONDS."""
        now = time.time()
        to_remove = []
        for sid, s in list(self._sessions.items()):
            if s.connected:
                continue
            idle = now - s.last_active
            if idle <= SESSION_TIMEOUT_SECONDS:
                continue

            task_running = s.graph_task is not None and not s.graph_task.done()
            waiting_for_user = s.pending_interrupt is not None

            if task_running and not waiting_for_user:
                if idle <= AUTONOMOUS_TIMEOUT_SECONDS:
                    logger.debug(
                        f"[SessionManager] Sesion {sid[:8]}... autonoma -- preservada "
                        f"({idle/60:.0f} min inactiva)"
                    )
                    continue

            to_remove.append(sid)

        for sid in to_remove:
            session = self._sessions.pop(sid, None)
            if session:
                session.is_active = False
                if session.graph_task and not session.graph_task.done():
                    session.graph_task.cancel()
                logger.info(f"[SessionManager] Sesion {sid[:8]}... expirada y eliminada")


# Global singleton
session_manager = SessionManager()
