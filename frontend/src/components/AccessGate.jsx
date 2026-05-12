import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { verifyInvite } from '../lib/invites'

export default function AccessGate() {
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    const result = await verifyInvite(code)
    setLoading(false)
    if (result.ok) {
      navigate('/studio', { replace: true })
    } else {
      setError(result.error)
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-stone-100 font-sans flex items-center justify-center px-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-12">
          <Link to="/" className="inline-block font-serif text-3xl tracking-wide mb-8">
            O<span className="text-gold-500">b</span>ra
          </Link>
          <p className="text-xs tracking-[0.4em] uppercase text-gold-500/70 mb-4">
            Acceso al estudio
          </p>
          <h1 className="font-serif text-3xl md:text-4xl leading-tight">
            Introduce tu <span className="italic text-gold-400">código de invitación</span>
          </h1>
          <p className="mt-6 text-sm text-stone-400 leading-relaxed">
            El estudio está en beta cerrada. Si recibiste un código, úsalo para entrar.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-xs tracking-[0.2em] uppercase text-stone-500 mb-3">
              Código
            </label>
            <input
              type="text"
              autoFocus
              value={code}
              onChange={(e) => { setCode(e.target.value); setError('') }}
              maxLength={64}
              placeholder="OBRA-ALPHA-XXX"
              className="w-full bg-transparent border border-white/15 focus:border-gold-500 rounded-xl
                         outline-none px-4 py-3 text-stone-100 placeholder-stone-700
                         font-mono tracking-wider uppercase transition-colors text-center"
            />
            {error && <p className="text-xs text-red-400 mt-3 text-center">{error}</p>}
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-gold-500 hover:bg-gold-400 disabled:opacity-60 disabled:cursor-not-allowed
                       text-[#0a0a0f] px-8 py-4 rounded-full font-medium tracking-wide
                       shadow-[0_10px_40px_-10px_rgba(212,168,87,0.6)] transition-all hover:scale-[1.01]"
          >
            {loading ? 'Verificando…' : 'Entrar al estudio →'}
          </button>
        </form>

        <div className="mt-10 text-center space-y-3">
          <p className="text-sm text-stone-500">
            ¿No tienes código?{' '}
            <Link to="/#contacto" className="text-gold-400 hover:text-gold-300 underline underline-offset-4">
              Solicítalo aquí
            </Link>
          </p>
          <Link to="/" className="inline-block text-xs text-stone-600 hover:text-stone-400 transition-colors">
            ← Volver a la portada
          </Link>
        </div>
      </div>
    </div>
  )
}
