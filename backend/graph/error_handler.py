"""
Manejador centralizado de errores — Sistema Editorial Multi-Agente
Normaliza todos los errores del sistema a mensajes en español comprensibles
para el usuario final, con instrucciones claras sobre qué hacer.

Categorías de error:
  - RED / CONEXIÓN   → reintento automático (no requiere acción del usuario)
  - LLM / API        → reintento automático con backoff
  - CONFIGURACIÓN    → error permanente, requiere acción del administrador
  - DATOS            → error en el contenido generado, se recupera automáticamente
  - SISTEMA          → error inesperado, se registra y muestra mensaje genérico
  - SEGURIDAD        → rechazo de entrada por política de uso — permanente, no reintentable
"""

import logging
import traceback
from enum import Enum
from typing import Optional

logger = logging.getLogger("editorial_system")


# ── Categorías de error ───────────────────────────────────────────────────────

class ErrorCategory(str, Enum):
    NETWORK       = "red"           # Pérdida de conexión, timeout — reintento automático
    LLM_API       = "api_llm"       # Error de la API de Anthropic — reintento automático
    RATE_LIMIT    = "limite_uso"    # Rate limit de la API — espera y reintento
    CONFIGURATION = "configuracion" # API key faltante, variable de entorno — permanente
    DATA          = "datos"         # JSON inválido, campo faltante — recuperable
    STORAGE       = "almacenamiento"# Error al guardar archivos — puede ser temporal
    SYSTEM        = "sistema"       # Error inesperado — registrar y continuar
    SECURITY      = "seguridad"     # Rechazo de entrada por política de seguridad


# ── Mensajes en español para el usuario ──────────────────────────────────────

_MENSAJES_USUARIO = {
    ErrorCategory.NETWORK: (
        "⚡ Conexión interrumpida temporalmente. "
        "El sistema retomará automáticamente donde quedó — no pierdas tu trabajo."
    ),
    ErrorCategory.LLM_API: (
        "⏳ El servicio de escritura tardó en responder. "
        "Reintentando automáticamente…"
    ),
    ErrorCategory.RATE_LIMIT: (
        "⏸️  Se alcanzó el límite de uso momentáneo de la API. "
        "El sistema esperará unos segundos y continuará solo."
    ),
    ErrorCategory.CONFIGURATION: (
        "⚙️  Error de configuración del sistema. "
        "Puede ser créditos insuficientes en Anthropic (ve a console.anthropic.com → Plans & Billing) "
        "o una clave API faltante/incorrecta. Tu progreso está guardado — "
        "recarga créditos y reconecta con el mismo session_id para continuar."
    ),
    ErrorCategory.DATA: (
        "🔄 El agente generó una respuesta con formato inesperado. "
        "Reintentando la operación automáticamente…"
    ),
    ErrorCategory.STORAGE: (
        "💾 No se pudo guardar un archivo temporalmente. "
        "Verifica que el disco tenga espacio disponible. Reintentando…"
    ),
    ErrorCategory.SYSTEM: (
        "🔧 Ocurrió un error inesperado en el sistema. "
        "El equipo técnico ha sido notificado. Intenta continuar — "
        "tu progreso está guardado en el checkpoint."
    ),
    ErrorCategory.SECURITY: (
        "🚫 Tu solicitud no pudo procesarse.\n\n"
        "El contenido enviado no es compatible con las políticas de uso de este sistema. "
        "Por favor revisa tu idea y vuelve a intentarlo.\n\n"
        "Si crees que esto es un error, contacta al administrador."
    ),
}

# Mensajes de recuperación exitosa (para mostrar después del reintento)
_MENSAJES_RECUPERACION = {
    ErrorCategory.NETWORK:    "✅ Conexión restablecida. Continuando desde donde quedó.",
    ErrorCategory.LLM_API:    "✅ Servicio respondió correctamente. Continuando.",
    ErrorCategory.RATE_LIMIT: "✅ Límite de uso liberado. Continuando.",
    ErrorCategory.DATA:       "✅ Respuesta corregida. Continuando.",
    ErrorCategory.STORAGE:    "✅ Archivo guardado correctamente. Continuando.",
}


# ── Clasificador de excepciones ───────────────────────────────────────────────

def classify_exception(exc: Exception) -> ErrorCategory:
    """
    Clasifica una excepción en una categoría de error.
    Cubre excepciones de: requests, anthropic, langchain, json, OSError.
    """
    exc_type = type(exc).__name__
    exc_str  = str(exc).lower()
    module   = type(exc).__module__ or ""

    # ── Errores de red / conexión ─────────────────────────────────────────
    if exc_type in (
        "ConnectionError", "ConnectTimeout", "ReadTimeout",
        "Timeout", "ConnectionResetError", "BrokenPipeError",
        "RemoteDisconnected", "IncompleteRead",
        "APIConnectionError", "APITimeoutError",
    ):
        return ErrorCategory.NETWORK

    if "timeout" in exc_str or "connection" in exc_str or "network" in exc_str:
        return ErrorCategory.NETWORK

    # ── Rate limit ────────────────────────────────────────────────────────
    if exc_type in ("RateLimitError",) or "rate limit" in exc_str or "429" in exc_str:
        return ErrorCategory.RATE_LIMIT

    if "overloaded" in exc_str or "529" in exc_str:
        return ErrorCategory.RATE_LIMIT

    # ── Créditos insuficientes (error permanente, requiere acción del usuario) ─
    if "credit balance is too low" in exc_str or "credit" in exc_str and "low" in exc_str:
        return ErrorCategory.CONFIGURATION

    # ── Errores de API del LLM ────────────────────────────────────────────
    if exc_type in (
        "APIStatusError", "APIError", "InternalServerError",
        "ServiceUnavailableError", "BadRequestError",
    ):
        return ErrorCategory.LLM_API

    if "anthropic" in module or "langchain_anthropic" in module:
        return ErrorCategory.LLM_API

    if "500" in exc_str or "502" in exc_str or "503" in exc_str:
        return ErrorCategory.LLM_API

    # ── Errores de configuración ──────────────────────────────────────────
    if exc_type in ("AuthenticationError",) or "api key" in exc_str or "401" in exc_str:
        return ErrorCategory.CONFIGURATION

    if "authentication" in exc_str or "unauthorized" in exc_str:
        return ErrorCategory.CONFIGURATION

    # ── Errores de datos / formato ────────────────────────────────────────
    if exc_type in ("JSONDecodeError", "JSONExtractionError", "ValidationError"):
        return ErrorCategory.DATA

    if exc_type == "ValueError" and (
        "json" in exc_str or "campo" in exc_str or "plan" in exc_str
    ):
        return ErrorCategory.DATA

    if exc_type in ("KeyError", "IndexError", "AttributeError"):
        return ErrorCategory.DATA

    # ── Errores de almacenamiento ─────────────────────────────────────────
    if exc_type in ("OSError", "IOError", "PermissionError", "FileNotFoundError"):
        return ErrorCategory.STORAGE

    if "disk" in exc_str or "space" in exc_str or "write" in exc_str:
        return ErrorCategory.STORAGE

    # ── Cualquier otro error ──────────────────────────────────────────────
    return ErrorCategory.SYSTEM


# ── Interfaz pública ──────────────────────────────────────────────────────────

class ErrorInfo:
    """Resultado del análisis de un error."""
    def __init__(
        self,
        exc: Exception,
        context: str = "",
        category: Optional[ErrorCategory] = None,
    ):
        self.exc       = exc
        self.context   = context
        self.category  = category or classify_exception(exc)
        self.retryable = self.category in (
            ErrorCategory.NETWORK,
            ErrorCategory.LLM_API,
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.DATA,
            ErrorCategory.STORAGE,
        )
        self.user_message    = _MENSAJES_USUARIO[self.category]
        self.recovery_message = _MENSAJES_RECUPERACION.get(self.category, "✅ Operación completada.")

    def log(self) -> None:
        """Registra el error con contexto completo para debugging."""
        ctx = f" [{self.context}]" if self.context else ""
        logger.error(
            f"{ctx} {type(self.exc).__name__}: {self.exc} "
            f"| Categoría: {self.category.value} "
            f"| Reintentable: {self.retryable}"
        )
        if self.category == ErrorCategory.SYSTEM:
            logger.debug(traceback.format_exc())

    def __str__(self) -> str:
        return self.user_message


def handle_error(exc: Exception, context: str = "") -> ErrorInfo:
    """
    Punto de entrada principal. Clasifica, registra y retorna un ErrorInfo.

    Uso:
        except Exception as e:
            err = handle_error(e, context="Arquitecto/plan")
            if err.retryable:
                # el retry_llm_call() se encarga del reintento
                ...
            else:
                raise SystemError(err.user_message) from e
    """
    info = ErrorInfo(exc, context)
    info.log()
    return info
