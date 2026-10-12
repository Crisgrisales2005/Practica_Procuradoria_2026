"""Acceso a PostgreSQL (Supabase): siempre vía get_connection / init_db / consultas."""

from backend.db.connection import (
    DatabaseError,
    contar_chunks,
    contar_chunks_vectorizados,
    contar_items,
    ensure_pool,
    get_connection,
    init_db,
    listar_documentos,
    listar_items_recientes,
    listar_modulos,
    obtener_item,
)

__all__ = [
    "DatabaseError",
    "contar_chunks",
    "contar_chunks_vectorizados",
    "contar_items",
    "ensure_pool",
    "get_connection",
    "init_db",
    "listar_documentos",
    "listar_items_recientes",
    "listar_modulos",
    "obtener_item",
]
