# CLAUDE.md — Book Factory v2.3

## Arrancar (desarrollo local)
```bash
# Backend — desde book-factory/
venv\Scripts\activate
uvicorn backend.main_api:app --port 8000 --ws-ping-interval 0

# Frontend — desde book-factory/frontend/
npm run dev
# Abrir http://localhost:8000 (prod) o http://localhost:5173 (dev HMR)
# Código de acceso beta: OBRA-ALPHA-001 ... OBRA-ALPHA-010

# Reset sesiones (borrar checkpoints)
Remove-Item output\checkpoints.db -Force
```

## Repositorios GitHub
- **editorial-backend** → `https://github.com/baboad58/editorial-backend` — backend + frontend integrado  
  Push desde `book-factory/` (tiene su propio `.git`)
- **editorial-frontend** → `https://github.com/baboad58/editorial-frontend` — frontend Lovable (solo lectura para Claude)  
  Para sincronizar: clonar y copiar `src/` al `frontend/` local, luego `npm install` y rebuild

## Estructura de archivos
```
backend/
├── main_api.py                        ← entry point, SSL truststore, rate limiter
├── agents/   architect.py  writer.py  editor.py  layouter.py  publisher.py
├── graph/    builder.py  state.py  utils.py  error_handler.py  retry.py
├── api/      graph_runner.py  app.py  session.py  models.py  websocket.py
└── tools/    documents.py  cover_generator.py  search.py

frontend/src/
├── App.jsx                            ← routing: / → /acceso → /studio
├── components/Landing.jsx             ← página de presentación
├── components/AccessGate.jsx          ← validación de invite (llama POST /api/verify-invite)
├── components/StudioApp.jsx           ← shell principal del studio
├── components/StartScreen.jsx         ← inicio de sesión / reconexión
├── components/ChatPanel.jsx           ← chat con agentes + botones de interrupt
├── components/AgentSidebar.jsx        ← estado visual de los agentes
├── hooks/useBookSession.js            ← lógica WebSocket + estado de sesión
├── lib/invites.js                     ← verifyInvite() llama al backend (sin códigos en JS)
└── lib/websocket.js                   ← cliente WS con reconnect automático
```

## Flujo del pipeline
```
architect (4 interrupts) → writer → editor → layouter → publisher (sin interrupt)
```
Interrupts del Arquitecto: entrevista → confirmación respuestas → aprobación plan → preferencia revisión capítulos.  
`book_status`: `planning` | `writing` | `editing` | `formatting` | `publishing` | `complete`

## Variables de entorno (.env)
```
ANTHROPIC_API_KEY=sk-ant-api03-...   # Requerida — modelos Claude
GOOGLE_API_KEY=AIza...               # Requerida — Gemini Imagen (portada + capítulos)
TAVILY_API_KEY=tvly-...              # Opcional — búsqueda web para no-ficción/académico
ANTHROPIC_MODEL=claude-sonnet-4-6   # Modelo por defecto
OUTPUT_DIR=output                    # Directorio de salida
OUTPUT_RETENTION_DAYS=30             # Días antes de borrar sesiones antiguas
INVITE_CODES=OBRA-ALPHA-001,...      # Códigos de acceso (separados por coma)
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:8000
```
⚠️ `IDEOGRAM_API_KEY` ya no es necesaria — Gemini es el único generador de imágenes.

## Convenciones críticas
- Todo texto al usuario en **español**
- `current_agent` → `AgentName.X.value` (siempre con `.value`)
- **Todas las LLM** → `retry_llm_call()`, nunca `llm.invoke()`
- `genre` → extraer a variable local al inicio del nodo
- `parse_formatted_text()` → convierte `[SUBTÍTULO:]` + `[IMAGEN:]` → `ContentBlock[]`
- `create_chapter_docx()` → recibe `ContentBlock[]`, nunca texto plano
- `book_status` inicial: `"planning"` (nunca `"interviewing"`)
- `logging.basicConfig` solo en `utils.py`
- `generate_cover()` → retorna `tuple[Optional[str], Optional[str]]` (path, warning)
- Marcadores de imagen en Publisher: `[IMAGE_PROMPT]...[/IMAGE_PROMPT]`
- `humanize_writing=True` activado automáticamente para ficción/YA por el Arquitecto
- SSL corporativo resuelto con `truststore.inject_into_ssl()` en `main_api.py`

## Seguridad (implementado)
- Validación de invitaciones en backend (`POST /api/verify-invite`)
- Rate limiting in-memory: 5 intentos/hora por IP en verify-invite, 10 WS/min por IP
- Headers HTTP: X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy
- Validador semántico de prompts → falla cerrada (rechaza si Haiku no responde)
- `reference_image_path` sanitizado contra path traversal
- Política de retención: auto-borrado de sesiones > `OUTPUT_RETENTION_DAYS` días
- Aviso de privacidad en StartScreen (Ley 19.628 Chile)

## initial_state — campos obligatorios
```python
"plan_revision": 0, "editor_rejection_count": 0,
"plan_feedback_history": [], "chapter_rewrite_history": [], "editor_feedback_history": [],
"layouter_feedback": "", "layouter_rejection_count": 0,
"author_name": "", "author_email": "", "author_bio": "",
"author_cover_preferences": "", "author_acknowledgment_context": "", "interview_answers": "",
"humanize_writing": False,  # se activa automáticamente en architect para ficción
```

## Límites de ciclo (utils.py)
`MAX_PLAN_REVISIONS=3` | `MAX_CHAPTER_REVISIONS=5` | `MAX_EDITOR_REJECTIONS=3` | `MAX_LAYOUTER_REJECTIONS=2`

## Errores frecuentes — solución rápida
| Error | Solución |
|-------|---------|
| `AgentName` sin `.value` | Agregar `.value` en todos los `current_agent` |
| Markdown en docx (`**`, `*`, `#`) | Pasar por `_parse_inline_markdown()` en `documents.py` |
| `CERTIFICATE_VERIFY_FAILED` | `truststore.inject_into_ssl()` ya está en `main_api.py` — verificar que truststore esté instalado |
| `npm install` falla SSL | `npm config set strict-ssl false` |
| WebSocket ping timeout | Arrancar con `--ws-ping-interval 0` |
| Créditos agotados Anthropic | Recargar en console.anthropic.com — el checkpoint persiste, reconectar desde Studio |
| `generate_cover` crash | Desempaquetar tupla: `path, warning = generate_cover(...)` |
| Imagen en página separada al título | `seen_text=False` en `_add_content_blocks` — primera imagen va sin salto previo |

## Regla de edición (OBLIGATORIA)
Leer el archivo completo antes de modificar. Verificar sintaxis con `python -c "from backend... import ..."` después de cada cambio.

→ Documentación completa de errores: ver ERRORES.md  
→ Guía de producción: ver PRODUCCION.md
