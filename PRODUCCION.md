# PRODUCCION.md — Guía de despliegue a producción

> Estado actual: **Beta cerrada** (local). Próximo paso: despliegue en servidor.

---

## Checklist antes de ir a producción

### Seguridad — OBLIGATORIO

- [ ] **Rotar TODAS las API keys** (Anthropic, Google, Tavily)
  - Anthropic: https://console.anthropic.com → API Keys → Create New Key → revocar la actual
  - Google: https://console.cloud.google.com → APIs & Services → Credentials
  - Tavily: https://app.tavily.com → API Keys
- [ ] Mover `INVITE_CODES` a variable de entorno del servidor (no en código)
- [ ] Configurar `ALLOWED_ORIGINS` con el dominio real (no `localhost`)
- [ ] Verificar que `.env` NO está en el repositorio (ya está en `.gitignore`)
- [ ] JWT authentication para sesiones (actualmente solo sessionStorage)
- [ ] HTTPS obligatorio (certificado TLS — Let's Encrypt o del proveedor cloud)
- [ ] Encriptación de PII en `checkpoints.db` (author_email, author_name)

### Infraestructura

- [ ] Elegir proveedor cloud (Railway, Render, DigitalOcean, AWS, GCP)
- [ ] Configurar variables de entorno en el proveedor (no en archivos)
- [ ] Volumen persistente para `output/` y `Biblioteca/`
- [ ] Dominio propio configurado con DNS
- [ ] Configurar `OUTPUT_RETENTION_DAYS` según política de privacidad

### Cumplimiento legal (Chile — Ley 21.719 vigente desde dic. 2026)

- [ ] Términos de servicio publicados con el procesamiento de datos explicado
- [ ] Política de privacidad completa (qué se recopila, con qué fin, por cuánto tiempo)
- [ ] Mecanismo de solicitud de borrado de datos (endpoint o email de contacto)
- [ ] Acuerdo DPA con Anthropic (transferencia de datos a EE.UU.)
- [ ] Registro de tratamiento de datos personales

### Rendimiento y monitoreo

- [ ] Configurar logging a servicio externo (Papertrail, Datadog, Logtail)
- [ ] Alertas de errores 5xx
- [ ] Monitoreo de créditos Anthropic (webhook o dashboard)
- [ ] Límite de sesiones concurrentes (actualmente sin límite hard)
- [ ] CDN para assets del frontend (Cloudflare Pages o similar)

---

## Opciones de despliegue recomendadas

### Opción A — Railway (más simple, recomendado para MVP)

```bash
# 1. Instalar Railway CLI
npm install -g @railway/cli
railway login

# 2. Desde book-factory/
railway init
railway up

# 3. Variables de entorno en Railway dashboard
# Agregar todas las del .env excepto INVITE_CODES (usar Railway secrets)
```

**Ventajas:** Deploy desde git push, volúmenes persistentes, SSL automático.  
**Costo estimado:** ~$20-30 USD/mes para uso beta.

### Opción B — Docker Compose en VPS

El proyecto ya tiene `docker-compose.yml` y `Dockerfile.api`.  
Falta: `Dockerfile.frontend` (ya existe en `frontend/`).

```bash
# En servidor:
docker compose up -d

# Nginx como reverse proxy con SSL (certbot):
apt install certbot python3-certbot-nginx
certbot --nginx -d tudominio.com
```

**Ventajas:** Control total, más barato a largo plazo.  
**Costo estimado:** VPS ~$10-20 USD/mes + dominio.

### Opción C — Serverless (más complejo)

- Backend: Google Cloud Run o AWS Lambda (requiere adaptar uvicorn → asgi handler)
- Frontend: Vercel o Netlify (gratis)
- WebSocket: requiere servicio separado (Cloud Run con websockets habilitados)

---

## Variables de entorno para producción

```env
# Obligatorias
ANTHROPIC_API_KEY=sk-ant-...           # ROTAR antes de producción
GOOGLE_API_KEY=AIza...                  # ROTAR antes de producción
ANTHROPIC_MODEL=claude-sonnet-4-6

# Opcionales
TAVILY_API_KEY=tvly-...                # Para no-ficción/académico
OUTPUT_DIR=/data/output                # Ruta en el volumen persistente
OUTPUT_RETENTION_DAYS=30

# Seguridad
INVITE_CODES=OBRA-BETA-001,...         # Nuevos códigos para producción
ALLOWED_ORIGINS=https://tudominio.com

# Puerto
PORT=8000
HOST=0.0.0.0
```

---

## Pendientes técnicos para producción

| Prioridad | Item | Esfuerzo |
|-----------|------|---------|
| ALTA | Rotar API keys | 15 min |
| ALTA | HTTPS + dominio | 1-2 h |
| ALTA | Variables de entorno en servidor | 30 min |
| ALTA | JWT authentication (reemplaza sessionStorage) | 1 día |
| MEDIA | Encriptación PII en checkpoint | 4 h |
| MEDIA | Logging centralizado | 2 h |
| MEDIA | Mecanismo de borrado de datos por solicitud | 4 h |
| BAJA | Rate limiting con Redis (en lugar de in-memory) | 4 h |
| BAJA | Métricas de uso (libros generados, géneros, etc.) | 1 día |

---

## Comandos útiles

```bash
# Arrancar backend local con configuración de producción
uvicorn backend.main_api:app --port 8000 --ws-ping-interval 0 --host 0.0.0.0

# Build del frontend para producción
cd frontend && npm run build
# El dist/ es servido automáticamente por el backend en /

# Verificar que el backend levanta correctamente
curl http://localhost:8000/health

# Verificar invitaciones
curl -X POST http://localhost:8000/api/verify-invite \
  -H "Content-Type: application/json" \
  -d '{"code": "OBRA-ALPHA-001"}'

# Ver logs en tiempo real
tail -f /tmp/backend.log
```

---

## Arquitectura de producción objetivo

```
Internet
    │
    ▼
[Cloudflare/CDN]  ← SSL termination, DDoS protection
    │
    ▼
[Nginx/Reverse Proxy]
    ├── / → frontend dist (estático)
    ├── /api/ → Backend FastAPI (puerto 8000)
    └── /ws/ → Backend WebSocket (puerto 8000)
         │
         ▼
    [FastAPI + LangGraph]
         ├── Anthropic API (Claude Sonnet/Haiku)
         └── Google Gemini API (Imagen 4)
         
    Persistencia:
    ├── output/checkpoints.db (SQLite — sesiones activas)
    └── Biblioteca/ (DOCX finalizados)
```

---

*Última actualización: 2026-05-11*
