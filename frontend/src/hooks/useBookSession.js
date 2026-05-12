import { useState, useRef, useCallback, useEffect } from 'react'
import { BookSocketClient } from '../lib/websocket'

const LS_KEY = 'bookSession'

/**
 * Core hook managing the WebSocket session and all UI state.
 *
 * State machine:
 *   idle -> connecting -> active (interrupt loop) -> complete | error
 *
 * Durante auto-reconexion el phase no cambia y reconnecting:true
 * se expone para que la UI muestre un banner con la razon de desconexion.
 */
export function useBookSession() {
  const [phase, setPhase]                   = useState('idle')
  const [sessionId, setSessionId]           = useState(null)
  const [sessionToken, setSessionToken]     = useState(null)
  const [currentInterrupt, setCurrentInterrupt] = useState(null)
  const [agentStatus, setAgentStatus]       = useState(null)
  const [messages, setMessages]             = useState([])
  const [result, setResult]                 = useState(null)
  const [errorMsg, setErrorMsg]             = useState(null)
  const [reconnecting, setReconnecting]     = useState(false)

  const clientRef      = useRef(null)
  const isCompleteRef  = useRef(false)
  const lastWarningRef = useRef('')

  const addMessage = useCallback((msg) => {
    setMessages(prev => [...prev, { ...msg, id: Date.now() + Math.random() }])
  }, [])

  // Persist sessionId + sessionToken to localStorage once received
  useEffect(() => {
    if (sessionId && sessionToken) {
      const saved = JSON.parse(localStorage.getItem(LS_KEY) || '{}')
      localStorage.setItem(LS_KEY, JSON.stringify({ ...saved, sessionId, sessionToken }))
    }
  }, [sessionId, sessionToken])

  // Clear localStorage when book completes
  useEffect(() => {
    if (phase === 'complete') {
      localStorage.removeItem(LS_KEY)
    }
  }, [phase])

  const handleServerMessage = useCallback((msg) => {
    switch (msg.type) {
      case 'session_created':
        setSessionId(msg.session_id)
        setSessionToken(msg.session_token || null)
        setPhase('active')
        setReconnecting(false)
        setErrorMsg(null)
        if (clientRef.current) {
          clientRef.current._sessionId = msg.session_id
        }
        if (!msg.reconnected) {
          // Nueva sesion: resetear estado de agente
          setAgentStatus({ agent: 'Sistema', status: 'working' })
        }
        // Si es reconexion: conservar currentInterrupt y agentStatus
        // El servidor mandara agent_status actualizado a continuacion
        if (msg.reconnected) {
          addMessage({
            role: 'system',
            agent: 'Sistema',
            content: 'Reconectado al servidor. Continuando...',
          })
        }
        break

      case 'agent_status':
        setAgentStatus(msg)
        if (msg.status === 'working') {
          addMessage({
            role: 'system',
            agent: msg.agent,
            content: `${getAgentEmoji(msg.agent)} **${msg.agent}** esta trabajando...`,
            chapter: msg.chapter_num ? `Capitulo ${msg.chapter_num}/${msg.total_chapters}` : null,
          })
        }
        break

      case 'interrupt':
        setCurrentInterrupt(msg)
        setPhase('active')
        addMessage({
          role: 'agent',
          agent: msg.agent,
          interrupt_type: msg.interrupt_type,
          content: getInterruptContent(msg),
          raw: msg.data,
        })
        break

      case 'complete':
        isCompleteRef.current = true
        setResult(msg)
        setCurrentInterrupt(null)
        setPhase('complete')
        setReconnecting(false)
        setAgentStatus(null)
        addMessage({
          role: 'system',
          agent: 'Sistema',
          content: `Libro completado! "${msg.title}" -- ${msg.chapters_count} capitulos`,
        })
        break

      case 'system_warning':
        lastWarningRef.current = msg.message
        addMessage({
          role: 'system',
          agent: 'Sistema',
          content: `Aviso: ${msg.message}`,
        })
        break

      case 'error':
        setErrorMsg(msg.message)
        setReconnecting(false)
        setPhase(msg.recoverable ? 'error_recoverable' : 'error')
        addMessage({
          role: 'error',
          agent: 'Sistema',
          content: `Error: ${msg.message}`,
        })
        break

      case 'pong':
        break

      default:
        console.warn('Unknown message type:', msg.type)
    }
  }, [addMessage])

  const startSession = useCallback((idea, existingSessionId = null, existingSessionToken = null, referenceImagePath = '') => {
    isCompleteRef.current = false
    lastWarningRef.current = ''
    setPhase('connecting')
    setMessages([])
    setCurrentInterrupt(null)
    setResult(null)
    setErrorMsg(null)
    setReconnecting(false)

    if (!existingSessionId) {
      localStorage.setItem(LS_KEY, JSON.stringify({ idea }))
    }

    addMessage({
      role: 'user',
      agent: 'Tu',
      content: `Idea: ${idea}`,
    })

    clientRef.current?.disconnect()
    clientRef.current = null

    const client = new BookSocketClient(
      handleServerMessage,
      // onConnect
      () => {
        client.startBook(idea, existingSessionId, existingSessionToken, referenceImagePath)
      },
      // onDisconnect -- only called after all retries are exhausted
      () => {
        if (!isCompleteRef.current) {
          setReconnecting(false)
          setPhase(p => p === 'complete' ? p : 'error_recoverable')
          const cause = lastWarningRef.current
            ? `Ultima advertencia: ${lastWarningRef.current} -- `
            : ''
          setErrorMsg(`${cause}Conexion perdida. El libro sigue procesandose en el servidor.`)
        }
      },
      // onReconnecting -- called before each auto-retry with disconnect reason
      (reason) => {
        setReconnecting(true)
        setErrorMsg(reason ? `Desconectado (${reason}) -- reconectando...` : 'Reconectando...')
      },
    )

    clientRef.current = client
    client.connect()
  }, [handleServerMessage, addMessage])

  const sendResponse = useCallback((response) => {
    if (!clientRef.current) return
    clientRef.current.resume(response)

    let displayContent = response
    try {
      const data = JSON.parse(response)
      if (data.action === 'aprobar') {
        displayContent = 'Capitulo aceptado'
      } else if (data.action === 'reescribir') {
        displayContent = `Cambios solicitados: ${data.feedback}`
      }
    } catch {}

    addMessage({
      role: 'user',
      agent: 'Tu',
      content: displayContent,
    })
    setCurrentInterrupt(null)
  }, [addMessage])

  const reset = useCallback(() => {
    clientRef.current?.disconnect()
    clientRef.current = null
    localStorage.removeItem(LS_KEY)
    setPhase('idle')
    setSessionId(null)
    setSessionToken(null)
    setCurrentInterrupt(null)
    setAgentStatus(null)
    setMessages([])
    setResult(null)
    setErrorMsg(null)
    setReconnecting(false)
  }, [])

  // Reconectar cuando la pestaña vuelve a ser visible (pantalla encendida / foco recuperado)
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState !== 'visible') return
      if (isCompleteRef.current) return
      const client = clientRef.current
      if (!client?._sessionId) return
      const wsReady = client.ws?.readyState === WebSocket.OPEN
      const wsClosed = !client.ws || client.ws.readyState === WebSocket.CLOSED
      if (!wsReady && wsClosed) {
        client._stopped = false
        client._reconnectAttempts = 0
        client.connect()
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clientRef.current?.disconnect()
    }
  }, [])

  return {
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
  }
}

function getAgentEmoji(agent) {
  const map = {
    'Arquitecto': '🏛️',
    'Escritor':   '✍️',
    'Editor':     '🔍',
    'Maquetador': '📐',
    'Publicador': '🚀',
    'Sistema':    '⚙️',
  }
  return map[agent] || '🤖'
}

function getInterruptContent(msg) {
  const data = msg.data || {}
  if (data.content) return data.content
  if (data.draft)   return data.draft
  if (data.question) return data.question
  return JSON.stringify(data, null, 2)
}
