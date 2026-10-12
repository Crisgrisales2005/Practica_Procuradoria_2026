# Preparación Sustanciador 4SU-11 (PGN)

Aplicación local para practicar casos situacionales del cargo **Sustanciador, código 4SU-11**, convocatoria 288-2026.

Esta es la **fase 8**: descarga e ingesta de la normativa del temario (PDFs oficiales), tabla puente `chunk_modulos` para corpus compartidos (Ley 594 → `esp_06` + `com_13`) y SRS por unidad sin partir el repaso por módulo. La práctica en Streamlit (fase 7.2) sigue en Home. La base relacional vive en **Supabase (PostgreSQL)**; Chroma, embeddings y PDFs siguen en cada PC.

## Cómo levantarlo (cualquier PC)

1. Instala [Docker Desktop](https://www.docker.com/products/docker-desktop/) (en Windows incluye WSL2).
2. En esta carpeta:

   ```bash
   cp .env.example .env
   ```

3. Edita `.env`:
   - `GOOGLE_API_KEY` — [Google AI Studio](https://aistudio.google.com/apikey)
   - `DATABASE_URL` — connection string de Supabase en **Session mode (pooler)**. En el dashboard: *Connect* → *Session pooler* → URI. Debe verse un host `….pooler.supabase.com` (no solo `db.…supabase.co`: ese host suele ser **solo IPv6** y falla con `Network is unreachable` en muchas redes). Casa y trabajo usan **el mismo** valor.
4. Arranca:

   ```bash
   docker compose up --build
   ```

   La **primera** construcción es lenta (PyTorch + modelo de embeddings ~1 GB en `data/hf_cache/`). Conviene tener **16 GB de RAM**.

5. Abre [http://localhost:8501](http://localhost:8501).

Si el proyecto free de Supabase estaba dormido, la primera conexión puede tardar ~1 minuto (la app reintenta sola). Si falla del todo: abre el dashboard de Supabase, espera a que despierte y recarga.

Para detenerlo: `Ctrl+C`, o `docker compose down`.

## Primera vez en Supabase (solo en el PC que tiene el `app.db` viejo)

1. Crea un proyecto free en [Supabase](https://supabase.com) y copia `DATABASE_URL` al `.env`.
2. Migra el SQLite local (269 artículos, ítems si los hay), **preservando IDs**:

   ```bash
   python scripts/migrar_sqlite_a_postgres.py
   ```

   ```bash
   docker compose exec app python scripts/migrar_sqlite_a_postgres.py
   ```

   Es normal que `init_db` ya haya sembrado los 13 módulos: el script **no aborta** por eso. Sí aborta si `documentos`/`chunks`/`items`/… ya tienen filas (usa `--force` solo si quieres reescribir esas tablas).

3. En el otro PC: mismo `.env` con el mismo `DATABASE_URL`. **No** vuelvas a migrar.

## Descargar normativa (fase 8)

Las URLs oficiales están en `manifests/descargas_normativa.yaml` (lista estática; sin descubrimiento).

```bash
python scripts/descargar_normativa.py --insecure-ssl
```

`--insecure-ssl` evita fallos por cadenas SSL incompletas en algunos `.gov.co`. Los HTML de `esp_05` / `com_10` se descargan pero **no** se ingieren en esta fase.

## Ingerir PDFs

El Decreto Ley 262 ya puede estar en Supabase. El resto del corpus:

```bash
python scripts/ingest_documento.py --manifest manifests/constitucion_politica_1991.yaml
python scripts/ingest_documento.py --manifest manifests/ley_2220_2022.yaml
python scripts/ingest_documento.py --manifest manifests/ley_1437_2011.yaml
python scripts/ingest_documento.py --manifest manifests/ley_594_2000.yaml   # esp_06 + com_13
python scripts/ingest_documento.py --manifest manifests/codigo_general_disciplinario.yaml
python scripts/ingest_documento.py --manifest manifests/manual_mipg_v6_1.yaml
```

Ley 594 crea **un** chunk por artículo y lo enlaza a ambos módulos vía `chunk_modulos`. El SRS comparte la misma unidad de repaso (UNIQUE sin `modulo_id`).

Antes de cambiar ese UNIQUE en una DB que ya tenga `srs_estado`:

```bash
python scripts/verificar_srs_colisiones.py
```

(`init_db` / `migrar_fase8_esquema` consolida colisiones si las hubiera y aplica el constraint.)

## Indexar vectores (Chroma, **local por máquina**)

Los vectores **no** viajan con Supabase. En **cada PC nuevo** (o tras borrar `data/chroma/`):

```bash
python scripts/indexar_vectores.py --reindex-all
```

```bash
docker compose exec app python scripts/indexar_vectores.py --reindex-all
```

**Importante:** sin `--reindex-all`, el script solo mira `chroma_id` vacío en Postgres. Tras migrar, esa columna ya está llena (la llenó el otro PC) y el Chroma local estaría vacío → el RAG fallaría en silencio. En la primera indexación de una máquina usa siempre `--reindex-all`.

## Probar la búsqueda

```bash
python scripts/consultar_rag.py --modulo esp_08 --query "funciones del Procurador General"
```

`com_11` sin corpus → `sin resultados`.

## Generar y revisar ítems

Igual que en la fase 5 (cuota Gemini aparte):

```bash
python scripts/generar_items.py --modulo esp_08 --limit 10 --dry-run
python scripts/generar_items.py --all --limit 15
python scripts/revisar_items.py --last 5
```

## Probar SRS (fase 6)

La repetición espaciada vive en backend (SM-2 adaptado a 5/2/0). No hace falta Streamlit ni Gemini.

```bash
# Responder un ítem (crea/actualiza intentos + srs_estado)
python scripts/simular_intento.py --item-id 3 --puntaje 5
python scripts/simular_intento.py --item-id 3 --puntaje 0

# Siguiente a practicar: vencidos antes que nuevos; excluye dudoso=1
python scripts/siguiente_practica.py --modulo esp_08

# Estado SRS del módulo
python scripts/consultar_srs.py --modulo esp_08

# Marcar / quitar dudoso (no borra el ítem)
python scripts/simular_intento.py --item-id 3 --marcar-dudoso
python scripts/simular_intento.py --item-id 3 --quitar-dudoso
```

Regla rápida: **5** alarga el intervalo y sube el ease; **2** vuelve en 1 día; **0** queda vencido de inmediato.

## Practicar en pantalla (fase 7 / 7.1 / 7.2)

La práctica diaria es la página principal de Streamlit (Home). El diagnóstico (RAG, conteos) quedó en la página lateral **Diagnóstico**.

```bash
streamlit run frontend/app.py
# o: docker compose up  → abrir el puerto de Streamlit
```

Flujo: elige módulo (`esp_08`) → marca una letra (Responder está deshabilitado hasta elegir) → ve la matriz completa → Siguiente o Ítem dudoso. Sin Gemini en esta pantalla.

**Fase 7.1 / 7.2:**

- En Home, panel **Progreso de práctica** con métricas (Para hoy / Nuevos / Programados / Dudosos / Aciertos óptimos / Parciales / Fallos) y racha de últimos intentos (verde 5, amarillo 2, rojo 0; más reciente a la derecha). Fallos = intentos con puntaje 0 en la tabla `intentos`. No predice el examen oficial.
- El aviso de no garantía aparece bajo el panel y otra vez al pie (a propósito).
- Casos nuevos salen más narrativos tras el ajuste del prompt; hay que **regenerar** ítems para verlo (`generar_items.py`).
- Al guardar un ítem, las 4 opciones se **barajan** y se reasignan letras A–D (la óptima no queda fija en D).
- Latencia: pool Postgres con `close_returns=True` (psycopg-pool ≥ 3.3) + resumen sin N+1; `conn.close()` de los callers actuales recicla la conexión.

## Qué queda en el disco vs en la nube

| Dónde | Uso |
|---|---|
| **Supabase (Postgres)** | Módulos, documentos, artículos, `chunk_modulos`, `items`, `intentos`, `srs_estado`, `chroma_id` (solo el ID de texto) |
| `data/chroma/` | Vectores **locales** (no se sincronizan) |
| `data/hf_cache/` | Modelo de embeddings local |
| `documentos_entidades/pgn/` | PDFs/HTML oficiales en cada PC |
| `manifests/descargas_normativa.yaml` | URLs de descarga (estático) |
| `data/sqlite/app.db` | **Legado** tras migrar (respaldo; ya no es la fuente de verdad) |
| `data/sqlite/generation.log` | Log opcional de generación |
| `prompts/evaluator_elite_pgn.xml` | System prompt de generación |
| `manifests/queries_generacion.yaml` | Queries del lote |

## Variables de entorno

| Variable | Valor por defecto | Notas |
|---|---|---|
| `DATABASE_URL` | (vacía) | Obligatoria. URI Postgres de Supabase, Session mode |
| `GOOGLE_API_KEY` | (vacía) | Obligatoria para generar (no para `--dry-run`) |
| `GENERATION_PROVIDER` | `gemini` | `gemini` u `ollama` (ollama no implementado) |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama en el PC |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Una llamada por ítem |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-mpnet-base-v2` | Español, local |
| `CHROMA_COLLECTION` | `pgn_articulos` | Colección embebida local |
| `RAG_MIN_SCORE` | `0.35` | Sin hits ≥ umbral no hay llamada a Gemini |

## Motor local (más adelante)

Ollama es un respaldo opcional cuando no hay internet. No forma parte de `docker compose`.
