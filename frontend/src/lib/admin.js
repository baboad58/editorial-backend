// Cliente admin para los endpoints FastAPI propios (/api/admin/*).
// Reemplaza las Edge Functions de Lovable — funciona local y en producción.

const TOKEN_KEY = 'obra_admin_token'
const USER_KEY  = 'obra_admin_user'
const EXP_KEY   = 'obra_admin_exp'
const API_BASE  = import.meta.env.VITE_API_URL || ''

export function getAdminToken() {
  try {
    const exp = Number(localStorage.getItem(EXP_KEY) || 0)
    if (exp && exp * 1000 < Date.now()) { clearAdminSession(); return null }
    return localStorage.getItem(TOKEN_KEY)
  } catch { return null }
}

export function getAdminUser() {
  try { return localStorage.getItem(USER_KEY) } catch { return null }
}

export function clearAdminSession() {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    localStorage.removeItem(EXP_KEY)
  } catch {}
}

function saveSession({ token, codigo_usuario, exp }) {
  try {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, codigo_usuario)
    localStorage.setItem(EXP_KEY, String(exp))
  } catch {}
}

async function apiFetch(path, { method = 'GET', body } = {}) {
  const token = getAdminToken()
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  let data = null
  try { data = await res.json() } catch {}

  if (!res.ok) {
    const err = new Error(data?.detail || data?.message || `Error ${res.status}`)
    err.status = res.status
    throw err
  }
  return data
}

export async function adminLogin(codigo_usuario, contrasena) {
  const data = await apiFetch('/api/admin/login', {
    method: 'POST',
    body: { codigo_usuario, contrasena },
  })
  if (!data?.token) throw new Error('Respuesta inválida del servidor')
  saveSession(data)
  return data
}

export async function adminLogout() {
  clearAdminSession()
}

export async function adminFetchData() {
  return apiFetch('/api/admin/data')
}

export async function adminAssignCode(submission_id, code_id) {
  return apiFetch('/api/admin/assign', {
    method: 'POST',
    body: { submission_id, code_id },
  })
}

export async function adminGenerateCodes(count = 10) {
  return apiFetch('/api/admin/generate-codes', {
    method: 'POST',
    body: { count },
  })
}
