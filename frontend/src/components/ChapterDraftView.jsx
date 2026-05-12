/**
 * Rich view for chapter draft interrupts.
 * When isActive=true (current interrupt): editable textarea + Accept/Feedback buttons.
 * When isActive=false (history): read-only collapsed view.
 */

import { useState } from 'react'
import { ChevronDown, ChevronUp, Check, MessageSquare } from 'lucide-react'

export default function ChapterDraftView({ msg, isActive = false, onSend }) {
  const [expanded, setExpanded] = useState(true)
  const [editedDraft, setEditedDraft] = useState(null)   // null = not yet touched
  const [showFeedback, setShowFeedback] = useState(false)
  const [feedbackText, setFeedbackText] = useState('')

  const data = msg.raw || {}
  const originalDraft = data.draft || msg.content || ''
  const editorFeedback = data.editor_feedback || ''
  const chapterNum = data.chapter_num
  const total = data.total_chapters
  const title = data.chapter_title || ''
  const revision = data.revision || 0
  const hint = data.hint || ''

  // Use edited content if user touched it, otherwise the original draft
  const currentDraft = editedDraft !== null ? editedDraft : originalDraft

  const handleAccept = () => {
    if (!onSend) return
    onSend(JSON.stringify({ action: 'aprobar', content: currentDraft }))
  }

  const handleFeedback = () => {
    if (!onSend || !feedbackText.trim()) return
    onSend(JSON.stringify({ action: 'reescribir', feedback: feedbackText.trim() }))
    setFeedbackText('')
    setShowFeedback(false)
  }

  return (
    <div className="glass rounded-2xl overflow-hidden border-yellow-500/20">
      {/* Header */}
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center justify-between px-5 py-3 glass-hover"
      >
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-yellow-400 font-semibold text-sm">✍️ Escritor</span>
          <span className="text-xs text-gray-500">
            Capítulo {chapterNum}/{total} — {title}
          </span>
          {revision > 0 && (
            <span className="text-xs bg-yellow-900/40 text-yellow-400 px-2 py-0.5 rounded-full">
              Revisión #{revision}
            </span>
          )}
          {isActive && (
            <span className="text-xs bg-green-900/40 text-green-400 px-2 py-0.5 rounded-full animate-pulse">
              Esperando revisión
            </span>
          )}
        </div>
        {expanded
          ? <ChevronUp size={16} className="text-gray-500 flex-shrink-0" />
          : <ChevronDown size={16} className="text-gray-500 flex-shrink-0" />}
      </button>

      {expanded && (
        <div className="px-5 pb-5">
          {/* Editor notes banner */}
          {editorFeedback && (
            <div className="mb-4 bg-red-900/20 border border-red-500/20 rounded-xl p-3">
              <p className="text-xs font-semibold text-red-400 mb-1">⚠️ El editor solicitó esta revisión</p>
              <p className="text-xs text-red-300/80 whitespace-pre-wrap line-clamp-4">{editorFeedback}</p>
            </div>
          )}

          {/* Draft — editable when active, read-only otherwise */}
          {isActive ? (
            <textarea
              value={currentDraft}
              onChange={e => setEditedDraft(e.target.value)}
              spellCheck={false}
              className="w-full bg-black/20 rounded-xl p-4 text-sm text-gray-200 leading-relaxed
                         font-serif resize-y focus:outline-none focus:ring-1 focus:ring-yellow-500/40
                         border border-white/10 min-h-96"
              style={{ height: '480px' }}
            />
          ) : (
            <div className="bg-black/20 rounded-xl p-4 max-h-96 overflow-y-auto">
              <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap font-serif">
                {originalDraft}
              </p>
            </div>
          )}

          {/* Active controls */}
          {isActive && (
            <div className="mt-4 space-y-3">
              <p className="text-xs text-gray-500 italic">{hint}</p>

              {/* Feedback input */}
              {showFeedback && (
                <div className="flex gap-2 items-start">
                  <textarea
                    rows={2}
                    value={feedbackText}
                    onChange={e => setFeedbackText(e.target.value)}
                    placeholder="Describe los cambios que quieres en este capítulo..."
                    className="flex-1 resize-none rounded-xl px-3 py-2 text-sm glass border border-white/10
                               text-gray-100 placeholder-gray-600 focus:outline-none focus:border-brand-500/50"
                    onKeyDown={e => {
                      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleFeedback() }
                    }}
                  />
                  <button
                    onClick={handleFeedback}
                    disabled={!feedbackText.trim()}
                    className="px-4 py-2 rounded-xl text-xs bg-orange-800/60 hover:bg-orange-700/60
                               text-orange-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    Enviar
                  </button>
                </div>
              )}

              {/* Action buttons */}
              <div className="flex gap-3">
                <button
                  onClick={handleAccept}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl
                             bg-green-700/60 hover:bg-green-600/60 text-green-200 text-sm font-medium
                             transition-colors"
                >
                  <Check size={16} />
                  Aceptar capítulo
                </button>
                <button
                  onClick={() => setShowFeedback(f => !f)}
                  className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl
                              text-sm font-medium transition-colors
                              ${showFeedback
                                ? 'bg-orange-800/60 text-orange-200'
                                : 'bg-yellow-900/40 hover:bg-yellow-800/40 text-yellow-300'}`}
                >
                  <MessageSquare size={16} />
                  Solicitar cambios
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
