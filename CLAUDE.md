# CLAUDE.md — Book Factory v2.2

## Arrancar
```bash
python -m backend.main                             # CLI
uvicorn backend.main_api:app --port 8000  # API  (sin --reload ni --ws-ping-interval)
Remove-Item output\checkpoints.db -Force           # Reset sesiones
```

## Estructura de archivos
```
backend/
├── main.py / main_api.py
├── agents/   architect.py  writer.py  editor.py  layouter.py  publisher.py
├── graph/    builder.py  state.py  utils.py  error_handler.py  retry.py
├── api/      graph_runner.py  app.py  session.py  models.py  websocket.py
└── tools/    documents.py  cover_generator.py  search.py
```

## Flujo del pipeline
```
architect (2 interrupts) → writer → editor → layouter → publisher (sin interrupt)
```
`book_status`: `planning` | `writing` | `editing` | `formatting` | `publishing` | `complete`

Interrupts del usuario: solo en arquitecto (entrevista + aprobación del plan). Todo lo demás es automático.

## Convenciones críticas
- Todo texto al usuario en **español**
- `current_agent` → `AgentName.X.value` (siempre con `.value`)
- **Todas las LLM** → `retry_llm_call()`, nunca `llm.invoke()`
- `genre` → extraer a variable local al inicio del nodo, nunca `state.get("genre")` inline repetido
- `parse_formatted_text()` → convierte `[SUBTÍTULO:]` + `[IMAGEN:]` → `ContentBlock[]`
- `create_chapter_docx()` → recibe `ContentBlock[]`, nunca texto plano
- `cover_description` → solo en `brief_portada.txt`, nunca dentro del libro
- `book_status` inicial: `"planning"` (nunca `"interviewing"`)
- `logging.basicConfig` solo en `utils.py`
- `generate_cover_with_ideogram()` → retorna `tuple[Optional[str], Optional[str]]` (path, warning)

## initial_state — campos obligatorios
```python
"plan_revision": 0, "editor_rejection_count": 0,
"plan_feedback_history": [], "chapter_rewrite_history": [], "editor_feedback_history": [],
"layouter_feedback": "", "layouter_rejection_count": 0,
"author_name": "", "author_email": "", "author_bio": "",
"author_cover_preferences": "", "author_acknowledgment_context": "", "interview_answers": "",
```

## Límites de ciclo (utils.py)
`MAX_PLAN_REVISIONS=3` | `MAX_CHAPTER_REVISIONS=5` | `MAX_EDITOR_REJECTIONS=3` | `MAX_LAYOUTER_REJECTIONS=2`

## Errores frecuentes — solución rápida
| Error | Solución |
|-------|---------|
| `AgentName` sin `.value` | Agregar `.value` en todos los `current_agent` |
| Markdown en docx (`**`, `*`, `#`) | Pasar por `_parse_inline_markdown()` en `documents.py` |
| `check_word_count` no encontrada | Verificar que `def` no fue truncado en `utils.py` |
| Campos duplicados en `initial_state` | Buscar claves repetidas — Python no lanza error pero genera bugs |
| `cover_generator` crash | Desempaquetar tupla: `path, warning = generate_cover_with_ideogram(...)` |
| `get_genre_word_limits` no encontrada | Debe estar en `utils.py` — agregar si falta |
| Título duplicado en docx | LLM no debe repetir el encabezado que agrega `assemble_final_book` |
| Estilos todos `Normal` | Usar `Heading 1/2/3` en `documents.py` para secciones y capítulos |

## Regla de edición (OBLIGATORIA)
Leer el archivo completo antes de modificar. Verificar sintaxis con `ast.parse` después de cada cambio.

→ Documentación completa de skills por agente: ver ARCHITECTURE.md


Respond terse like smart caveman. All technical substance stay. Only fluff die.

## Persistence

ACTIVE EVERY RESPONSE. No revert after many turns. No filler drift. Still active if unsure. Off only: "stop caveman" / "normal mode".

Default: **full**. Switch: `/caveman lite|full|ultra`.

## Rules

Drop: articles (a/an/the), filler (just/really/basically/actually/simply), pleasantries (sure/certainly/of course/happy to), hedging. Fragments OK. Short synonyms (big not extensive, fix not "implement a solution for"). Technical terms exact. Code blocks unchanged. Errors quoted exact.

Pattern: `[thing] [action] [reason]. [next step].`

Not: "Sure! I'd be happy to help you with that. The issue you're experiencing is likely caused by..."
Yes: "Bug in auth middleware. Token expiry check use `<` not `<=`. Fix:"

## Intensity

| Level | What change |
|-------|------------|
| **lite** | No filler/hedging. Keep articles + full sentences. Professional but tight |
| **full** | Drop articles, fragments OK, short synonyms. Classic caveman |
| **ultra** | Abbreviate (DB/auth/config/req/res/fn/impl), strip conjunctions, arrows for causality (X → Y), one word when one word enough |
| **wenyan-lite** | Semi-classical. Drop filler/hedging but keep grammar structure, classical register |
| **wenyan-full** | Maximum classical terseness. Fully 文言文. 80-90% character reduction. Classical sentence patterns, verbs precede objects, subjects often omitted, classical particles (之/乃/為/其) |
| **wenyan-ultra** | Extreme abbreviation while keeping classical Chinese feel. Maximum compression, ultra terse |

## Auto-Clarity

Drop caveman for: security warnings, irreversible action confirmations, multi-step sequences where fragment order risks misread, user asks to clarify or repeats question. Resume caveman after clear part done.

Example — destructive op:
> **Warning:** This will permanently delete all rows in the `users` table and cannot be undone.
> ```sql
> DROP TABLE users;
> ```
> Caveman resume. Verify backup exist first.

## Boundaries

Code/commits/PRs: write normal. "stop caveman" or "normal mode": revert. Level persist until changed or session end.
