/**
 * WebSocket client manager.
 * Handles connection, reconnection, and the message protocol.
 *
 * Reconnection strategy:
 *   - On any unexpected close, auto-retry up to MAX_RECONNECT_ATTEMPTS times
 *     with exponential backoff.
 *   - onReconnecting(reason) is called before each retry (UI can show banner with reason).
 *   - onConnect() is called when connection is established (initial or reconnect).
 *   - onDisconnect() is called only after all retries are exhausted.
 *   - onMessage() is called for every server message (including on reconnect).
 */

const WS_URL = import.meta.env.VITE_WS_URL || `ws://${window.location.host}/ws/book`

const RECONNECT_DELAYS = [2000, 4000, 8000, 15000, 30000, 45000, 60000] // backoff in ms
const MAX_RECONNECT_ATTEMPTS = 7

export class BookSocketClient {
  constructor(onMessage, onConnect, onDisconnect, onReconnecting) {
    this.onMessage      = onMessage
    this.onConnect      = onConnect
    this.onDisconnect   = onDisconnect
    this.onReconnecting = onReconnecting   // called before each auto-retry with reason string
    this.ws = null
    this.pingInterval = null
    this._idea = null
    this._sessionId = null
    this._reconnectAttempts = 0
    this._reconnectTimer = null
    this._stopped = false       // true when disconnect is intentional or irrecoverable
  }

  connect() {
    this.ws = new WebSocket(WS_URL)
    this._attachHandlers(this.ws, /* isReconnect= */ false)
  }

  _attachHandlers(ws, isReconnect) {
    ws.onopen = () => {
      this._reconnectAttempts = 0
      this.onConnect?.()
      this._startPing(ws)
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        // Keep client's session_id in sync so reconnects use the right one
        if (msg.type === 'session_created') {
          this._sessionId = msg.session_id
        }
        // Terminal states -> stop auto-reconnect so server close doesn't loop
        if (msg.type === 'complete' || (msg.type === 'error' && !msg.recoverable)) {
          this._stopped = true
        }
        this.onMessage?.(msg)
      } catch (e) {
        console.error('[ws] Failed to parse message', e)
      }
    }

    ws.onclose = (event) => {
      clearInterval(this.pingInterval)
      const reason = event.reason || (event.code ? `codigo ${event.code}` : 'conexion perdida')
      if (!this._stopped && this._sessionId && this._reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        const delay = RECONNECT_DELAYS[this._reconnectAttempts] ?? 30000
        this._reconnectAttempts++
        console.log(`[ws] Reconectando en ${delay}ms (intento ${this._reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}) — ${reason}`)
        this.onReconnecting?.(reason)
        this._reconnectTimer = setTimeout(() => this._autoReconnect(), delay)
      } else {
        this.onDisconnect?.()
      }
    }

    ws.onerror = (err) => {
      console.error('[ws] Error', err)
    }
  }

  _autoReconnect() {
    if (this._stopped) return
    const ws = new WebSocket(WS_URL)
    this.ws = ws

    ws.onopen = () => {
      console.log('[ws] Reconexion exitosa')
      this._reconnectAttempts = 0
      // Resume existing session -- send start directly, do NOT call onConnect
      ws.send(JSON.stringify({
        type:       'start',
        idea:       this._idea || '',
        session_id: this._sessionId,
      }))
      this._startPing(ws)
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'session_created') {
          this._sessionId = msg.session_id
        }
        if (msg.type === 'complete' || (msg.type === 'error' && !msg.recoverable)) {
          this._stopped = true
        }
        this.onMessage?.(msg)
      } catch (e) {
        console.error('[ws] Failed to parse message on reconnect', e)
      }
    }

    ws.onclose = (event) => {
      clearInterval(this.pingInterval)
      const reason = event.reason || (event.code ? `codigo ${event.code}` : 'conexion perdida')
      if (!this._stopped && this._sessionId && this._reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        const delay = RECONNECT_DELAYS[this._reconnectAttempts] ?? 30000
        this._reconnectAttempts++
        console.log(`[ws] Reintentando en ${delay}ms (intento ${this._reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}) — ${reason}`)
        this.onReconnecting?.(reason)
        this._reconnectTimer = setTimeout(() => this._autoReconnect(), delay)
      } else {
        this.onDisconnect?.()
      }
    }

    ws.onerror = (err) => {
      console.error('[ws] Error en reconexion', err)
    }
  }

  _startPing(ws) {
    clearInterval(this.pingInterval)
    this.pingInterval = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, 15000)
  }

  send(data) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
      return true
    }
    return false
  }

  startBook(idea, sessionId = null, referenceImagePath = '') {
    this._idea = idea
    this._sessionId = sessionId
    return this.send({ type: 'start', idea, session_id: sessionId, reference_image_path: referenceImagePath })
  }

  resume(response) {
    return this.send({ type: 'resume', response })
  }

  disconnect() {
    this._stopped = true
    clearInterval(this.pingInterval)
    clearTimeout(this._reconnectTimer)
    this.ws?.close()
  }
}
