/**
 * Pantalla de inicio: idea del libro + imagen de referencia + Biblioteca.
 */

import { useState, useEffect, useRef } from 'react'

const LS_KEY   = 'bookSession'
const API_BASE = import.meta.env.VITE_API_URL || ''

const EXAMPLES = [
  'Una guía práctica para emprender tu primer negocio digital desde cero',
  'Una novela de thriller psicológico sobre un detective que resuelve crímenes en Buenos Aires',
  'Un libro de autoayuda sobre hábitos de productividad para padres ocupados',
]

export default function StartScreen({ onStart, phase }) {
  const [idea, setIdea]             = useState('')
  const [savedSession, setSavedSession] = useState(null)
  const [refImage, setRefImage]     = useState(null)
  const [uploadState, setUploadState] = useState('idle')
  const [uploadError, setUploadError] = useState('')
  const fileInputRef                = useRef(null)
  const [showBiblioteca, setShowBiblioteca] = useState(false)
  const [showGithub, setShowGithub] = useState(false)

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(LS_KEY) || 'null')
      if (saved?.sessionId) setSavedSession(saved)
    } catch {}
  }, [])

  const handleSubmit = (e) => {
    e.preventDefault()
    const val = idea.trim()
    if (val) onStart(val, null, refImage?.serverPath || '')
  }

  const handleReconnect = () => {
    if (savedSession) onStart(savedSession.idea || '', savedSession.sessionId, refImage?.serverPath || '')
  }

  const handleDismissSaved = () => {
    localStorage.removeItem(LS_KEY)
    setSavedSession(null)
  }

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const preview = URL.createObjectURL(file)
    setRefImage({ preview, serverPath: '' })
    setUploadState('uploading')
    setUploadError('')
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${API_BASE}/api/upload-reference`, { method: 'POST', body: form })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Error desconocido' }))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }
      const { reference_image_path } = await res.json()
      setRefImage({ preview, serverPath: reference_image_path })
      setUploadState('done')
    } catch (err) {
      setUploadState('error')
      setUploadError(err.message)
      setRefImage(null)
      URL.revokeObjectURL(preview)
    }
    e.target.value = ''
  }

  const handleRemoveImage = () => {
    if (refImage?.preview) URL.revokeObjectURL(refImage.preview)
    setRefImage(null)
    setUploadState('idle')
    setUploadError('')
  }

  const isLoading = phase === 'connecting'

  return (
    <div className="flex-1 flex items-center justify-center px-8 py-8 overflow-y-auto">
      <div className="w-full max-w-xl">

        {/* Hero */}
        <div className="text-center mb-10">
          <div className="text-6xl mb-4">📚</div>
          <h1 className="text-4xl font-bold text-white mb-3">Book Factory</h1>
          <p className="text-gray-400 leading-relaxed">
            Un equipo de 5 agentes de IA transformará tu idea en un libro completo,
            editado y maquetado — listo para publicar.
          </p>
        </div>

        {/* Reconnect banner */}
        {savedSession && (
          <div className="mb-6 bg-blue-900/30 border border-blue-500/30 rounded-2xl px-5 py-4">
            <p className="text-sm text-blue-300 font-semibold mb-1">📂 Sesión anterior guardada</p>
            {savedSession.idea && (
              <p className="text-xs text-gray-400 mb-3 line-clamp-2">"{savedSession.idea}"</p>
            )}
            <div className="flex gap-2">
              <button
                onClick={handleReconnect}
                disabled={isLoading}
                className="flex-1 py-2 rounded-xl text-sm font-medium bg-blue-700/60 hover:bg-blue-600/60
                           text-blue-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                ↩ Reconectar libro anterior
              </button>
              <button
                onClick={handleDismissSaved}
                disabled={isLoading}
                className="px-3 py-2 rounded-xl text-xs text-gray-500 hover:text-gray-400 glass glass-hover transition-colors"
              >
                Descartar
              </button>
            </div>
          </div>
        )}

        {/* Input form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              ¿Cuál es la idea para tu libro?
            </label>
            <textarea
              rows={4}
              value={idea}
              onChange={e => setIdea(e.target.value)}
              placeholder="Describe tu idea aquí… puede ser solo un título, un concepto, o varios párrafos."
              disabled={isLoading}
              className="w-full resize-none rounded-2xl px-5 py-4 glass text-gray-100 text-sm
                         placeholder-gray-600 focus:outline-none focus:border-brand-500/50
                         transition-colors duration-150 border border-white/10"
            />
          </div>

          {/* Reference image */}
          <div className="rounded-2xl glass border border-white/10 px-5 py-4">
            <p className="text-sm font-medium text-gray-400 mb-1">
              🖼️ Imagen de referencia visual <span className="text-gray-600 font-normal">(opcional)</span>
            </p>
            <p className="text-xs text-gray-600 mb-3">
              Guía de estilo para la portada e ilustraciones de capítulos.
            </p>
            {refImage ? (
              <div className="flex items-center gap-3">
                <img src={refImage.preview} alt="Referencia" className="w-16 h-16 object-cover rounded-xl border border-white/10 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  {uploadState === 'uploading' && <p className="text-xs text-blue-400 animate-pulse">⟳ Subiendo…</p>}
                  {uploadState === 'done' && <p className="text-xs text-green-400">✓ Lista para usar</p>}
                </div>
                <button type="button" onClick={handleRemoveImage} disabled={isLoading}
                  className="text-xs text-gray-500 hover:text-red-400 transition-colors px-2 py-1 rounded-lg glass">
                  Quitar
                </button>
              </div>
            ) : (
              <button type="button" onClick={() => fileInputRef.current?.click()}
                disabled={isLoading || uploadState === 'uploading'}
                className="w-full py-2.5 rounded-xl text-sm text-gray-400 border border-dashed border-white/20
                           hover:border-white/40 hover:text-gray-300 transition-colors">
                + Subir imagen (JPG, PNG, WebP · máx. 10 MB)
              </button>
            )}
            {uploadState === 'error' && <p className="mt-2 text-xs text-red-400">⚠️ {uploadError}</p>}
            <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp"
              className="hidden" onChange={handleFileChange} />
          </div>

          <button
            type="submit"
            disabled={!idea.trim() || isLoading || uploadState === 'uploading'}
            className="w-full py-3.5 rounded-2xl font-semibold text-sm transition-all duration-150
                       bg-brand-600 hover:bg-brand-500 text-white shadow-xl shadow-brand-900/40
                       disabled:bg-white/5 disabled:text-gray-600 disabled:cursor-not-allowed"
          >
            {isLoading ? '⏳ Conectando con los agentes…' : '🚀 Crear mi libro'}
          </button>
        </form>

        {/* Aviso de privacidad — Ley 19.628 / Ley 21.719 Chile */}
        <p className="mt-4 text-[11px] text-gray-600 text-center leading-relaxed px-2">
          Al crear tu libro aceptas que recopilemos tu nombre, correo y datos de autor para
          generar la obra. Esta información se procesa mediante IA (Anthropic) y se almacena
          por un máximo de 30 días. Puedes solicitar su eliminación en cualquier momento.
          Tratamiento conforme a la Ley 19.628 de Protección de la Vida Privada (Chile).
        </p>

        {/* Biblioteca */}
        <button
          onClick={() => setShowBiblioteca(true)}
          className="mt-4 w-full flex items-center justify-center gap-2 py-3 rounded-2xl
                     glass border border-white/10 glass-hover text-gray-300 hover:text-white
                     text-sm font-medium transition-colors"
        >
          📖 Ver mi Biblioteca
        </button>

        <button
          onClick={() => setShowGithub(true)}
          className="mt-2 w-full flex items-center justify-center gap-2 py-3 rounded-2xl
                     glass border border-white/10 glass-hover text-gray-300 hover:text-white
                     text-sm font-medium transition-colors"
        >
          🐙 Repos de GitHub (baboad58/editorial-frontend)
        </button>

        {/* Examples */}
        <div className="mt-8">
          <p className="text-xs text-gray-600 text-center mb-3">O prueba con estos ejemplos</p>
          <div className="space-y-2">
            {EXAMPLES.map((ex, i) => (
              <button key={i} onClick={() => setIdea(ex)} disabled={isLoading}
                className="w-full text-left text-xs text-gray-500 glass rounded-xl px-4 py-2.5 glass-hover transition-colors">
                {ex}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Modal Biblioteca */}
      {showBiblioteca && (
        <BibliotecaModal onClose={() => setShowBiblioteca(false)} />
      )}

      {showGithub && (
        <GithubReposModal owner="baboad58" onClose={() => setShowGithub(false)} />
      )}
    </div>
  )
}

function BibliotecaModal({ onClose }) {
  const [books, setBooks] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API_BASE}/api/biblioteca`)
      .then(r => r.json())
      .then(data => setBooks(data.books || []))
      .catch(() => setBooks([]))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-gray-900 border border-white/10 rounded-2xl w-full max-w-lg mx-4 shadow-2xl flex flex-col max-h-[80vh]">
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
          <div className="flex items-center gap-2">
            <span className="text-xl">📖</span>
            <h2 className="text-base font-semibold text-white">Mi Biblioteca</h2>
            {!loading && (
              <span className="text-xs text-gray-500 ml-1">{books.length} libro{books.length !== 1 ? 's' : ''}</span>
            )}
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors text-lg leading-none">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
              <span className="animate-pulse">Cargando libros…</span>
            </div>
          ) : books.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-gray-500 text-sm gap-2">
              <span className="text-3xl">📭</span>
              <p>La biblioteca está vacía.</p>
              <p className="text-xs text-gray-600">Los libros completados aparecerán aquí.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {books.map((book, i) => (
                <div key={i} className="glass rounded-xl px-4 py-3 flex items-center gap-3">
                  <span className="text-2xl flex-shrink-0">📗</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">{book.title}</p>
                    <p className="text-xs text-gray-500">{book.date} · {book.size_kb} KB</p>
                  </div>
                  <a
                    href={`${API_BASE}/api/biblioteca/${book.rel_path}`}
                    download={book.name}
                    className="flex-shrink-0 px-3 py-1.5 rounded-lg bg-brand-700/60 hover:bg-brand-600/60
                               text-brand-200 text-xs font-medium transition-colors"
                  >
                    ⬇ Descargar
                  </a>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function GithubReposModal({ owner, onClose }) {
  const [repos, setRepos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch(`https://api.github.com/users/${owner}/repos?per_page=100&sort=updated`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => setRepos(Array.isArray(data) ? data : []))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [owner])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-gray-900 border border-white/10 rounded-2xl w-full max-w-2xl mx-4 shadow-2xl flex flex-col max-h-[80vh]">
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
          <div className="flex items-center gap-2">
            <span className="text-xl">🐙</span>
            <h2 className="text-base font-semibold text-white">Repos de @{owner}</h2>
            {!loading && !error && (
              <span className="text-xs text-gray-500 ml-1">{repos.length}</span>
            )}
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors text-lg leading-none">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
              <span className="animate-pulse">Cargando…</span>
            </div>
          ) : error ? (
            <div className="text-red-400 text-sm py-8 text-center">⚠️ {error}</div>
          ) : repos.length === 0 ? (
            <div className="text-gray-500 text-sm py-8 text-center">Sin repos públicos.</div>
          ) : (
            <div className="space-y-2">
              {repos.map(repo => (
                <a
                  key={repo.id}
                  href={repo.html_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block glass rounded-xl px-4 py-3 glass-hover transition-colors"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-white truncate">
                        {repo.name}
                        {repo.private && <span className="ml-2 text-[10px] text-yellow-400">PRIVATE</span>}
                        {repo.fork && <span className="ml-2 text-[10px] text-gray-500">fork</span>}
                      </p>
                      {repo.description && (
                        <p className="text-xs text-gray-400 mt-1 line-clamp-2">{repo.description}</p>
                      )}
                      <div className="flex items-center gap-3 mt-2 text-[11px] text-gray-500">
                        {repo.language && <span>● {repo.language}</span>}
                        <span>★ {repo.stargazers_count}</span>
                        <span>⑂ {repo.forks_count}</span>
                        <span className="truncate">↻ {new Date(repo.updated_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  </div>
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
