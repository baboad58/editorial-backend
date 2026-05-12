"""
Sistema de reintentos automáticos — Sistema Editorial Multi-Agente
Envuelve todas las llamadas al LLM y operaciones de red con reintentos
inteligentes según la categoría de error, sin intervención del usuario.

Estrategia de backoff:
  - Red / conexión  : espera 2s, 4s, 8s  (hasta 3 intentos)
  - Rate limit      : espera 10s, 30s, 60s (hasta 3 intentos)
  - LLM API         : espera 3s, 6s, 12s  (hasta 3 intentos)
  - Datos / formato : reintento inmediato  (hasta 2 intentos)
  - Configuración   : sin reintento — error permanente

El decorador @with_retry envuelve cualquier función.
La función retry_llm_call() es el helper directo para llm.invoke().
"""

import logging
import time
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from backend.graph.error_handler import (
    ErrorCategory,
    ErrorInfo,
    handle_error,
)

logger = logging.getLogger("editorial_system")

F = TypeVar("F", bound=Callable[..., Any])


# ── Configuración de reintentos por categoría ─────────────────────────────────

_RETRY_CONFIG: dict[ErrorCategory, dict] = {
    ErrorCategory.NETWORK: {
        "max_attempts": 3,
        "delays":       [2, 4, 8],
        "auto_recover": True,
    },
    ErrorCategory.RATE_LIMIT: {
        "max_attempts": 3,
        "delays":       [10, 30, 60],
        "auto_recover": True,
    },
    ErrorCategory.LLM_API: {
        "max_attempts": 3,
        "delays":       [3, 6, 12],
        "auto_recover": True,
    },
    ErrorCategory.DATA: {
        "max_attempts": 2,
        "delays":       [0, 1],
        "auto_recover": True,
    },
    ErrorCategory.STORAGE: {
        "max_attempts": 2,
        "delays":       [1, 3],
        "auto_recover": True,
    },
    ErrorCategory.CONFIGURATION: {
        "max_attempts": 1,
        "delays":       [],
        "auto_recover": False,
    },
    ErrorCategory.SYSTEM: {
        "max_attempts": 1,
        "delays":       [],
        "auto_recover": False,
    },
}


# ── Excepción para errores no recuperables ────────────────────────────────────

class PermanentError(RuntimeError):
    """
    Error no reintentable. El mensaje está en español para mostrarse al usuario.
    """
    def __init__(self, user_message: str, original: Optional[Exception] = None):
        super().__init__(user_message)
        self.user_message = user_message
        self.original     = original


# ── Motor de reintentos ───────────────────────────────────────────────────────

def execute_with_retry(
    func: Callable,
    *args,
    context: str = "",
    **kwargs,
) -> Any:
    """
    Ejecuta func(*args, **kwargs) con reintentos automáticos.

    - Si el error es reintentable: espera el tiempo configurado y reintenta.
    - Si se agotan los intentos: lanza PermanentError con mensaje en español.
    - Si el error es permanente (configuración): lanza PermanentError inmediatamente.
    - Cuando se recupera tras un fallo: muestra mensaje de recuperación al log.

    Args:
        func:    función a ejecutar
        context: nombre del contexto para los logs (ej: "Arquitecto/plan")
        *args, **kwargs: argumentos para func
    """
    last_error_info: Optional[ErrorInfo] = None

    # Primer intento siempre se hace, luego los reintentos
    attempt = 0
    while True:
        try:
            result = func(*args, **kwargs)
            # Recuperación exitosa tras un fallo previo
            if last_error_info is not None and last_error_info.retryable:
                logger.info(
                    f"[Retry]{' [' + context + ']' if context else ''} "
                    f"{last_error_info.recovery_message}"
                )
            return result

        except Exception as exc:
            error_info = handle_error(exc, context=context)
            last_error_info = error_info

            config = _RETRY_CONFIG.get(error_info.category, _RETRY_CONFIG[ErrorCategory.SYSTEM])

            # Error permanente → fallo inmediato
            if not config["auto_recover"]:
                raise PermanentError(error_info.user_message, original=exc) from exc

            attempt += 1
            delays = config["delays"]

            if attempt > config["max_attempts"] or attempt > len(delays):
                # Agotados los intentos
                msg = (
                    f"{error_info.user_message}\n\n"
                    f"No se pudo recuperar tras {config['max_attempts']} intentos. "
                    f"Tu progreso está guardado. Intenta reanudar en unos minutos."
                )
                raise PermanentError(msg, original=exc) from exc

            # Calcular espera
            wait = delays[attempt - 1] if (attempt - 1) < len(delays) else delays[-1]

            ctx_str = f" [{context}]" if context else ""
            logger.warning(
                f"[Retry]{ctx_str} Intento {attempt}/{config['max_attempts']} "
                f"— {error_info.user_message} "
                f"— Reintentando en {wait}s…"
            )

            if wait > 0:
                time.sleep(wait)


# ── Decorador ─────────────────────────────────────────────────────────────────

def with_retry(context: str = "") -> Callable[[F], F]:
    """
    Decorador que añade reintentos automáticos a cualquier función.

    Uso:
        @with_retry(context="Editor/review")
        def mi_funcion():
            ...

    Los errores de red, rate limit y LLM se reintentan automáticamente.
    Los errores de configuración lanzan PermanentError inmediatamente.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            ctx = context or func.__qualname__
            return execute_with_retry(func, *args, context=ctx, **kwargs)
        return wrapper  # type: ignore
    return decorator


# ── Helper directo para llm.invoke() ─────────────────────────────────────────

def retry_llm_call(llm: Any, messages: list, context: str = "") -> Any:
    """
    Envuelve una llamada llm.invoke(messages) con reintentos automáticos.

    Reemplaza el patrón:
        response = llm.invoke([SystemMessage(...), HumanMessage(...)])

    Por:
        response = retry_llm_call(llm, [SystemMessage(...), HumanMessage(...)],
                                  context="Escritor/borrador")

    Maneja automáticamente:
      - Pérdida de conexión      → reintento en 2/4/8 segundos
      - Rate limit (429)         → reintento en 10/30/60 segundos
      - Error interno API (500)  → reintento en 3/6/12 segundos
      - Timeout                  → reintento en 2/4/8 segundos

    Lanza PermanentError (mensaje en español) si se agotan los intentos.
    """
    return execute_with_retry(
        llm.invoke,
        messages,
        context=context or "LLM",
    )
