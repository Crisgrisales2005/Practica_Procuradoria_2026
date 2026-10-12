-- Reversa de migrate_fase9_web.sql
-- NO restaura automáticamente los GRANT amplios de anon/authenticated
-- (habría que re-otorgarlos a mano si quisieras el estado previo inseguro).
--
--   psql "$ADMIN_DATABASE_URL" -f scripts/sql/migrate_fase9_web_rollback.sql
--
-- Tras el rollback, el progreso (items/intentos/srs_estado) NO se borra.
-- Para restaurar datos desde el dump previo: backups/pre_fase9_*/{items,intentos,srs_estado}.sql

DROP POLICY IF EXISTS procuradoria_web_select_modulos ON modulos;
DROP POLICY IF EXISTS procuradoria_web_select_items ON items;
DROP POLICY IF EXISTS procuradoria_web_update_dudoso_items ON items;
DROP POLICY IF EXISTS procuradoria_web_select_intentos ON intentos;
DROP POLICY IF EXISTS procuradoria_web_insert_intentos ON intentos;
DROP POLICY IF EXISTS procuradoria_web_all_srs ON srs_estado;
DROP POLICY IF EXISTS procuradoria_web_select_presentaciones ON presentaciones_consumidas;
DROP POLICY IF EXISTS procuradoria_web_insert_presentaciones ON presentaciones_consumidas;

ALTER TABLE IF EXISTS presentaciones_consumidas DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS modulos DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS items DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS intentos DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS srs_estado DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS documentos DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS chunks DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS chunk_modulos DISABLE ROW LEVEL SECURITY;

DROP TABLE IF EXISTS presentaciones_consumidas;

REVOKE ALL ON TABLE modulos FROM procuradoria_web;
REVOKE ALL ON TABLE items FROM procuradoria_web;
REVOKE ALL ON TABLE intentos FROM procuradoria_web;
REVOKE ALL ON TABLE srs_estado FROM procuradoria_web;
REVOKE ALL ON SEQUENCE intentos_id_seq FROM procuradoria_web;
REVOKE ALL ON SEQUENCE srs_estado_id_seq FROM procuradoria_web;
REVOKE USAGE ON SCHEMA public FROM procuradoria_web;
REVOKE CONNECT ON DATABASE postgres FROM procuradoria_web;

DROP ROLE IF EXISTS procuradoria_web;
