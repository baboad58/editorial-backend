/**
 * Left sidebar: agent pipeline + Biblioteca button.
 */

import { useState, useEffect } from 'react'

const AGENTS = [
  { id: 'Arquitecto', emoji: '🏛️', label: 'Arquitecto', desc: 'Plan maestro' },
  { id: 'Escritor',   emoji: '✍️',  label: 'Escritor',   desc: 'Redacta capítulos' },
  { id: 'Editor',     emoji: '🔍',  label: 'Editor',     desc: 'Crítica editorial' },
  { id: 'Maquetador', emoji: '📐',  label: 'Maquetador', desc: 'Formato y diseño' },
  { id: 'Publicador', emoji: '🚀',  label: 'Publicador', desc: 'Cierre y portada' },
]

const API_BASE = import.meta.env.VITE_API_URL || ''

export default function AgentSidebar({ agentStatus, phase, messages }) {
  const activeAgent = agentStatus?.agent
  const [showBiblioteca, setShowBiblioteca] = useState(false)
  const [books, setBooks] = useState([])
  const [loadingBooks, setLoadingBooks] = useState(false)

  const usedAgents = new Set(
    messages
      .filter(m => m.role === 'agent' || m.role === 'system')
      .map(m => m.agent)
  )

  const openBiblioteca = async () => {
    setShowBiblioteca(true)
    setLoadingBooks(true)
    try {
      const res = await fetch(`${API_BASE}/api/biblioteca`)
      const data = await res.json()
      setBooks(data.books || [])
    } catch {
      setBooks([])
    } finally {
      setLoadingBooks(false)
    }
  }

  return (
    <aside className="w-64 flex-shrink-0 flex flex-col gap-3 py-6 px-4">
      {/* Logo */}
      <div className="mb-4">
        <h1 className="text-xl font-bold text-brand-500">📚 Book Factory</h1>
        <p className="text-xs text-gray-500 mt-0.5">Sistema Editorial con IA</p>
      </div>

      {/* Agent list */}
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider px-1">Agentes</p>
      {AGENTS.map(agent => {
        const isActive = activeAgent === agent.id
        const isDone = !isActive && usedAgents.has(agent.id)
        return (
          <div
            key={agent.id}
            className={`
              glass rounded-xl p-3 transition-all duration-300
              ${isActive ? 'border-brand-500/50 bg-brand-900/20 shadow-lg shadow-brand-900/20' : ''}
              ${isDone && !isActive ? 'opacity-60' : ''}
            `}
          >
            <div className="flex items-center gap-2">
              <span className="text-xl">{agent.emoji}</span>
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-semibold ${isActive ? 'text-brand-400' : 'text-gray-300'}`}>
                  {agent.label}
                </p>
                <p className="text-xs text-gray-500 truncate">{agent.desc}</p>
              </div>
              {isActive && (
                <span className="w-2 h-2 rounded-full bg-brand-500 animate-pulse flex-shrink-0" />
              )}
              {isDone && !isActive && (
                <span className="text-green-500 text-sm flex-shrink-0">✓</span>
              )}
            </div>
            {isActive && agentStatus?.status === 'waiting' && (
              <p className="text-xs text-brand-400/80 mt-1.5 pl-7">Esperando tu respuesta…</p>
            )}
            {isActive && agentStatus?.status === 'working' && (
              <p className="text-xs text-yellow-400/80 mt-1.5 pl-7">Procesando…</p>
            )}
          </div>
        )
      })}

      {/* Biblioteca button */}
      <button
        onClick={openBiblioteca}
        className="mt-2 flex items-center gap-2 px-3 py-2.5 rounded-xl glass glass-hover
                   text-sm text-gray-300 hover:text-white transition-colors border border-white/10"
      >
        <span className="text-lg">📖</span>
        <span className="font-medium">Biblioteca</span>
      </button>

      {/* Phase indicator */}
      <div className="mt-auto glass rounded-xl p-3">
        <p className="text-xs text-gray-500 mb-1">Estado</p>
        <PhaseIndicator phase={phase} />
      </div>

      {/* Biblioteca modal */}
      {showBiblioteca && (
        <BibliotecaModal
          books={books}
          loading={loadingBooks}
          onClose={() => setShowBiblioteca(false)}
        />
      )}
    </aside>
  )
}

function BibliotecaModal({ books, loading, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-gray-900 border border-white/10 rounded-2xl w-full max-w-lg mx-4 shadow-2xl flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
          <div className="flex items-center gap-2">
            <span className="text-xl">📖</span>
            <h2 className="text-base font-semibold text-white">Biblioteca</h2>
            {!loading && (
              <span className="text-xs text-gray-500 ml-1">{books.length} libro{books.length !== 1 ? 's' : ''}</span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors text-lg leading-none"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
              <span className="animate-pulse">Cargando libros…</span>
            </div>
          ) : books.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-gray-500 text-sm gap-2">
              <span className="text-3xl">📭</span>
              <p>La biblioteca está vacía.</p>
              <p className="text-xs text-gray-600">Los libros aparecerán aquí al completarse.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {books.map((book, i) => (
                <BookEntry key={i} book={book} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function BookEntry({ book }) {
  const API_BASE = import.meta.env.VITE_API_URL || ''
  const downloadUrl = `${API_BASE}/api/biblioteca/${book.rel_path}`

  return (
    <div className="glass rounded-xl px-4 py-3 flex items-center gap-3">
      <span className="text-2xl flex-shrink-0">📗</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white truncate">{book.title}</p>
        <p className="text-xs text-gray-500">{book.date} · {book.size_kb} KB</p>
      </div>
      <a
        href={downloadUrl}
        download={book.name}
        className="flex-shrink-0 px-3 py-1.5 rounded-lg bg-brand-700/60 hover:bg-brand-600/60
                   text-brand-200 text-xs font-medium transition-colors"
      >
        ⬇ Descargar
      </a>
    </div>
  )
}

function PhaseIndicator({ phase }) {
  const map = {
    idle:              { label: 'Esperando',     color: 'text-gray-400' },
    connecting:        { label: 'Conectando…',   color: 'text-yellow-400' },
    active:            { label: 'En progreso',   color: 'text-brand-400' },
    complete:          { label: '✅ Completado',  color: 'text-green-400' },
    error:             { label: '❌ Error',       color: 'text-red-400' },
    error_recoverable: { label: '⚠️ Pausado',     color: 'text-yellow-400' },
  }
  const { label, color } = map[phase] || map.idle
  return <p className={`text-sm font-medium ${color}`}>{label}</p>
}
