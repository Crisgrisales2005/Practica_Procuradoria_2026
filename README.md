# Preparación Sustanciador 4SU-11 (PGN)

Práctica de casos situacionales para el cargo **Sustanciador, código 4SU-11**, convocatoria 288-2026.

**Fase 9:** interfaz web propia (FastAPI + React) desplegable en **Render**. La práctica es la SPA en `frontend/`. Ingesta, vectores y Gemini siguen en el PC de administración y escriben en el mismo Supabase.

---

## Publicar la práctica (sin saber programar)

1. Aplica una sola vez la migración SQL como admin (ver [scripts/sql/DRY_RUN_FASE9.md](scripts/sql/DRY_RUN_FASE9.md)). Necesitas `psql` y la contraseña del rol web en una variable de entorno (no va en el repo).
2. Crea cuenta en [Render](https://render.com) y conecta este repositorio.
3. Crea el Web Service desde `render.yaml` (Docker).
4. Variables en Render (solo estas):
   - `DATABASE_URL` — Session pooler con usuario **`procuradoria_web.<project_ref>`** y la contraseña que usaste en el SQL.
   - `APP_PASSWORD` — **frase larga** de varias palabras (no un PIN corto). Es la contraseña que usará tu padre para entrar.
   - `SESSION_SECRET` — déjala generar a Render, o pega un secreto largo aleatorio.
5. Espera el build. Abre la URL de Render.

**Arranque en frío (importante):** con el plan free, si el servicio estuvo dormido, la **primera visita del día** muestra la pantalla de espera de **Render** (gris), no la nuestra. Puede tardar cerca de un minuto. Cuando la app ya cargó y solo la base está fría, verás dentro de la página «Despertando el servidor…» / «Conectando con la base…».

**Data API de Supabase (opcional):** en el dashboard del proyecto, si aparece la opción de desactivar la Data API / API REST, desactívala. Esta app no la usa; la migración ya cierra `anon`/`authenticated` con RLS.

---

## Migración Fase 9 (admin, una vez)

Antes de aplicar, haz un dump local de la base (carpeta `backups/` es solo en tu máquina, no va al repo). Scripts:

| Archivo | Uso |
|---|---|
| [scripts/sql/migrate_fase9_web.sql](scripts/sql/migrate_fase9_web.sql) | Forward |
| [scripts/sql/migrate_fase9_web_rollback.sql](scripts/sql/migrate_fase9_web_rollback.sql) | Reversa |
| [scripts/sql/DRY_RUN_FASE9.md](scripts/sql/DRY_RUN_FASE9.md) | Dry-run `BEGIN…ROLLBACK` y apply |

```bash
export PROCURADORIA_WEB_PASSWORD='tu frase larga aquí'
export ADMIN_DATABASE_URL='postgresql://postgres.<ref>:…@….pooler.supabase.com:5432/postgres'

# Dry-run primero (ver DRY_RUN_FASE9.md), luego:
psql "$ADMIN_DATABASE_URL" \
  -v ON_ERROR_STOP=1 \
  -v web_password="$PROCURADORIA_WEB_PASSWORD" \
  -f scripts/sql/migrate_fase9_web.sql
```

La web **no** ejecuta `init_db()` ni DDL.

Tras aplicar: smoke admin (misma URL postgres) — p. ej. `python scripts/consultar_rag.py …` e `ingest_documento.py` idempotente. El rol admin no queda sujeto a RLS (no usamos `FORCE ROW LEVEL SECURITY`).

---

## Correr la web en local

```bash
cp .env.example .env
# DATABASE_URL, APP_PASSWORD, SESSION_SECRET, SESSION_HTTPS_ONLY=0
pip install -r requirements-web.txt
# Build local del SPA (opcional; en Render el Dockerfile corre npm run build):
#   cd frontend && npm install && npm run build
uvicorn backend.app.main:app --reload --port 8000 --proxy-headers
```

Abre [http://localhost:8000](http://localhost:8000).

Docker (servicio liviano):

```bash
docker compose up --build web
```

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/test_siguiente_no_leak.py tests/test_intentos_replay.py tests/test_error_after_lock.py -q
```

E2E con el rol restringido (después de la migración):

```bash
export DATABASE_URL_WEB='postgresql://procuradoria_web.<ref>:…@….pooler.supabase.com:5432/postgres'
pytest tests/test_e2e_web_role.py -v
```

---

## Administración local (ingesta / RAG / Gemini)

Sigue igual que en fases 3–8. Usa `requirements-admin.txt` y la URL **admin** (`postgres.<ref>`), no el rol web.

### Descargar normativa

```bash
python scripts/descargar_normativa.py --insecure-ssl
```

HTML `esp_05` / `com_10`: solo descarga, sin ingesta.

### Ingerir PDFs

```bash
python scripts/ingest_documento.py --manifest manifests/ley_594_2000.yaml
# … demás manifiestos
```

### Vectores (Chroma, por máquina)

```bash
python scripts/indexar_vectores.py --reindex-all
```

### Generar / revisar ítems

```bash
python scripts/generar_items.py --all --limit 15
python scripts/revisar_items.py --last 5
```

Diagnóstico local: scripts CLI (`consultar_rag.py`, etc.), no van a la imagen de Render.

---

## Qué vive dónde

| Dónde | Uso |
|---|---|
| **Supabase** | Módulos, documentos, chunks, `chunk_modulos`, items, intentos, `srs_estado`, `presentaciones_consumidas` |
| **Render** | Solo la API + SPA (sin Gemini, sin Chroma, sin PDFs) |
| `backend/app/` | API: controllers → services → repositories → util / models |
| `data/chroma/`, `data/hf_cache/` | Vectores y embeddings **locales** (admin) |
| `documentos_entidades/pgn/` | PDFs/HTML oficiales (locales; no van al repo ni a Render) |
| `frontend/dist/` | SPA compilada (build local opcional; en Render la genera el Dockerfile) |

---

## Variables de entorno

| Variable | Notas |
|---|---|
| `DATABASE_URL` | Session pooler; en Render = rol `procuradoria_web.<ref>` |
| `APP_PASSWORD` | Frase larga de acceso a la práctica |
| `SESSION_SECRET` | Firma de cookie HttpOnly |
| `SESSION_HTTPS_ONLY` | `1` en Render; `0` en local |
| `GOOGLE_API_KEY` | Solo admin / generación; **no** en Render |

---

## Contrato rápido de la API

- `GET /api/modulos/{codigo}/siguiente` → caso, enunciado, opciones (letra+texto), `presentacion_token`. **Nunca** puntaje, matriz, justificación, norma, artículo ni `chunk_ids`.
- `POST /api/intentos` → registra en servidor y entonces devuelve matriz, cita y próximo repaso. Mismo token repetido → 200 replay. Otra pestaña que ya respondió el ítem → 409 «Esta pregunta ya fue respondida».
