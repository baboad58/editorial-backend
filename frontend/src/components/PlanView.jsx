/**
 * Rich view for plan approval interrupts.
 * Renders the book plan in a structured, readable format.
 */

import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

export default function PlanView({ msg }) {
  const [expanded, setExpanded] = useState(true)
  const data = msg.raw || {}
  const plan = data.plan_data || {}
  const content = data.content || msg.content || ''
  const hint = data.hint || ''

  return (
    <div className="glass rounded-2xl overflow-hidden border-blue-500/20">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center justify-between px-5 py-3 glass-hover"
      >
        <div className="flex items-center gap-3">
          <span className="text-blue-400 font-semibold text-sm">🏛️ Arquitecto</span>
          <span className="text-xs text-gray-500">Plan Maestro del Libro</span>
          {plan.num_chapters && (
            <span className="text-xs bg-blue-900/40 text-blue-400 px-2 py-0.5 rounded-full">
              {plan.num_chapters} capítulos
            </span>
          )}
        </div>
        {expanded ? <ChevronUp size={16} className="text-gray-500" /> : <ChevronDown size={16} className="text-gray-500" />}
      </button>

      {expanded && (
        <div className="px-5 pb-5 space-y-4">
          {/* Book metadata */}
          {plan.title && (
            <div className="bg-blue-900/10 border border-blue-500/20 rounded-xl p-4">
              <h3 className="text-lg font-bold text-white">{plan.title}</h3>
              {plan.subtitle && <p className="text-sm text-gray-400 mt-0.5">{plan.subtitle}</p>}
              <div className="flex gap-4 mt-3 flex-wrap">
                <MetaTag label="Género" value={plan.genre} />
                <MetaTag label="Tono" value={plan.tone} />
                <MetaTag label="Audiencia" value={plan.target_audience} />
              </div>
            </div>
          )}

          {/* Chapter list */}
          {plan.chapter_outlines?.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Capítulos</p>
              {plan.chapter_outlines.map((ch, i) => (
                <ChapterRow key={i} chapter={ch} />
              ))}
            </div>
          )}

          {/* Fallback: raw text plan */}
          {!plan.title && content && (
            <div className="bg-black/20 rounded-xl p-4 max-h-80 overflow-y-auto">
              <p className="text-sm text-gray-300 whitespace-pre-wrap">{content}</p>
            </div>
          )}

          {/* Hint */}
          <p className="text-xs text-gray-500 italic">{hint}</p>
        </div>
      )}
    </div>
  )
}

function MetaTag({ label, value }) {
  if (!value) return null
  return (
    <div className="text-xs">
      <span className="text-gray-500">{label}: </span>
      <span className="text-gray-300">{value}</span>
    </div>
  )
}

function ChapterRow({ chapter }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="glass rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-4 py-2.5 text-left glass-hover"
      >
        <span className="text-xs font-mono text-gray-600 w-6 flex-shrink-0">
          {String(chapter.index + 1).padStart(2, '0')}
        </span>
        <span className="text-sm text-gray-200 flex-1">{chapter.title}</span>
        <span className="text-xs text-gray-600">~{chapter.word_count_target}p</span>
        {open ? <ChevronUp size={14} className="text-gray-600" /> : <ChevronDown size={14} className="text-gray-600" />}
      </button>
      {open && (
        <div className="px-4 pb-3 pl-10">
          <p className="text-xs text-gray-400 mb-1.5">{chapter.summary}</p>
          <div className="flex flex-wrap gap-1.5">
            {(chapter.key_points || []).map((p, i) => (
              <span key={i} className="text-xs bg-white/5 text-gray-400 px-2 py-0.5 rounded-full">
                {p}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
