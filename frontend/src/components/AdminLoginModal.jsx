import { useEffect, useState } from 'react'
import { adminLogin } from '../lib/admin'

export default function AdminLoginModal({ open, onClose, onSuccess }) {
  const [codigo, setCodigo] = useState('')
  const [pass, setPass] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (open) { setCodigo(''); setPass(''); setErr(''); setSubmitting(false) }
  }, [open])

  if (!open) return null

  async function onSubmit(e) {
    e.preventDefault()
    setErr(''); setSubmitting(true)
    try {
      await adminLogin(codigo.trim(), pass)
      onSuccess?.()
    } catch (e2) {
      setErr(e2?.message || 'Credenciales inválidas')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-6"
      onClick={onClose}
    >
      <form
        onClick={e => e.stopPropagation()}
        onSubmit={onSubmit}
        className="w-full max-w-sm bg-[#0a0a0f] border border-white/10 rounded-2xl p-8 space-y-5 shadow-2xl"
      >
        <div className="text-center space-y-1">
          <p className="font-serif text-2xl">O<span className="text-gold-500">b</span>ra</p>
          <p className="text-xs tracking-[0.25em] uppercase text-stone-500">Acceso interno</p>
        </div>

        <label className="block">
          <span className="block text-xs tracking-[0.2em] uppercase text-stone-500 mb-2">Código de usuario</span>
          <input
            autoFocus
            value={codigo}
            onChange={e => setCodigo(e.target.value)}
            disabled={submitting}
            maxLength={100}
            className="w-full bg-transparent border border-white/10 focus:border-gold-500 rounded-xl outline-none p-3 text-stone-100 transition-colors disabled:opacity-50"
          />
        </label>

        <label className="block">
          <span className="block text-xs tracking-[0.2em] uppercase text-stone-500 mb-2">Contraseña</span>
          <input
            type="password"
            value={pass}
            onChange={e => setPass(e.target.value)}
            disabled={submitting}
            maxLength={200}
            className="w-full bg-transparent border border-white/10 focus:border-gold-500 rounded-xl outline-none p-3 text-stone-100 transition-colors disabled:opacity-50"
          />
        </label>

        {err && <p className="text-sm text-red-400 text-center">{err}</p>}

        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="flex-1 px-4 py-3 rounded-full border border-white/10 text-stone-400 hover:text-stone-100 hover:border-white/20 transition-colors disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={submitting || !codigo || !pass}
            className="flex-1 bg-gold-500 hover:bg-gold-400 text-[#0a0a0f] px-4 py-3 rounded-full font-medium transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {submitting ? 'Entrando…' : 'Entrar'}
          </button>
        </div>
      </form>
    </div>
  )
}
