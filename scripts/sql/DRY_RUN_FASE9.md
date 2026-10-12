# Dry-run y apply — migración Fase 9 (admin)

El agente **no** aplica este SQL a Supabase. Tú lo haces como admin cuando confirmes.

## Dump previo

Ya generado (no lo borres hasta confirmar que la migración quedó bien):

- Ver puntero: `backups/LATEST_PRE_FASE9.txt`
- Contenido típico: `items.json` / `intentos.json` / `srs_estado.json` y `.sql` equivalentes

## Contraseña del rol

```bash
export PROCURADORIA_WEB_PASSWORD='una frase larga de varias palabras'
# NUNCA commits esta variable ni pegues la password en el .sql
```

## Dry-run (no deja cambios)

Con `psql` instalado localmente:

```bash
export ADMIN_DATABASE_URL='postgresql://postgres.<ref>:<pass>@….pooler.supabase.com:5432/postgres'

psql "$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 -v web_password="$PROCURADORIA_WEB_PASSWORD" <<'EOSQL'
BEGIN;
\i scripts/sql/migrate_fase9_web.sql
ROLLBACK;
EOSQL
```

Si algo falla, no queda aplicado.  
Nota: `CREATE ROLE` es transaccional en PostgreSQL moderno; el `ROLLBACK` deshace el rol de prueba.

## Apply (solo con tu confirmación explícita)

```bash
psql "$ADMIN_DATABASE_URL" \
  -v ON_ERROR_STOP=1 \
  -v web_password="$PROCURADORIA_WEB_PASSWORD" \
  -f scripts/sql/migrate_fase9_web.sql
```

Luego configura Render / `.env` web con:

```text
DATABASE_URL=postgresql://procuradoria_web.<project_ref>:<PROCURADORIA_WEB_PASSWORD>@….pooler.supabase.com:5432/postgres
```

(mismo host Session pooler; usuario con sufijo del proyecto).

## Rollback

```bash
psql "$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/sql/migrate_fase9_web_rollback.sql
```

No reabre automáticamente los GRANT de `anon`/`authenticated` (a propósito: ese estado era inseguro).
