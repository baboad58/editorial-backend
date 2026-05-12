/**
 * Panel principal: historial de mensajes + interrupt activo + input/botones de respuesta.
 */

import { useEffect, useRef, useState } from 'react'
import { Send } from 'lucide-react'
import ChapterDraftView from './ChapterDraftView'
import PlanView from './PlanView'

const AGENT_COLORS = {
  Arquitecto: 'text-blue-400',
  Escritor:   'text-yellow-400',
  Editor:     'text-red-400',
  Maquetador: 'text-cyan-400',
  Publicador: 'text-purple-400',
  Sistema:    'text-gray-400',
  Tu:         'text-green-400',
}

const AGENT_EMOJIS = {
  Arquitecto: '🏛️',
  Escritor:   '✍️',
  Editor:     '🔍',
  Maquetador: '📐',
  Publicador: '🚀',
  Sistema:    '⚙️',
  Tu:         '👤',
}

// Mensajes técnicos del backend -> texto amigable para el usuario
function normalizeSystemMessage(content) {
  if (!content) return content
  const rules = [
    [/Reconectado al servidor\. Continuando\.\.\./i, '🔄 Reconectado. Continuando donde lo dejamos…'],
    [/Arquitecto.*trabajando/i,   '🏛️ El Arquitecto está diseñando el plan de tu libro…'],
    [/Escritor.*trabajando/i,     '✍️ El Escritor está redactando los capítulos…'],
    [/Editor.*trabajando/i,       '🔍 El Editor está revisando la calidad del texto…'],
    [/Maquetador.*trabajando/i,   '📐 El Maquetador está dando formato al libro…'],
    [/Publicador.*trabajando/i,   '🚀 El Publicador está preparando la versión final…'],
    [/Sistema.*trabajando/i,      '⚙️ Procesando…'],
    [/\*\*(\w+)\*\*\s*está trabajando/i, (_, agent) => `${AGENT_EMOJIS[agent] || '⚙️'} ${agent} está trabajando…`],
    [/esta trabajando/i,          '⚙️ Procesando…'],
  ]
  for (const [pattern, replacement] of rules) {
    if (typeof replacement === 'function') {
      const m = content.match(pattern)
      if (m) return replacement(...m)
    } else if (pattern.test(content)) {
      return replacement
    }
  }
  // Limpiar markdown bold residual
  return content.replace(/\*\*([^*]+)\*\*/g, '$1')
}

// Detecta si un interrupt tiene opciones de respuesta predefinidas (botones)
function getQuickOptions(interrupt) {
  if (!interrupt) return null
  const type = interrupt.interrupt_type
  const data = interrupt.data || {}

  if (type === 'plan_approval') {
    return [
      { label: '✅ Aprobar plan', value: 'aprobar', style: 'green' },
      { label: '✏️ Pedir cambios', value: '__custom__', style: 'yellow' },
    ]
  }
  if (type === 'interview_confirmation') {
    return [
      { label: '✅ Sí, confirmo', value: 'si', style: 'green' },
      { label: '✏️ Quiero corregir algo', value: '__custom__', style: 'yellow' },
    ]
  }
  if (type === 'review_mode') {
    return [
      { label: '✅ Sí, revisar capítulo a capítulo', value: 'si', style: 'green' },
      { label: '⚡ No, generación automática', value: 'no', style: 'blue' },
    ]
  }
  // Para la entrevista inicial y otros: sin botones, texto libre
  return null
}

const API_BASE = import.meta.env.VITE_API_URL || ''

export default function ChatPanel({ messages, currentInterrupt, phase, onSend, result, onReset }) {
  const [input, setInput] = useState('')
  const [customMode, setCustomMode] = useState(false)
  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, currentInterrupt])

  // Resetear modo custom cuando cambia el interrupt
  useEffect(() => {
    setCustomMode(false)
    setInput('')
    if (currentInterrupt && currentInterrupt.interrupt_type !== 'chapter_review') {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [currentInterrupt?.interrupt_type])

  const handleSend = (value) => {
    const val = (value ?? input).trim()
    if (!val || !currentInterrupt) return
    onSend(val)
    setInput('')
    setCustomMode(false)
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const isChapterReviewActive = currentInterrupt?.interrupt_type === 'chapter_review'
  const canInput = currentInterrupt && phase === 'active' && !isChapterReviewActive
  const quickOptions = getQuickOptions(currentInterrupt)
  const showButtons = canInput && quickOptions && !customMode
  const showTextInput = canInput && (!quickOptions || customMode)

  const lastChapterReviewIdx = messages.reduce(
    (last, msg, idx) => (msg.interrupt_type === 'chapter_review' ? idx : last), -1
  )

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <p className="text-gray-600 text-sm">Inicia un nuevo libro para comenzar.</p>
          </div>
        )}

        {messages.map((msg, idx) => {
          if (msg.role === 'agent' && msg.interrupt_type === 'chapter_review') {
            const isActive = isChapterReviewActive && idx === lastChapterReviewIdx
            return (
              <ChapterDraftView key={msg.id} msg={msg} isActive={isActive} onSend={isActive ? onSend : null} />
            )
          }
          if (msg.role === 'agent' && msg.interrupt_type === 'plan_approval') {
            return <PlanView key={msg.id} msg={msg} />
          }
          return <MessageBubble key={msg.id} msg={msg} />
        })}

        {/* Completion card */}
        {phase === 'complete' && result && (
          <CompletionCard result={result} onReset={onReset} />
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      {!isChapterReviewActive && (
        <div className="border-t border-white/10 px-6 py-4">
          {/* Quick-option buttons */}
          {showButtons && (
            <div className="mb-3 space-y-2">
              <p className="text-xs text-gray-500 mb-2">{getHint(currentInterrupt)}</p>
              <div className="flex flex-wrap gap-2">
                {quickOptions.map(opt => (
                  opt.value === '__custom__' ? (
                    <button
                      key={opt.value}
                      onClick={() => { setCustomMode(true); setTimeout(() => inputRef.current?.focus(), 50) }}
                      className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors
                        bg-yellow-900/40 hover:bg-yellow-800/40 text-yellow-300 border border-yellow-700/30`}
                    >
                      {opt.label}
                    </button>
                  ) : (
                    <button
                      key={opt.value}
                      onClick={() => handleSend(opt.value)}
                      className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors
                        ${opt.style === 'green'
                          ? 'bg-green-800/50 hover:bg-green-700/50 text-green-200 border border-green-700/30'
                          : 'bg-blue-900/40 hover:bg-blue-800/40 text-blue-300 border border-blue-700/30'}`}
                    >
                      {opt.label}
                    </button>
                  )
                ))}
              </div>
            </div>
          )}

          {/* Text input (free text or custom mode) */}
          {showTextInput && (
            <>
              {customMode && (
                <div className="flex items-center gap-2 mb-2">
                  <button
                    onClick={() => setCustomMode(false)}
                    className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
                  >
                    ← Volver a opciones
                  </button>
                </div>
              )}
              {!customMode && currentInterrupt && (
                <p className="text-xs text-gray-500 mb-2">{getHint(currentInterrupt)}</p>
              )}
              <div className="flex gap-3">
                <textarea
                  ref={inputRef}
                  rows={3}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKey}
                  disabled={!canInput}
                  placeholder={canInput ? 'Escribe tu respuesta… (Enter para enviar)' : 'Esperando al agente…'}
                  className={`flex-1 resize-none rounded-xl px-4 py-3 text-sm glass border
                    focus:outline-none focus:border-brand-500/50 transition-colors duration-150 placeholder-gray-600
                    ${canInput ? 'text-gray-100' : 'text-gray-600 cursor-not-allowed'}`}
                />
                <button
                  onClick={() => handleSend()}
                  disabled={!canInput || !input.trim()}
                  className={`px-4 rounded-xl flex items-center justify-center transition-all duration-150
                    ${canInput && input.trim()
                      ? 'bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-900/30'
                      : 'bg-white/5 text-gray-600 cursor-not-allowed'}`}
                >
                  <Send size={18} />
                </button>
              </div>
            </>
          )}

          {/* Waiting state — no interrupt active */}
          {!canInput && !isChapterReviewActive && phase === 'active' && (
            <p className="text-xs text-gray-600 text-center py-2">Los agentes están trabajando…</p>
          )}
        </div>
      )}
    </div>
  )
}

function MessageBubble({ msg }) {
  const isUser  = msg.role === 'user'
  const isError = msg.role === 'error'
  const colorClass = AGENT_COLORS[msg.agent] || 'text-gray-400'
  const emoji      = AGENT_EMOJIS[msg.agent] || '🤖'
  const displayContent = (msg.role === 'system') ? normalizeSystemMessage(msg.content) : msg.content

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-full glass flex items-center justify-center flex-shrink-0 text-sm">
          {emoji}
        </div>
      )}
      <div className={`max-w-2xl ${isUser ? 'order-first' : ''}`}>
        {!isUser && (
          <p className={`text-xs font-semibold mb-1 ${colorClass}`}>
            {msg.agent}
            {msg.chapter && <span className="text-gray-500 font-normal ml-2">{msg.chapter}</span>}
          </p>
        )}
        <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap
          ${isUser
            ? 'bg-brand-700/40 text-gray-100 rounded-tr-sm'
            : isError
              ? 'bg-red-900/30 border border-red-500/30 text-red-300'
              : 'glass text-gray-200 rounded-tl-sm'}`}>
          {displayContent}
        </div>
      </div>
    </div>
  )
}

function CompletionCard({ result, onReset }) {
  const downloadUrl = result.download_path ? `/api/output/${result.download_path}` : null
  const filename = result.final_path
    ? result.final_path.replace(/\\/g, '/').split('/').pop()
    : 'LIBRO_FINAL.docx'

  return (
    <div className="glass rounded-2xl p-6 border border-green-500/30 bg-green-900/10">
      <h3 className="text-lg font-bold text-green-400 mb-4">🎉 ¡Tu libro está listo!</h3>

      <div className="space-y-2 mb-5">
        <p className="text-sm text-gray-300">
          <span className="text-gray-500">Título:</span>{' '}
          <strong className="text-white">{result.title}</strong>
        </p>
        <p className="text-sm text-gray-300">
          <span className="text-gray-500">Capítulos:</span>{' '}
          <strong className="text-white">{result.chapters_count}</strong>
        </p>
        <p className="text-sm text-gray-300">
          <span className="text-gray-500">Archivo:</span>{' '}
          <code className="text-green-400 text-xs break-all">{filename}</code>
        </p>
        <p className="text-xs text-gray-500 mt-1">
          El libro también fue guardado en tu carpeta Biblioteca.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        {downloadUrl ? (
          <a
            href={downloadUrl}
            download={filename}
            className="inline-flex items-center justify-center gap-2 bg-green-700 hover:bg-green-600
                       text-white text-sm px-5 py-2.5 rounded-xl transition-colors font-medium"
          >
            ⬇️ Descargar libro (.docx)
          </a>
        ) : (
          <p className="text-xs text-yellow-400">
            ⚠️ El libro fue guardado en la carpeta Biblioteca del servidor.
          </p>
        )}

        <p className="text-xs text-gray-600 text-center mt-1">
          Incluye portada, capítulos, índice y sección del autor.
        </p>
        <button
          onClick={onReset}
          className="mt-2 w-full py-2.5 rounded-xl text-sm font-medium border border-white/10
                     text-gray-400 hover:text-white hover:border-white/30 glass glass-hover transition-colors"
        >
          ← Crear otro libro
        </button>
      </div>
    </div>
  )
}

function getHint(interrupt) {
  if (!interrupt) return ''
  const data = interrupt.data || {}
  if (data.hint) return data.hint
  const type = interrupt.interrupt_type
  if (type === 'interview') return 'Responde las preguntas del Arquitecto para diseñar tu libro.'
  if (type === 'plan_approval') return 'Revisa el plan y decide si aprobarlo o pedir cambios.'
  if (type === 'interview_confirmation') return 'Confirma los datos o pide correcciones.'
  return 'Escribe tu respuesta y presiona Enter.'
}
