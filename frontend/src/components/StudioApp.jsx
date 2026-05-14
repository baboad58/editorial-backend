import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useBookSession } from '../hooks/useBookSession'
import { markInviteUsed } from '../lib/invites'
import AgentSidebar from './AgentSidebar'
import ChatPanel from './ChatPanel'
import StartScreen from './StartScreen'

const API_BASE = import.meta.env.VITE_API_URL || ''

function useBackendHealth() {
  const [status, setStatus] = useState('checking') // 'checking' | 'online' | 'offline'

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      try {
        const ctrl = new AbortController()
        const timer = setTimeout(() => ctrl.abort(), 4000)
        const res = await fetch(`${API_BASE}/api/biblioteca`, { signal: ctrl.signal })
        clearTimeout(timer)
        if (cancelled) return
        setStatus(res.ok ? 'online' : 'offline')
      } catch {
        if (!cancelled) setStatus('offline')
      }
    }
    check()
    const interval = setInterval(check, 30000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  return status
}

export default function StudioApp() {
  const backendStatus = useBackendHealth()
  const navigate = useNavigate()
  const {
    phase,
    sessionId,
    sessionToken,
    currentInterrupt,
    agentStatus,
    messages,
    result,
    errorMsg,
    reconnecting,
    startSession,
    sendResponse,
    reset,
  } = useBookSession()

  // Marcar invitación como usada al cerrar/recargar la ventana
  useEffect(() => {
    const handleUnload = () => markInviteUsed(true)   // true = sendBeacon
    window.addEventListener('beforeunload', handleUnload)
    return () => window.removeEventListener('beforeunload', handleUnload)
  }, [])

  // Wrapper de reset: marcar invite + redirigir al gate para pedir nuevo código
  const handleReset = () => {
    reset()              // internamente llama markInviteUsed + clearStoredInvite
    navigate('/acceso', { replace: true })
  }

  const showStart = phase === 'idle' || phase === 'error'
  const showRecoverableBanner = phase === 'error_recoverable'

  return (
    <div className="h-screen flex overflow-hidden bg-gray-950">
      {!showStart && (
        <AgentSidebar
          agentStatus={agentStatus}
          phase={phase}
          messages={messages}
        />
      )}

      <main className="flex-1 flex flex-col min-w-0 border-l border-white/5">
        {backendStatus === 'offline' && (
          <div className="bg-amber-900/40 border-b border-amber-500/40 px-6 py-3 text-sm text-amber-200 flex items-start gap-3 flex-shrink-0">
            <span className="text-lg leading-none">⚠️</span>
            <div className="flex-1">
              <p className="font-semibold">Modo demostración — backend no disponible</p>
              <p className="text-xs text-amber-300/80 mt-0.5">
                El servidor de los agentes (FastAPI) no está activo. La interfaz funciona, pero no se podrá generar un libro real hasta que se despliegue el backend.
              </p>
            </div>
          </div>
        )}
        {!showStart && (
          <header className="flex items-center justify-between px-6 py-3 border-b border-white/10 flex-shrink-0">
            <div className="flex items-center gap-3">
              <Link
                to="/"
                className="font-serif text-sm text-gray-500 hover:text-gray-300 transition-colors"
                title="Volver a la portada"
              >
                ← Obra
              </Link>
              <h2 className="text-sm font-semibold text-gray-300">
                {result?.title || 'Nuevo libro en proceso…'}
              </h2>
              {sessionId && (
                <span className="text-xs text-gray-600 font-mono hidden sm:block">
                  #{sessionId.slice(0, 8)}
                </span>
              )}
            </div>
            <button
              onClick={handleReset}
              className="text-xs text-gray-600 hover:text-gray-400 transition-colors px-3 py-1 rounded-lg glass glass-hover"
            >
              ✕ Nuevo libro
            </button>
          </header>
        )}

        {reconnecting && !showStart && (
          <div className="mx-4 mt-4 bg-blue-900/20 border border-blue-500/20 rounded-xl px-4 py-2 text-sm text-blue-300 flex items-center gap-2 flex-shrink-0">
            <span className="animate-pulse">⟳</span>
            <span>Reconectando automáticamente…</span>
          </div>
        )}

        {showRecoverableBanner && (
          <div className="mx-4 mt-4 bg-yellow-900/30 border border-yellow-500/30 rounded-xl px-4 py-3 text-sm text-yellow-300 flex items-center justify-between flex-shrink-0">
            <span>⚠️ {errorMsg}</span>
            <button
              onClick={() => {
                const saved = JSON.parse(localStorage.getItem('bookSession') || '{}')
                startSession(saved.idea || '', sessionId, sessionToken || saved.sessionToken)
              }}
              className="ml-4 px-3 py-1 rounded-lg bg-yellow-700/40 hover:bg-yellow-600/40 text-yellow-200 text-xs font-medium transition-colors"
            >
              ↩ Reconectar
            </button>
          </div>
        )}

        {showStart ? (
          <>
            {errorMsg && (
              <div className="mx-auto mt-6 max-w-xl w-full px-4">
                <div className="bg-red-900/30 border border-red-500/30 rounded-xl px-4 py-3 text-sm text-red-300">
                  <p className="mb-3">❌ {errorMsg}</p>
                  <div className="flex gap-2 flex-wrap">
                    {sessionId && (
                      <button
                        onClick={() => {
                          const saved = JSON.parse(localStorage.getItem('bookSession') || '{}')
                          startSession(saved.idea || '', sessionId, sessionToken || saved.sessionToken)
                        }}
                        className="px-3 py-1.5 rounded-lg bg-blue-700/40 hover:bg-blue-600/40 text-blue-200 text-xs font-medium transition-colors"
                      >
                        ↩ Reconectar sesión guardada
                      </button>
                    )}
                    <button
                      onClick={handleReset}
                      className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 text-xs font-medium transition-colors"
                    >
                      ✕ Nuevo libro
                    </button>
                  </div>
                </div>
              </div>
            )}
            <StartScreen onStart={startSession} phase={phase} />
          </>
        ) : (
          <ChatPanel
            messages={messages}
            currentInterrupt={currentInterrupt}
            phase={phase}
            onSend={sendResponse}
            result={result}
            onReset={handleReset}
          />
        )}
      </main>
    </div>
  )
}
