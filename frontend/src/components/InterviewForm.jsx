/**
 * Formulario estructurado de entrevista.
 * Muestra todas las preguntas a la vez: pregunta a la izquierda, campo de texto a la derecha.
 * Al enviar, formatea las respuestas como texto numerado para el Arquitecto.
 */

import { useEffect, useRef, useState } from 'react'

export default function InterviewForm({ questions, onSend, disabled }) {
  const [answers, setAnswers] = useState({})
  const [error, setError]     = useState('')
  const firstRef = useRef(null)

  useEffect(() => {
    // Inicializar respuestas vacías y enfocar primer campo
    const init = {}
    questions.forEach(q => { init[q.id] = '' })
    setAnswers(init)
    setTimeout(() => firstRef.current?.focus(), 150)
  }, [questions])

  const setAnswer = (id, value) => {
    setAnswers(prev => ({ ...prev, [id]: value }))
    if (error) setError('')
  }

  const handleSubmit = () => {
    // Validar que todas las preguntas no-opcionales tengan respuesta
    const missing = questions.filter(q => {
      const optional = /opcional/i.test(q.pregunta)
      return !optional && !answers[q.id]?.trim()
    })
    if (missing.length > 0) {
      setError(`Por favor responde: ${missing.map(q => `"${q.titulo}"`).join(', ')}`)
      return
    }

    // Formatear respuestas como texto numerado para el Arquitecto
    const formatted = questions
      .map(q => {
        const ans = answers[q.id]?.trim() || '(Sin respuesta)'
        return `${q.id}. ${q.titulo}: ${ans}`
      })
      .join('\n')

    onSend(formatted)
  }

  const handleKey = (e) => {
    // Shift+Enter en el último campo envía el formulario
    if (e.key === 'Enter' && e.shiftKey && !disabled) {
      e.preventDefault()
      handleSubmit()
    }
  }

  if (!questions || questions.length === 0) return null

  // Separar preguntas base de las de publicación (id >= 8)
  const baseQuestions = questions.filter(q => q.id < 8)
  const pubQuestions  = questions.filter(q => q.id >= 8)

  return (
    <div className="w-full space-y-1 pb-2">
      <QuestionBlock
        questions={baseQuestions}
        answers={answers}
        onChange={setAnswer}
        onKey={handleKey}
        firstRef={firstRef}
        disabled={disabled}
      />

      {pubQuestions.length > 0 && (
        <>
          <div className="flex items-center gap-3 py-3">
            <div className="h-px flex-1 bg-white/10" />
            <span className="text-xs tracking-widest uppercase text-gray-500">Datos para la publicación</span>
            <div className="h-px flex-1 bg-white/10" />
          </div>
          <QuestionBlock
            questions={pubQuestions}
            answers={answers}
            onChange={setAnswer}
            onKey={handleKey}
            disabled={disabled}
          />
        </>
      )}

      {error && (
        <p className="text-xs text-red-400 px-1 pt-1">{error}</p>
      )}

      <div className="pt-3 flex items-center justify-between gap-4">
        <p className="text-xs text-gray-600">
          Las preguntas opcionales pueden dejarse en blanco · Shift+Enter para enviar
        </p>
        <button
          onClick={handleSubmit}
          disabled={disabled}
          className={`px-6 py-2.5 rounded-xl text-sm font-medium transition-all
            ${disabled
              ? 'bg-white/5 text-gray-600 cursor-not-allowed'
              : 'bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-900/30'}`}
        >
          Enviar respuestas →
        </button>
      </div>
    </div>
  )
}

function QuestionBlock({ questions, answers, onChange, onKey, firstRef, disabled }) {
  return (
    <div className="divide-y divide-white/5 border border-white/10 rounded-2xl overflow-hidden">
      {questions.map((q, idx) => {
        const isOptional = /opcional/i.test(q.pregunta)
        const isMultiline = q.pregunta.length > 120 || /descri|formaci|experiencia|enfoque|bio|cuéntanos|cuéntame/i.test(q.pregunta)
        return (
          <div key={q.id} className="grid grid-cols-[1fr_1.2fr] gap-0 min-h-[72px]">
            {/* Pregunta — columna izquierda */}
            <div className="px-4 py-3 bg-white/[0.02] border-r border-white/10 flex flex-col justify-start gap-1">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-brand-400 opacity-70 flex-shrink-0">
                  {q.id}.
                </span>
                <span className="text-xs font-semibold text-gray-300">{q.titulo}</span>
                {isOptional && (
                  <span className="text-[10px] text-gray-600 bg-white/5 px-1.5 py-0.5 rounded-full flex-shrink-0">
                    opcional
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-500 leading-relaxed pl-5">
                {/* Ocultar el paréntesis "(Opcional)" del texto para no duplicar */}
                {q.pregunta.replace(/\(Opcional[^)]*\)/gi, '').trim()}
              </p>
            </div>

            {/* Respuesta — columna derecha */}
            <div className="px-3 py-2 flex items-start">
              <textarea
                ref={idx === 0 && firstRef ? firstRef : undefined}
                rows={isMultiline ? 4 : 2}
                value={answers[q.id] ?? ''}
                onChange={e => onChange(q.id, e.target.value)}
                onKeyDown={onKey}
                disabled={disabled}
                placeholder={isOptional ? 'Opcional…' : 'Tu respuesta…'}
                className={`w-full resize-none rounded-xl px-3 py-2 text-sm glass border
                  focus:outline-none focus:border-brand-500/50 transition-colors
                  placeholder-gray-700 leading-relaxed
                  ${disabled ? 'text-gray-600 cursor-not-allowed' : 'text-gray-100'}`}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}
