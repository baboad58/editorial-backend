# ERRORES.md — Book Factory Knowledge Base
> Actualizar en cada sesión. Claude debe leer este archivo al inicio de cada conversación.
>
> ⚠️ **INSTRUCCIÓN PARA CLAUDE:** Ante cualquier error, busca aquí PRIMERO antes de consultar
> tu base de conocimiento interna o la web. Usa Ctrl+F con el mensaje exacto del error,
> el archivo afectado, o una palabra clave del síntoma.

---

## ÍNDICE DE ERRORES

| # | Palabra clave | Síntoma corto | Archivo |
|---|--------------|---------------|---------|
| E01 | `NotFoundError` `claude-3-5-sonnet` | Modelo LLM retirado | `graph/utils.py` |
| E02 | `unexpected keyword argument 'visual_context'` | Kwarg inválido en cover | `agents/publisher.py` |
| E03 | `ImportError` `generate_chapter_image` | Función no existía | `tools/cover_generator.py` |
| E05 | `404` descarga botón libro | Path de descarga incorrecto | `api/graph_runner.py` |
| E06 | Título del libro es de referencia | Arquitecto copió título de libro citado | `agents/architect.py` |
| E07 | Mensajes duplicados al reconectar | Cliente WS anterior no desconectado | `frontend/hooks/useBookSession.js` |
| E08 | `python-multipart` `Form data requires` | Dependencia no instalada | `requirements.txt` |
| E09 | Mensaje "trabajando" duplicado | AgentStatusMessage enviado dos veces | `api/websocket.py` |
| E10 | "El plan está listo" aparece después de aprobar | Mensaje en interrupt equivocado | `agents/architect.py` |
| E11 | Capítulo infantil rechazado por extensión | Límites de palabras genéricos | `graph/utils.py` `agents/architect.py` |
| E13 | Pantalla de descarga no aparece al terminar | Race condition complete vs onDisconnect | `frontend/hooks/useBookSession.js` |
| E14 | Imagen sale fuera de página en docx | Alto no calculado según dimensiones reales | `tools/documents.py` |
| E15 | `CERTIFICATE_VERIFY_FAILED` API Anthropic/Gemini | Proxy corporativo SSL intercepta HTTPS | `backend/main_api.py` |
| E16 | `keepalive ping timeout` WebSocket cae cada ~2 min | uvicorn CLI tiene ping activo por defecto | arranque uvicorn |
| E17 | `react-router-dom@^7.x` not found en npm | npm caché desactualizado + SSL corporativo | `frontend/` |
| E18 | `Messages.create() got unexpected keyword argument 'http_client'` | http_client no soportado en esta versión de ChatAnthropic | `graph/utils.py` |
| E19 | Imagen queda en página separada del título | `doc.add_page_break()` antes de primera imagen | `tools/documents.py` |
| E20 | `process is not defined` en consola admin | `process.env` no existe en Vite (solo Node.js) | `frontend/integrations/supabase/client.ts` |
| E21 | `Reflect.get called on non-object` en admin | Proxy de Supabase llama `Reflect.get(null,...)` cuando cliente es null | `frontend/integrations/supabase/client.ts` |
| E22 | Variables `VITE_*` no disponibles en Vite | `.env` estaba en `book-factory/` pero Vite lee desde `book-factory/frontend/` | `frontend/vite.config.js` |
| E23 | `Failed to send a request to the Edge Function` admin | Lovable Edge Functions no accesibles desde localhost — solo desde Lovable Cloud | `frontend/lib/admin.js` |
| E24 | `Method Not Allowed 405` en formulario de contacto | Landing.jsx llamaba `supabase.functions.invoke('send-contact')` que no existe localmente | `frontend/components/Landing.jsx` |
| E25 | Consola admin cuelga al asignar código | Email vía Resend bloqueaba respuesta HTTP (timeout 15s en el event loop) | `backend/api/admin.py` |
| E26 | `Client error 400` en `/api/admin/data` | Columna `contact_submissions` se llama `codigo_asignado`, no `assigned_code` | `backend/api/admin.py` |
| E27 | Login admin `Error 500` — `400 Bad Request` Supabase | Columna `Estado` en realidad es `estado` (minúscula); contraseña es hash bcrypt | `backend/api/admin.py` |
| E28 | Preguntas de entrevista aparecen duplicadas | Bubble mostraba texto completo + formulario al mismo tiempo | `frontend/components/ChatPanel.jsx` |
| E29 | Punto 10 resumen mezcla correo y portada | `ANSWER_SUMMARY_PROMPT` tenía `10. Contacto y portada` en lugar de Q10/Q11 separados | `backend/agents/architect.py` |
| E30 | `onReset` en CompletionCard no redirige a `/acceso` | `ChatPanel` recibía `onReset={reset}` en lugar de `onReset={handleReset}` | `frontend/components/StudioApp.jsx` |

---

## DETALLE DE ERRORES

---

### E01 — Modelo LLM retirado

```
NotFoundError: model: claude-3-5-sonnet-20241022
```

**Causa:** Anthropic retiró ese modelo del API.  
**Archivo:** `backend/graph/utils.py` → `_AGENT_MODEL_CONFIG`  
**Fix:**
```python
# Alta complejidad:
"claude-3-5-sonnet-20241022"  →  "claude-sonnet-4-6"
# Baja complejidad (Layouter, Publisher):
"claude-3-haiku-20240307"     →  "claude-haiku-4-5-20251001"
```
Aplicar también en el fallback de `get_llm_for_agent`.  
**Modelos vigentes:** alta → `claude-sonnet-4-6` | baja → `claude-haiku-4-5-20251001`

---

### E02 — Kwarg inesperado `visual_context`

```
TypeError: generate_cover_with_ideogram() got an unexpected keyword argument 'visual_context'
```

**Causa:** `publisher.py` pasaba `visual_context=` pero la firma no lo acepta.  
**Archivo:** `backend/agents/publisher.py` ~línea 595  
**Fix:** Eliminar `visual_context=state.get("visual_context", "")` de la llamada.

---

### E03 — `generate_chapter_image` no existe

```
ImportError: cannot import name 'generate_chapter_image' from 'backend.tools.cover_generator'
```

**Causa:** `documents.py` importaba una función nunca implementada.  
**Archivo:** `backend/tools/cover_generator.py`  
**Fix:** Implementar con firma:
```python
def generate_chapter_image(description, output_dir, chapter_index, image_index,
                           book_title="", genre="", reference_image_path="") -> tuple[Optional[str], Optional[str]]:
```

---

### E05 — Libro no disponible para descarga (404)

```
GET /api/output/LIBRO_FINAL.docx → 404 Not Found
```

**Causa:** `_to_download_path(final_path, output_dir)` usaba subdir de sesión. El endpoint busca desde `output/`.  
**Archivo:** `backend/api/graph_runner.py`  
**Fix:**
```python
# Incorrecto:
"download_path": _to_download_path(final_path, output_dir)
# Correcto:
"download_path": _to_download_path(final_path, base_output_dir)
```
Aplicar en **ambas** llamadas a `_to_download_path`.

---

### E06 — Título del libro tomado de referencia narrativa

**Síntoma:** El libro se tituló con el nombre de un libro que el usuario citó como referencia de estilo.  
**Causa:** `PLAN_PROMPT` no distinguía referencias de estilo del libro a crear.  
**Archivo:** `backend/agents/architect.py` → `PLAN_PROMPT`  
**Fix:** Agregar al inicio del prompt:
```
REGLA CRÍTICA: Si el usuario cita un libro existente, es SOLO referencia de estilo.
Nunca usar su nombre como título ni copiar su trama.
```

---

### E07 — Mensajes duplicados al reconectar

**Síntoma:** Al reconectar, mensajes del cliente anterior persisten o aparecen duplicados.  
**Causa:** `startSession` creaba nuevo `BookSocketClient` sin desconectar el anterior.  
**Archivo:** `frontend/src/hooks/useBookSession.js` → `startSession`  
**Fix:** Agregar antes de `new BookSocketClient(...)`:
```javascript
clientRef.current?.disconnect()
clientRef.current = null
```

---

### E08 — `python-multipart` no instalado

```
RuntimeError: Form data requires "python-multipart" to be installed
```

**Causa:** FastAPI requiere `python-multipart` para `UploadFile`.  
**Fix:**
```bash
venv\Scripts\pip.exe install python-multipart
```
Agregar `python-multipart>=0.0.9` a `requirements.txt`.

---

### E09 — Mensaje "trabajando" duplicado tras respuesta del usuario

**Síntoma:** `✍️ **Escritor** está trabajando...` (u otro agente) aparece dos veces seguidas al aprobar un capítulo o interrupt.  
**Causa:** `websocket.py` enviaba `AgentStatusMessage(status="working")` inmediatamente al recibir la respuesta del usuario (línea 258), y luego el runner también enviaba `__agent_working__` al iniciar el siguiente paso del grafo.  
**Archivo:** `backend/api/websocket.py`  
**Fix:** Eliminar la línea redundante en el handler tras `session.pending_interrupt = None`:
```python
# Eliminar esta línea:
await _send(websocket, AgentStatusMessage(agent=agent, status="working").model_dump())
```
El runner ya envía su propio `__agent_working__` al comienzo de cada iteración del loop.

---

### E10 — "El plan está listo" aparece DESPUÉS de aprobar los capítulos

**Síntoma:** El usuario ve la lista de capítulos, los aprueba, y recién entonces aparece el mensaje "El plan está listo. El libro tendrá X capítulos." — orden confuso.  
**Causa:** Ese texto estaba en el interrupt `review_mode`, que se dispara **después** de que el usuario aprueba el interrupt `plan_approval`.  
**Archivo:** `backend/agents/architect.py`  
**Fix:** Mover el texto al inicio del `content` del interrupt `plan_approval`:
```python
"content": (
    f"El plan está listo. El libro tendrá {num_ch} capítulo(s).\n\n"
    + plan_display
),
```
Y en `review_mode` dejar solo la pregunta sobre preferencia de revisión, sin el anuncio.

---

### E11 — Capítulos infantiles rechazados por extensión insuficiente

```
[Editor] Cap.2 | Aprobado=False | Palabras=957/1500 | Rechazo #1
```

**Causa 1:** `_validate_plan` usaba `max(2000, ...)` para todos los géneros, aplastando targets menores que ponía el LLM para infantil.  
**Causa 2:** `get_genre_word_limits` no distinguía álbum ilustrado de juvenil.  
**Archivos:** `backend/graph/utils.py` → `get_genre_word_limits` | `backend/agents/architect.py` → `_validate_plan`  
**Fix en `utils.py`:**
```python
# Álbum ilustrado / infantil ilustrado:
if any(k in g for k in ["ilustrad", "álbum", "album", "picture"]):
    return (200, 900)
# Young adult:
if any(k in g for k in ["young adult", "ya "]):
    return (1500, 4000)
# Infantil / juvenil:
if any(k in g for k in ["infantil", "juvenil"]):
    return (500, 1800)
```
**Fix en `_validate_plan`:**
```python
wc_min, wc_max = get_genre_word_limits(plan.get("genre", ""))
ch["word_count_target"] = max(wc_min, min(wc_max, ch["word_count_target"]))
```

---

### E13 — Pantalla de descarga no aparece al terminar (vuelve al menú)

**Síntoma:** El libro se genera exitosamente en el backend, pero el frontend vuelve a la pantalla principal sin mostrar la tarjeta de descarga.  
**Causa:** Race condition — el servidor envía `complete` y cierra el WebSocket casi simultáneamente. El handler `onDisconnect` del cliente dispara antes de que React procese `setPhase('complete')`. El `phase` en el closure de `onDisconnect` es el valor viejo (`'active'`), así que `setPhase(p => ...)` setea `'error'` en lugar de respetar `'complete'`. Como `showStart = phase === 'error'`, vuelve al menú.  
**Archivo:** `frontend/src/hooks/useBookSession.js`  
**Fix:** Usar un ref sincrónico para rastrear la completitud:
```javascript
const isCompleteRef = useRef(false)

// En handleServerMessage, case 'complete':
isCompleteRef.current = true   // ← antes de setPhase('complete')

// En onDisconnect del cliente:
if (!isCompleteRef.current) { ... }  // ← en lugar de (phase !== 'complete')

// En startSession al inicio:
isCompleteRef.current = false
```
El ref se actualiza sincrónicamente en el mismo event loop tick que llega el mensaje, garantizando que `onDisconnect` lo vea correctamente.

---

### E14 — Imagen de capítulo/portada sale fuera de la página en el docx

**Síntoma:** La imagen se coloca en la línea 1 de la página pero su alto desborda el margen inferior.  
**Causa:** `add_picture(img_path, width=Inches(X))` solo fija el ancho; python-docx calcula el alto proporcional pero no verifica si cabe en la página. Para portada 2:3 con `width=4.5"` → `height=6.75"`, que junto al título supera la página.  
**Archivo:** `backend/tools/documents.py`  
**Fix:** Agregar helper `_fit_image(img_path, max_w, max_h)` que usa PIL para leer dimensiones reales y calcular `(width, height)` que caben en los límites:
```python
from PIL import Image as _PILImage
# Escala preservando aspect ratio para que quepa en max_w × max_h
```
Límites: capítulos → `max_w=4.0", max_h=6.5"` | portada → `max_w=4.0", max_h=3.5"`.  
Agregar `Pillow>=10.0.0` a `requirements.txt`.

---

### E15 — `CERTIFICATE_VERIFY_FAILED` al llamar a Anthropic/Gemini

```
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]
certificate verify failed: Basic Constraints of CA cert not marked critical
```

**Causa:** Proxy corporativo intercepta HTTPS con su propio certificado. Python no lo confía.  
**Archivo:** `backend/main_api.py`  
**Fix aplicado:** `truststore.inject_into_ssl()` al inicio de `main_api.py` — usa el almacén de certificados de Windows.
```python
import truststore
truststore.inject_into_ssl()   # ANTES de cualquier import de langchain/anthropic
```
Instalar si falta: `venv\Scripts\pip install truststore`  
**Nota:** NO usar `httpx.Client(verify=False)` ni `ssl._create_unverified_context` — ChatAnthropic ignora esos patches.

---

### E16 — WebSocket cae cada ~2 minutos (`keepalive ping timeout`)

```
ConnectionClosedError: sent 1011 (internal error) keepalive ping timeout; no close frame received
```

**Causa:** uvicorn CLI tiene ping interval activo por defecto (~20s). Si el cliente tarda en responder el pong, cierra la conexión.  
**Fix:** Arrancar uvicorn con:
```bash
uvicorn backend.main_api:app --port 8000 --ws-ping-interval 0
```
El frontend tiene reconexión automática (`visibilitychange` API), pero la conexión intermitente genera ruido.  
**Archivo:** `activar-frontend.txt` ya tiene el comando correcto.

---

### E17 — `npm install` falla con `ETARGET` o SSL

```
npm error notarget No matching version found for react-router-dom@^7.15.0
npm error UNABLE_TO_VERIFY_LEAF_SIGNATURE
```

**Causa 1 (ETARGET):** npm caché desactualizado con proxy corporativo.  
**Causa 2 (SSL):** Proxy corporativo intercepta HTTPS del registry de npm.  
**Fix:**
```bash
npm config set strict-ssl false
npm install
```
Aplicar solo en el entorno local con proxy — no subir `.npmrc` con esta configuración a producción.

---

### E18 — `Messages.create() got unexpected keyword argument 'http_client'`

```
TypeError: Messages.create() got an unexpected keyword argument 'http_client'
UserWarning: WARNING! http_client is not default parameter. http_client was transferred to model_kwargs.
```

**Causa:** `langchain_anthropic` v1.4.1 no expone `http_client` en `ChatAnthropic` — lo reenvía como `model_kwarg` al API de Anthropic, que lo rechaza.  
**Fix:** No pasar `http_client` a `ChatAnthropic`. Usar `truststore` globalmente (ver E15).

---

### E19 — Primera imagen de capítulo aparece en página separada del título

**Síntoma:** Título del capítulo en pág. 1 (vacía abajo), imagen en pág. 2, texto en pág. 3+.  
**Causa:** `_add_content_blocks` hacía `doc.add_page_break()` antes de TODAS las imágenes, incluyendo la primera.  
**Archivo:** `backend/tools/documents.py`  
**Fix aplicado:** Rastrear `seen_text = False`. Si la imagen es la primera del capítulo y no ha habido texto previo, omitir el salto antes de ella.
```python
if seen_text or image_counter > 1:
    doc.add_page_break()
```

---

## MEJORAS IMPLEMENTADAS — Sesión 2026-05-11

| Feature | Archivos |
|---------|----------|
| Nuevo frontend Lovable: Landing + AccessGate + Studio con react-router-dom | `frontend/src/` completo |
| Validación de invitaciones en backend (POST /api/verify-invite + rate limiting) | `api/app.py` `lib/invites.js` `AccessGate.jsx` |
| Headers HTTP de seguridad (X-Frame-Options, CSP, HSTS, etc.) | `api/app.py` |
| Rate limiting WS: 10 conexiones/min por IP | `api/app.py` |
| Validador semántico a falla CERRADA | `api/graph_runner.py` |
| Sanitización reference_image_path contra path traversal | `api/graph_runner.py` |
| Retención automática 30 días (OUTPUT_RETENTION_DAYS) | `api/app.py` |
| Aviso de privacidad Ley 19.628 en StartScreen | `StartScreen.jsx` |
| Botones Sí/No para interrupt review_mode | `ChatPanel.jsx` |
| Reconexión automática al encender pantalla (visibilitychange) | `useBookSession.js` |
| Botón "Reconectar sesión guardada" en error de créditos | `StudioApp.jsx` |
| Limpiar "Procesando..." al terminar el libro | `useBookSession.js` |
| SSL corporativo resuelto con truststore | `main_api.py` |
| humanize_writing activado automáticamente para ficción/YA | `architect.py` |
| VOZ VERNÁCULA: léxico cotidiano, tiempos informales, sintaxis natural | `agents/writer.py` |
| visual_context expandido a 5 campos con descripciones físicas de personajes | `agents/layouter.py` |
| _build_chapter_prompt usa todos los campos del visual_context sin truncado | `tools/cover_generator.py` |
| Primera imagen bajo el título (sin salto previo) | `tools/documents.py` |
| Portada sin nombre del autor en imagen (ya va en texto del doc) | `tools/cover_generator.py` |
| Eliminado Ideogram — Gemini único generador (v4.0) | `tools/cover_generator.py` `agents/publisher.py` `api/app.py` |
| Marcadores portada: [IDEOGRAM_PROMPT] → [IMAGE_PROMPT] | `agents/publisher.py` `tools/cover_generator.py` |
| .gitignore: excluye output/, Biblioteca/, __pycache__, node_modules/, environment.txt | `.gitignore` |
| Arranque backend con --ws-ping-interval 0 documentado | `activar-frontend.txt` |

## MEJORAS IMPLEMENTADAS — Sesión 2026-04-17

| Feature | Archivos |
|---------|----------|
| Loop confirmación entrevista (resumen numerado, corrección ítem a ítem) | `architect.py` |
| Imagen de referencia visual (upload → remix Ideogram portada + capítulos) | `app.py` `state.py` `websocket.py` `graph_runner.py` `cover_generator.py` `documents.py` `publisher.py` `StartScreen.jsx` `websocket.js` `useBookSession.js` |
| `generate_style_reference()`: genera imagen base si usuario no sube una | `cover_generator.py` |
| Retry en 400 de Ideogram con prompt seguro (soporte infantil) | `cover_generator.py` |
| Botón "← Crear otro libro" en pantalla de completado | `ChatPanel.jsx` `App.jsx` |
| Fix download path (subdir de sesión en URL) | `graph_runner.py` |
| `_is_children()` para detección de género infantil en prompts Ideogram | `cover_generator.py` |
| Regla anti-referencia en `PLAN_PROMPT` | `architect.py` |
| Desconexión WS anterior al reconectar | `useBookSession.js` |
| Orden correcto de mensajes del Arquitecto (plan antes de review_mode) | `architect.py` |
| Límites de palabras por género (`get_genre_word_limits`) diferenciados | `utils.py` `architect.py` |
| `_validate_plan` usa límites de género en vez de `max(2000,...)` hardcoded | `architect.py` |
| `_fit_image()` en documents.py — calcula dimensiones con PIL antes de insertar | `documents.py` `requirements.txt` |
| Fix doble mensaje "trabajando" — eliminar AgentStatusMessage redundante | `websocket.py` |
| Fix race condition complete/onDisconnect con `isCompleteRef` | `useBookSession.js` |
| Fix doble anidado en `_call_ideogram_remix` payload | `cover_generator.py` |

---

## REFERENCIA — Gemini Imagen (generador activo)

| Uso | Modelo | Aspect ratio |
|-----|--------|-------------|
| Portada | `imagen-4.0-generate-001` | `3:4` |
| Capítulos | `imagen-4.0-fast-generate-001` | `1:1` |
| Referencia de estilo | `imagen-4.0-fast-generate-001` | `1:1` |

**Requisito:** `GOOGLE_API_KEY` en `.env`. Sin key, las imágenes se omiten graciosamente.  
**SDK:** `google-genai>=1.0.0` (ya en `requirements.txt`).  
**SSL corporativo:** `truststore.inject_into_ssl()` en `main_api.py` — se aplica antes de cualquier llamada a la API.  
**Marcadores en Publisher prompt:** `[IMAGE_PROMPT]...[/IMAGE_PROMPT]` (antes eran `[IDEOGRAM_PROMPT]`).  
**Función pública:** `generate_cover(...)` — alias `generate_cover_with_ideogram` disponible por compatibilidad.

---

---

### E20 — `process is not defined` en consola admin

**Síntoma:** Al navegar a `/admin/solicitudes` la app explota con `process is not defined`.
**Causa:** `integrations/supabase/client.ts` usaba `process.env.SUPABASE_URL` como fallback para SSR. Vite (browser) no expone `process`.
**Archivo:** `frontend/src/integrations/supabase/client.ts`
**Fix:** Eliminar los fallbacks `process.env.*` — solo usar `import.meta.env.VITE_*`.

---

### E21 — `Reflect.get called on non-object`

**Síntoma:** Error en runtime al acceder al cliente Supabase.
**Causa:** El Proxy de Supabase llama `Reflect.get(_supabase, prop)` pero `_supabase` es `null` cuando las variables de entorno no están configuradas.
**Archivo:** `frontend/src/integrations/supabase/client.ts`
**Fix:** Agregar guarda `if (!_supabase) return undefined;` en el getter del Proxy.

---

### E22 — Variables `VITE_*` no disponibles en Vite

**Síntoma:** `import.meta.env.VITE_SUPABASE_URL` es `undefined` aunque la variable está en `.env`.
**Causa:** Vite lee `.env` desde el directorio raíz del proyecto frontend (`book-factory/frontend/`), pero el archivo `.env` está en `book-factory/`.
**Archivo:** `frontend/vite.config.js`
**Fix:** Agregar `envDir: '../'` en `vite.config.js` para que Vite lea desde `book-factory/`.

---

### E23 — `Failed to send a request to the Edge Function`

**Síntoma:** La consola admin no puede hacer login ni cargar datos.
**Causa:** Las Edge Functions de Lovable (`admin-login`, `admin-data`, etc.) solo existen en Lovable Cloud. No son accesibles desde localhost.
**Fix:** Reimplementar endpoints admin en FastAPI propio (`/api/admin/*`). Actualizar `admin.js` para llamar al backend en lugar de `supabase.functions.invoke()`.

---

### E24 — `Method Not Allowed 405` en formulario de contacto

**Síntoma:** Al enviar el formulario de contacto de la Landing page, el servidor responde 405.
**Causa:** `Landing.jsx` llamaba `supabase.functions.invoke('send-contact')` — Edge Function de Lovable que no existe localmente.
**Archivo:** `frontend/src/components/Landing.jsx`
**Fix:** Reemplazar por `fetch('/api/invites/request', ...)` que llama al backend FastAPI propio.

---

### E25 — Consola admin cuelga al asignar código

**Síntoma:** Al hacer click en "Asignar código", la pantalla se queda colgada durante ~15 segundos.
**Causa:** El envío de correo vía Resend API bloqueaba el event loop de asyncio — la llamada httpx tardaba el timeout completo (15s) en el contexto de la respuesta HTTP.
**Archivo:** `backend/api/admin.py`, `backend/api/app.py`
**Fix:** Mover el envío de correo a `BackgroundTasks` de FastAPI. La respuesta HTTP se retorna inmediatamente tras actualizar Supabase; el correo se envía después en background.

---

### E26 — `Client error 400` en `/api/admin/data`

**Síntoma:** La consola admin carga el login pero falla al cargar datos con error 400 de Supabase.
**Causa:** El campo de la tabla `contact_submissions` se llama `codigo_asignado` pero el código usaba `assigned_code`.
**Archivo:** `backend/api/admin.py`
**Fix:** Corregir a `codigo_asignado` en `select` y en el `PATCH` de asignación. También actualizar `AdminConsole.jsx` que referenciaba `s.assigned_code`.

---

### E27 — Login admin `Error 500` — columna `Estado` y contraseña bcrypt

**Síntoma:** Al intentar login admin, el backend responde 500. El log muestra `400 Bad Request` de Supabase.
**Causas (dos):**
1. Columna es `estado` (minúscula), no `Estado` — PostgREST es case-sensitive.
2. La contraseña en Supabase está hasheada con bcrypt (`$2a$10$...`), no en texto plano.
**Archivo:** `backend/api/admin.py`
**Fix:** Usar `"estado": "eq.Activo"` (minúscula) en el filtro. Importar `bcrypt` y verificar con `bcrypt.checkpw(contrasena.encode(), hash.encode())`.

---

### E28 — Preguntas de entrevista aparecen duplicadas

**Síntoma:** Al llegar al interrupt de entrevista, aparece el texto completo de las preguntas en un bubble de chat Y luego el formulario debajo — doble visualización.
**Causa:** `ChatPanel.jsx` renderizaba el `MessageBubble` con el contenido completo (intro + preguntas) y además mostraba `InterviewForm`.
**Archivo:** `frontend/src/components/ChatPanel.jsx`
**Fix:** Para mensajes `interrupt_type === 'interview'` con `questions` estructuradas, usar `extractInterviewIntro()` para mostrar solo el texto introductorio antes de la primera pregunta `**1.`.

---

### E29 — Punto 10 del resumen mezcla correo y portada

**Síntoma:** En el resumen de confirmación de respuestas, el ítem 10 dice "Contacto y portada" combinando dos campos distintos.
**Causa:** `ANSWER_SUMMARY_PROMPT` tenía hardcodeado `10. **Contacto y portada:**`.
**Archivo:** `backend/agents/architect.py`
**Fix:** Separar en `10. **Correo de contacto:**` y `11. **Preferencias de portada:**`. Actualizar también la INTERVIEW_PROMPT para que genere Q10 y Q11 como preguntas independientes.

---

### E30 — `onReset` en CompletionCard no redirige a `/acceso`

**Síntoma:** Al hacer click en "← Crear otro libro", el estado se limpia pero el usuario se queda en `/studio` (StartScreen) en lugar de volver al gate de acceso.
**Causa:** `StudioApp.jsx` pasaba `onReset={reset}` a `ChatPanel` en lugar de `onReset={handleReset}`. `reset()` limpia el estado pero no navega; `handleReset()` llama `reset()` + `navigate('/acceso')`.
**Archivo:** `frontend/src/components/StudioApp.jsx`
**Fix:** Cambiar a `onReset={handleReset}`.

---

## REFERENCIA — Límites de palabras por género

| Género | Mínimo | Máximo |
|--------|--------|--------|
| Álbum ilustrado / infantil ilustrado | 200 | 900 |
| Infantil / juvenil | 500 | 1800 |
| Young adult (12+) | 1500 | 4000 |
| Ficción adulta | 2000 | 5000 |
| Académico / ensayo | 2000 | 4500 |
| No-ficción práctica (default) | 1500 | 4000 |
