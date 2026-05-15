// Cliente para las edge functions admin (Lovable Cloud).
// El token de sesión se guarda en localStorage y viaja en Authorization: Bearer.

import { supabase } from '../integrations/supabase/client'

const TOKEN_KEY = 'obra_admin_token'
const USER_KEY = 'obra_admin_user'
const EXP_KEY = 'obra_admin_exp'

export function getAdminToken() {
  try {
    const exp = Number(localStorage.getItem(EXP_KEY) || 0)
    if (exp && exp * 1000 < Date.now()) {
      clearAdminSession()
      return null
    }
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
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

async function invoke(name, { body, method = 'POST' } = {}) {
  const token = getAdminToken()
  const headers = token ? { Authorization: `Bearer ${token}` } : {}
  const { data, error } = await supabase.functions.invoke(name, {
    method,
    body,
    headers,
  })
  if (error) {
    // supabase-js wraps non-2xx; intenta extraer JSON
    let detail = null
    try { detail = await error.context?.json?.() } catch {}
    const message = detail?.error || error.message || 'Error de red'
    const err = new Error(message)
    err.status = error.context?.status
    throw err
  }
  return data
}

export async function adminLogin(codigo_usuario, contrasena) {
  const data = await invoke('admin-login', {
    method: 'POST',
    body: { codigo_usuario, contrasena },
  })
  if (!data?.token) throw new Error('Respuesta inválida')
  saveSession(data)
  return data
}

export async function adminLogout() {
  clearAdminSession()
}

export async function adminFetchData() {
  return invoke('admin-data', { method: 'GET' })
}

export async function adminAssignCode(submission_id, code_id) {
  return invoke('admin-assign', {
    method: 'POST',
    body: { submission_id, code_id },
  })
}

export async function adminGenerateCodes(count = 10) {
  return invoke('admin-generate-codes', {
    method: 'POST',
    body: { count },
  })
}
