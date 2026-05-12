"""
WebSocket message protocol models.
All messages between server and client follow these schemas.
"""

from typing import Any, Optional, Literal
from pydantic import BaseModel


# ── Client → Server ────────────────────────────────────────────────────────────

class StartMessage(BaseModel):
    type: Literal["start"]
    idea: str
    session_id: Optional[str] = None  # If provided, resume existing session


class ResumeMessage(BaseModel):
    type: Literal["resume"]
    response: str


class PingMessage(BaseModel):
    type: Literal["ping"]


# ── Server → Client ────────────────────────────────────────────────────────────

class AgentStatusMessage(BaseModel):
    type: Literal["agent_status"] = "agent_status"
    agent: str
    status: str  # "working" | "waiting" | "done"
    chapter_num: Optional[int] = None
    total_chapters: Optional[int] = None


class InterruptMessage(BaseModel):
    type: Literal["interrupt"] = "interrupt"
    interrupt_type: str   # "interview" | "plan_approval" | "chapter_review" | etc.
    agent: str
    data: dict            # Full interrupt payload for the frontend to render


class BookCompleteMessage(BaseModel):
    type: Literal["complete"] = "complete"
    title: str
    final_path: str        # ruta absoluta en el servidor (para mostrar al usuario)
    download_path: str     # ruta relativa con forward slashes para /api/output/{path}
    output_dir: str
    chapters_count: int


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str
    recoverable: bool = False
    category: Optional[str] = None


class SecurityRejectedMessage(BaseModel):
    """Rechazo explícito por política de seguridad.

    Tipo propio (no "error") para que el frontend pueda renderizarlo
    de forma diferenciada: sin ícono de fallo técnico, sin opción de
    reintento automático, con instrucción clara al usuario.
    """
    type: Literal["security_rejected"] = "security_rejected"
    # Motivo legible para el usuario — nunca exponer detalles técnicos internos
    message: str
    # Código corto para que el frontend decida cómo renderizar
    # "input_too_long" | "unsafe_content" | "rate_limit_session"
    code: str
    # Sugerencia concreta de acción para el usuario
    suggestion: str


class PongMessage(BaseModel):
    type: Literal["pong"] = "pong"


class SessionCreatedMessage(BaseModel):
    type: Literal["session_created"] = "session_created"
    session_id: str
