// Gestión de acceso al estudio.
// La validación de códigos ocurre en el BACKEND (POST /api/verify-invite).
// El frontend solo almacena el token de sesión una vez que el backend confirma.

const ACCESS_KEY = 'obra_access_granted'
const API_BASE = import.meta.env.VITE_API_URL || ''

export function isAccessGranted() {
  try {
    return sessionStorage.getItem(ACCESS_KEY) === '1'
  } catch {
    return false
  }
}

/**
 * Verifica el código contra el backend.
 * Retorna { ok: true } o { ok: false, error: string }.
 */
export async function verifyInvite(code) {
  const normalized = String(code || '').trim().toUpperCase()
  if (!normalized) return { ok: false, error: 'Código requerido.' }
  try {
    const res = await fetch(`${API_BASE}/api/verify-invite`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: normalized }),
    })
    if (res.ok) {
      try { sessionStorage.setItem(ACCESS_KEY, '1') } catch {}
      return { ok: true }
    }
    if (res.status === 429) {
      return { ok: false, error: 'Demasiados intentos. Espera una hora.' }
    }
    return { ok: false, error: 'Código no válido. Revisa que esté escrito correctamente.' }
  } catch {
    return { ok: false, error: 'No se pudo conectar con el servidor. Intenta de nuevo.' }
  }
}

export function revokeAccess() {
  try {
    sessionStorage.removeItem(ACCESS_KEY)
  } catch {}
}
