-- Fase 9: presentaciones_consumidas + rol procuradoria_web + RLS + revoke API pública.
-- NO contiene la contraseña del rol. Pasarla solo por psql:
--
--   export PROCURADORIA_WEB_PASSWORD='tu frase larga aquí'
--   psql "$ADMIN_DATABASE_URL" \
--     -v web_password="$PROCURADORIA_WEB_PASSWORD" \
--     -f scripts/sql/migrate_fase9_web.sql
--
-- Valor SIN comillas extras en -v; el SQL usa :'web_password'.
-- Dry-run: ver scripts/sql/DRY_RUN_FASE9.md (BEGIN … ROLLBACK).
-- El agente NO aplica este script; lo aplica el admin a mano tras confirmar.

-- ---------------------------------------------------------------------------
-- 1) Tabla de presentaciones (idempotencia de intentos web)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS presentaciones_consumidas (
    presentacion_id TEXT PRIMARY KEY,
    item_id BIGINT NOT NULL REFERENCES items(id),
    intento_id BIGINT NOT NULL REFERENCES intentos(id),
    letra_elegida TEXT NOT NULL CHECK (letra_elegida IN ('A', 'B', 'C', 'D')),
    puntaje INTEGER NOT NULL CHECK (puntaje IN (0, 2, 5)),
    creado_en TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_presentaciones_item
    ON presentaciones_consumidas (item_id);

-- ---------------------------------------------------------------------------
-- 2) Rol de la web (password solo vía :'web_password')
-- ---------------------------------------------------------------------------
-- Si el rol ya existe, CREATE ROLE fallará: en ese caso usa solo
--   ALTER ROLE procuradoria_web LOGIN PASSWORD :'web_password';
CREATE ROLE procuradoria_web LOGIN PASSWORD :'web_password';

-- En Session pooler de Supabase el usuario de conexión es:
--   procuradoria_web.<project_ref>
-- (mismo sufijo que postgres.<project_ref>).

GRANT CONNECT ON DATABASE postgres TO procuradoria_web;
GRANT USAGE ON SCHEMA public TO procuradoria_web;

-- Catálogo de práctica
GRANT SELECT ON TABLE modulos TO procuradoria_web;
GRANT SELECT ON TABLE items TO procuradoria_web;
GRANT UPDATE (dudoso) ON TABLE items TO procuradoria_web;

GRANT SELECT, INSERT ON TABLE intentos TO procuradoria_web;
GRANT SELECT, INSERT, UPDATE ON TABLE srs_estado TO procuradoria_web;
GRANT SELECT, INSERT ON TABLE presentaciones_consumidas TO procuradoria_web;

-- Sequences IDENTITY (INSERT)
GRANT USAGE, SELECT ON SEQUENCE intentos_id_seq TO procuradoria_web;
GRANT USAGE, SELECT ON SEQUENCE srs_estado_id_seq TO procuradoria_web;
-- presentaciones_consumidas no usa sequence (PK TEXT)

-- Explicitamente SIN grants sobre chunks / documentos / chunk_modulos.

-- ---------------------------------------------------------------------------
-- 3) Cerrar API pública (anon / authenticated) + RLS sin FORCE
-- ---------------------------------------------------------------------------
REVOKE ALL ON TABLE modulos FROM anon, authenticated, PUBLIC;
REVOKE ALL ON TABLE items FROM anon, authenticated, PUBLIC;
REVOKE ALL ON TABLE intentos FROM anon, authenticated, PUBLIC;
REVOKE ALL ON TABLE srs_estado FROM anon, authenticated, PUBLIC;
REVOKE ALL ON TABLE documentos FROM anon, authenticated, PUBLIC;
REVOKE ALL ON TABLE chunks FROM anon, authenticated, PUBLIC;
REVOKE ALL ON TABLE chunk_modulos FROM anon, authenticated, PUBLIC;
REVOKE ALL ON TABLE presentaciones_consumidas FROM anon, authenticated, PUBLIC;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON TABLES FROM anon, authenticated, PUBLIC;

ALTER TABLE modulos ENABLE ROW LEVEL SECURITY;
ALTER TABLE items ENABLE ROW LEVEL SECURITY;
ALTER TABLE intentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE srs_estado ENABLE ROW LEVEL SECURITY;
ALTER TABLE documentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunk_modulos ENABLE ROW LEVEL SECURITY;
ALTER TABLE presentaciones_consumidas ENABLE ROW LEVEL SECURITY;
-- NO usar FORCE ROW LEVEL SECURITY: el owner/admin sigue sin quedar sujeto a RLS.

-- Policies solo para procuradoria_web (conexión directa psycopg).
-- Sin policies para anon/authenticated → PostgREST no ve filas útiles.

DROP POLICY IF EXISTS procuradoria_web_select_modulos ON modulos;
CREATE POLICY procuradoria_web_select_modulos ON modulos
    FOR SELECT TO procuradoria_web USING (true);

DROP POLICY IF EXISTS procuradoria_web_select_items ON items;
CREATE POLICY procuradoria_web_select_items ON items
    FOR SELECT TO procuradoria_web USING (true);

DROP POLICY IF EXISTS procuradoria_web_update_dudoso_items ON items;
CREATE POLICY procuradoria_web_update_dudoso_items ON items
    FOR UPDATE TO procuradoria_web USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS procuradoria_web_select_intentos ON intentos;
CREATE POLICY procuradoria_web_select_intentos ON intentos
    FOR SELECT TO procuradoria_web USING (true);

DROP POLICY IF EXISTS procuradoria_web_insert_intentos ON intentos;
CREATE POLICY procuradoria_web_insert_intentos ON intentos
    FOR INSERT TO procuradoria_web WITH CHECK (true);

DROP POLICY IF EXISTS procuradoria_web_all_srs ON srs_estado;
CREATE POLICY procuradoria_web_all_srs ON srs_estado
    FOR ALL TO procuradoria_web USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS procuradoria_web_select_presentaciones ON presentaciones_consumidas;
CREATE POLICY procuradoria_web_select_presentaciones ON presentaciones_consumidas
    FOR SELECT TO procuradoria_web USING (true);

DROP POLICY IF EXISTS procuradoria_web_insert_presentaciones ON presentaciones_consumidas;
CREATE POLICY procuradoria_web_insert_presentaciones ON presentaciones_consumidas
    FOR INSERT TO procuradoria_web WITH CHECK (true);

-- documentos / chunks / chunk_modulos: RLS on, sin policy para web ni anon
-- → API pública cerrada; web no necesita esas tablas.
