// Códigos de invitación válidos para acceder al estudio.
// Edita esta lista para añadir/revocar accesos.
//
// NOTA: La validación es client-side. Cualquiera con conocimientos técnicos
// puede leer los códigos en el bundle. Suficiente para una beta cerrada,
// no para seguridad real. Para invitaciones serias (un solo uso, expiración,
// auditoría) hace falta un backend con tabla de invitaciones.

export const VALID_INVITES = new Set([
  'OBRA-ALPHA-001',
  'OBRA-ALPHA-002',
  'OBRA-ALPHA-003',
  'OBRA-ALPHA-004',
  'OBRA-ALPHA-005',
  'OBRA-ALPHA-006',
  'OBRA-ALPHA-007',
  'OBRA-ALPHA-008',
  'OBRA-ALPHA-009',
  'OBRA-ALPHA-010',
])

const ACCESS_KEY = 'obra_access_granted'

export function isAccessGranted() {
  try {
    return sessionStorage.getItem(ACCESS_KEY) === '1'
  } catch {
    return false
  }
}

export function grantAccess(code) {
  const normalized = String(code || '').trim().toUpperCase()
  if (!VALID_INVITES.has(normalized)) return false
  try {
    sessionStorage.setItem(ACCESS_KEY, '1')
  } catch {}
  return true
}

export function revokeAccess() {
  try {
    sessionStorage.removeItem(ACCESS_KEY)
  } catch {}
}
