// Gestión de acceso al estudio.
// La validación ocurre en el BACKEND via Supabase (POST /api/verify-invite).
// El par email+code se guarda en localStorage para marcar como 'used' al terminar.

const INVITE_KEY = 'obra_invite'   // { email, code }
const API_BASE   = import.meta.env.VITE_API_URL || ''

export function getStoredInvite() {
  try {
    return JSON.parse(localStorage.getItem(INVITE_KEY) || 'null')
  } catch {
    return null
  }
}

export function clearStoredInvite() {
  try { localStorage.removeItem(INVITE_KEY) } catch {}
}

/**
 * Verifica el par email+code contra el backend (Supabase).
 * Si es válido, guarda la invitación en localStorage.
 * Retorna { ok: true } o { ok: false, error: string }.
 */
export async function verifyInvite(code, email) {
  const normalizedCode  = String(code  || '').trim().toUpperCase()
  const normalizedEmail = String(email || '').trim().toLowerCase()

  if (!normalizedCode)  return { ok: false, error: 'Código requerido.' }
  if (!normalizedEmail) return { ok: false, error: 'Email requerido.' }

  try {
    const res = await fetch(`${API_BASE}/api/verify-invite`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ code: normalizedCode, email: normalizedEmail }),
    })

    if (res.ok) {
      try {
        localStorage.setItem(INVITE_KEY, JSON.stringify({
          code:  normalizedCode,
          email: normalizedEmail,
        }))
      } catch {}
      return { ok: true }
    }

    if (res.status === 429) {
      return { ok: false, error: 'Demasiados intentos. Espera una hora.' }
    }
    if (res.status === 401) {
      return {
        ok: false,
        error: 'Email o código no válidos, o el código ya fue utilizado.',
      }
    }
    return { ok: false, error: 'Error al verificar. Intenta de nuevo.' }
  } catch {
    return { ok: false, error: 'No se pudo conectar con el servidor. Intenta de nuevo.' }
  }
}

/**
 * Notifica al backend que el código fue consumido.
 * Usa sendBeacon si beacon=true (para beforeunload).
 */
export function markInviteUsed(beacon = false) {
  const invite = getStoredInvite()
  if (!invite?.code || !invite?.email) return

  const body = JSON.stringify({ code: invite.code, email: invite.email })

  if (beacon && navigator.sendBeacon) {
    navigator.sendBeacon(
      `${API_BASE}/api/mark-invite-used`,
      new Blob([body], { type: 'application/json' }),
    )
  } else {
    fetch(`${API_BASE}/api/mark-invite-used`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
    }).catch(() => {})
  }
}
