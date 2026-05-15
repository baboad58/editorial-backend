import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  adminFetchData,
  adminAssignCode,
  adminGenerateCodes,
  adminLogout,
  getAdminToken,
  getAdminUser,
} from '../lib/admin'
import { buildAssignmentEmail } from '../lib/emailTemplate'

function fmtDate(s) {
  if (!s) return '—'
  try { return new Date(s).toLocaleString('es-CL', { dateStyle: 'short', timeStyle: 'short' }) }
  catch { return s }
}

export default function AdminConsole() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [submissions, setSubmissions] = useState([])
  const [codes, setCodes] = useState([])
  const [me, setMe] = useState(null)
  const [openIdea, setOpenIdea] = useState(null)
  const [picker, setPicker] = useState(null) // submission seleccionada
  const [emailPreview, setEmailPreview] = useState(null) // { submission, code }
  const [assigning, setAssigning] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [toast, setToast] = useState(null)

  useEffect(() => {
    if (!getAdminToken()) { navigate('/', { replace: true }); return }
    refresh()
  }, [])

  async function refresh() {
    setLoading(true); setError('')
    try {
      const data = await adminFetchData()
      setSubmissions(data.submissions || [])
      setCodes(data.codes || [])
      setMe(data.me || { codigo_usuario: getAdminUser() })
    } catch (e) {
      if (e.status === 401) {
        adminLogout(); navigate('/', { replace: true }); return
      }
      setError(e.message || 'Error cargando datos')
    } finally {
      setLoading(false)
    }
  }

  const codeStatus = (c) => c.estado ?? c.status ?? ''
  const isAvailable = (c) => codeStatus(c).toLowerCase() === 'available'
  const isAssigned  = (c) => ['assigned', 'asignado', 'sent'].includes(codeStatus(c).toLowerCase())
  const isUsed      = (c) => ['used', 'usado'].includes(codeStatus(c).toLowerCase())

  const availableCodes = useMemo(() => codes.filter(isAvailable), [codes])
  const assignedCodes  = useMemo(() => codes.filter(isAssigned),  [codes])
  const usedCodes      = useMemo(() => codes.filter(isUsed),      [codes])

  function statusBadge(s) {
    const v = (s ?? '').toLowerCase()
    let dot = 'bg-rose-400', txt = 'text-rose-300', label = s ?? '—'
    if (v === 'available')                              { dot = 'bg-emerald-400'; txt = 'text-emerald-300'; label = 'Disponible' }
    else if (['assigned','asignado','sent'].includes(v)){ dot = 'bg-amber-400';   txt = 'text-amber-300';   label = 'Asignado' }
    else if (['used','usado'].includes(v))              { dot = 'bg-stone-500';   txt = 'text-stone-400';   label = 'Usado' }
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px]">
        <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
        <span className={txt}>{label}</span>
      </span>
    )
  }

  async function doAssign(code_id) {
    if (!picker) return
    setAssigning(true)
    try {
      const res = await adminAssignCode(picker.id, code_id)
      setPicker(null)
      const reasonMap = {
        missing_resend_api_key: 'falta configurar RESEND_API_KEY en el servidor',
        missing_recipient: 'la solicitud no tiene email destinatario',
        missing_code: 'el código asignado no tiene valor',
        invalid_recipient: 'el email del destinatario no es válido',
        resend_client_error: `Resend rechazó el envío (${res.email_error_status ?? '4xx'})`,
        resend_server_error: `Resend tuvo un error de servidor (${res.email_error_status ?? '5xx'})`,
        resend_unknown_error: 'Resend devolvió un estado inesperado',
        network_error: 'no se pudo conectar con Resend',
      }
      if (res.email_sent) {
        setToast({ kind: 'ok', text: `Código asignado: ${res.code ?? '✓'} · correo enviado` })
      } else {
        const why = reasonMap[res.email_error_reason] || res.email_error || 'motivo desconocido'
        setToast({ kind: 'err', text: `Código asignado: ${res.code ?? '✓'} · correo NO enviado (${why})` })
      }
      await refresh()
    } catch (e) {
      setToast({ kind: 'err', text: e.message || 'Error al asignar' })
    } finally {
      setAssigning(false)
      setTimeout(() => setToast(null), 4500)
    }
  }

  async function logout() {
    await adminLogout()
    navigate('/', { replace: true })
  }

  async function doGenerate() {
    if (generating) return
    setGenerating(true)
    try {
      const res = await adminGenerateCodes(10)
      setToast({ kind: 'ok', text: `Generados ${res.count} códigos` })
      await refresh()
    } catch (e) {
      setToast({ kind: 'err', text: e.message || 'Error al generar códigos' })
    } finally {
      setGenerating(false)
      setTimeout(() => setToast(null), 4500)
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-stone-100">
      <header className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <p className="font-serif text-xl">O<span className="text-gold-500">b</span>ra</p>
          <span className="text-xs tracking-[0.2em] uppercase text-stone-500">Consola</span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-stone-400">
            {me?.codigo_usuario ?? '—'}
            <span className="mx-2 text-stone-700">·</span>
            <span className="text-emerald-300">{availableCodes.length} disponibles</span>
            <span className="mx-2 text-stone-700">·</span>
            <span className="text-amber-300">{assignedCodes.length} asignados</span>
            <span className="mx-2 text-stone-700">·</span>
            <span className="text-stone-400">{usedCodes.length} usados</span>
          </span>
          <button
            onClick={refresh}
            className="px-3 py-1.5 rounded-full border border-white/10 hover:border-white/30 text-stone-300 transition-colors"
          >
            Refrescar
          </button>
          <button
            onClick={doGenerate}
            disabled={generating}
            className="px-3 py-1.5 rounded-full bg-gold-500 hover:bg-gold-400 text-[#0a0a0f] font-medium text-xs disabled:opacity-50"
          >
            {generating ? 'Generando…' : 'Generar 10 códigos'}
          </button>
          <button
            onClick={logout}
            className="px-3 py-1.5 rounded-full border border-white/10 hover:border-white/30 text-stone-300 transition-colors"
          >
            Salir
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <h1 className="font-serif text-3xl mb-2">Solicitudes de invitación</h1>
        <p className="text-xs text-stone-500 mb-6 max-w-2xl">
          <span className="text-emerald-300">Disponible</span>: listo para asignar ·{' '}
          <span className="text-amber-300">Asignado</span>: ya entregado a un solicitante, pendiente de canje ·{' '}
          <span className="text-stone-400">Usado</span>: el invitado lo canjeó al registrarse en Obra (lo marca el flujo de registro, no esta consola).
        </p>

        {loading && <p className="text-stone-500">Cargando…</p>}
        {error && <p className="text-red-400">{error}</p>}

        {!loading && !error && (
          <div className="border border-white/10 rounded-2xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-white/5 text-stone-400 text-xs uppercase tracking-wider">
                <tr>
                  <th className="text-left px-4 py-3">Fecha</th>
                  <th className="text-left px-4 py-3">Nombre</th>
                  <th className="text-left px-4 py-3">Email</th>
                  <th className="text-left px-4 py-3">Idea</th>
                  <th className="text-left px-4 py-3">Estado</th>
                  <th className="text-right px-4 py-3">Acción</th>
                </tr>
              </thead>
              <tbody>
                {submissions.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-stone-500">Sin solicitudes</td></tr>
                )}
                {submissions.map(s => (
                  <tr key={s.id} className="border-t border-white/5 hover:bg-white/[0.02]">
                    <td className="px-4 py-3 text-stone-400 whitespace-nowrap">{fmtDate(s.created_at)}</td>
                    <td className="px-4 py-3">{s.name}</td>
                    <td className="px-4 py-3 text-stone-400">{s.email}</td>
                    <td className="px-4 py-3 max-w-md">
                      <span className="text-stone-300 line-clamp-2">{s.idea}</span>
                      <button
                        onClick={() => setOpenIdea(s)}
                        className="text-xs text-gold-400 hover:text-gold-300 mt-1"
                      >
                        ver completa
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      {s.status === 'asignado' ? (
                        <span className="inline-flex items-center gap-2 text-xs">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          <span className="text-emerald-300">Asignado</span>
                          {s.assigned_code && (
                            <span className="text-stone-500 font-mono">{s.assigned_code}</span>
                          )}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-2 text-xs">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                          <span className="text-amber-300">En espera</span>
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex items-center gap-2">
                        <button
                          onClick={() => setEmailPreview({ submission: s, code: s.codigo_asignado || 'OBRA-XXXX' })}
                          className="px-3 py-1.5 rounded-full border border-white/10 hover:border-white/30 text-stone-300 text-xs"
                          title="Ver cómo se vería el correo enviado"
                        >
                          Vista previa correo
                        </button>
                        {s.status !== 'asignado' && (
                          <button
                            onClick={() => setPicker(s)}
                            disabled={availableCodes.length === 0}
                            className="px-3 py-1.5 rounded-full bg-gold-500 hover:bg-gold-400 text-[#0a0a0f] font-medium text-xs disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            Asignar código
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {/* Modal idea */}
      {openIdea && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm p-6 flex items-center justify-center"
             onClick={() => setOpenIdea(null)}>
          <div onClick={e => e.stopPropagation()}
               className="max-w-2xl w-full bg-[#0a0a0f] border border-white/10 rounded-2xl p-6 space-y-3">
            <p className="text-xs tracking-[0.2em] uppercase text-stone-500">Solicitud de {openIdea.name}</p>
            <p className="text-stone-400 text-sm">{openIdea.email} · {fmtDate(openIdea.created_at)}</p>
            <div className="border-l-2 border-gold-500 pl-4 whitespace-pre-wrap text-stone-200 font-serif">
              {openIdea.idea}
            </div>
            <div className="text-right pt-2">
              <button onClick={() => setOpenIdea(null)}
                      className="px-4 py-2 rounded-full border border-white/10 hover:border-white/30 text-stone-300 text-sm">
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Picker código */}
      {picker && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm p-6 flex items-center justify-center"
             onClick={() => !assigning && setPicker(null)}>
          <div onClick={e => e.stopPropagation()}
               className="max-w-lg w-full bg-[#0a0a0f] border border-white/10 rounded-2xl p-6 space-y-4">
            <div>
              <p className="text-xs tracking-[0.2em] uppercase text-stone-500">Asignar código a</p>
              <p className="font-serif text-xl mt-1">{picker.name}</p>
              <p className="text-sm text-stone-400">{picker.email}</p>
            </div>
            <p className="text-xs text-stone-500">
              Sólo se listan códigos en estado <span className="text-emerald-300">Disponible</span>. Al asignar pasarán a <span className="text-amber-300">Asignado</span>.
            </p>
            <div className="max-h-80 overflow-y-auto border border-white/10 rounded-xl divide-y divide-white/5">
              {availableCodes.length === 0 && (
                <p className="p-4 text-stone-500 text-sm text-center">No hay códigos disponibles</p>
              )}
              {availableCodes.map(c => (
                <button
                  key={c.id}
                  onClick={() => doAssign(c.id)}
                  disabled={assigning}
                  className="w-full text-left px-4 py-3 hover:bg-white/5 flex items-center justify-between gap-3 disabled:opacity-50"
                >
                  <span className="flex items-center gap-3">
                    <span className="font-mono text-stone-100">{c.code}</span>
                    {statusBadge(c.estado ?? c.status)}
                  </span>
                  <span className="text-xs text-gold-400">Asignar →</span>
                </button>
              ))}
            </div>
            <div className="text-right">
              <button
                onClick={() => setPicker(null)}
                disabled={assigning}
                className="px-4 py-2 rounded-full border border-white/10 hover:border-white/30 text-stone-300 text-sm disabled:opacity-50"
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Vista previa correo */}
      {emailPreview && (() => {
        const mail = buildAssignmentEmail({
          name: emailPreview.submission.name ?? '',
          code: emailPreview.code ?? '',
          email: emailPreview.submission.email ?? '',
        })
        return (
          <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm p-6 flex items-center justify-center"
               onClick={() => setEmailPreview(null)}>
            <div onClick={e => e.stopPropagation()}
                 className="max-w-3xl w-full bg-[#0a0a0f] border border-white/10 rounded-2xl p-6 space-y-4 max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs tracking-[0.2em] uppercase text-stone-500">Vista previa correo</p>
                  <p className="font-serif text-xl mt-1">{emailPreview.submission.name}</p>
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-stone-500">Código:</label>
                  <input
                    value={emailPreview.code}
                    onChange={(e) => setEmailPreview({ ...emailPreview, code: e.target.value })}
                    className="bg-white/5 border border-white/10 rounded px-2 py-1 text-xs font-mono text-stone-100 w-32"
                  />
                </div>
              </div>

              <dl className="text-xs grid grid-cols-[80px_1fr] gap-y-1 gap-x-3 border border-white/10 rounded-xl p-3 bg-white/[0.02]">
                <dt className="text-stone-500">From</dt><dd className="text-stone-200 font-mono">{mail.from}</dd>
                <dt className="text-stone-500">To</dt><dd className="text-stone-200 font-mono">{emailPreview.submission.email}</dd>
                <dt className="text-stone-500">Subject</dt><dd className="text-stone-200">{mail.subject}</dd>
              </dl>

              <div>
                <p className="text-[11px] tracking-[0.2em] uppercase text-stone-500 mb-2">HTML renderizado</p>
                <iframe
                  title="Vista previa HTML"
                  srcDoc={mail.html}
                  sandbox=""
                  className="w-full h-[420px] bg-white rounded-xl border border-white/10"
                />
              </div>

              <div>
                <p className="text-[11px] tracking-[0.2em] uppercase text-stone-500 mb-2">Texto plano</p>
                <pre className="text-xs text-stone-300 whitespace-pre-wrap bg-white/[0.02] border border-white/10 rounded-xl p-3 font-mono">
{mail.text}
                </pre>
              </div>

              <div className="text-right">
                <button onClick={() => setEmailPreview(null)}
                        className="px-4 py-2 rounded-full border border-white/10 hover:border-white/30 text-stone-300 text-sm">
                  Cerrar
                </button>
              </div>
            </div>
          </div>
        )
      })()}


      {toast && (
        <div className={`fixed bottom-6 right-6 z-[60] px-4 py-3 rounded-xl border text-sm shadow-2xl ${
          toast.kind === 'ok'
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-200'
            : 'bg-red-500/10 border-red-500/30 text-red-200'
        }`}>
          {toast.text}
        </div>
      )}
    </div>
  )
}
