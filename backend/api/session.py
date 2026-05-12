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


class SessionManager:
    """Singleton that manages all active book sessions."""

    def __init__(self):
        self._sessions: Dict[str, BookSession] = {}
        self.checkpointer = MemorySaver()

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
