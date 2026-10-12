"""Orquesta RAG → umbral → Gemini → validar → guardar. Sin cola ni worker."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from backend.config import settings
from backend.generation.client import (
    ESPACIADO_SEGUNDOS,
    CuotaDia,
    CuotaMinutoAgotada,
    DisponibilidadAgotada,
    GeneracionError,
    ProveedorNoSoportado,
    generar_json,
)
from backend.generation.persist import guardar_item
from backend.generation.prompt import armar_user_message, cargar_system_prompt
from backend.generation.validate import MAX_INTENTOS_FORMATO, ItemInvalido, validar_respuesta
from backend.rag.retrieve import Hit, recuperar

QUERIES_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "manifests"
    / "queries_generacion.yaml"
)


@dataclass
class ResultadoLote:
    """Acumulado de una corrida de generación.

    Variables:
        ok: ítems guardados.
        omitidos_sin_rag: queries cuyo mejor artículo no superó el umbral.
        omitidos_advertencia: el modelo dijo que el fragmento no alcanzaba.
        fail_json: respuestas que no pasaron la validación tras 3 intentos.
        n_429_minuto: reintentos por límite de minuto.
        n_disponibilidad: reintentos por error 5xx.
        detenido_por_cuota_diaria: la corrida paró porque se acabó la cuota del día.
        detenido_por_disponibilidad: paró por tres 5xx seguidos.
        ids_insertados: ids nuevos en `items`.
        llamadas_api: llamadas a Gemini, contando reintentos de formato.
        ultimo_modulo / ultima_query: dónde quedó la corrida si se detuvo.
    """
    ok: int = 0
    omitidos_sin_rag: int = 0
    omitidos_advertencia: int = 0
    fail_json: int = 0
    n_429_minuto: int = 0
    n_disponibilidad: int = 0
    detenido_por_cuota_diaria: bool = False
    detenido_por_disponibilidad: bool = False
    ids_insertados: list[int] = field(default_factory=list)
    llamadas_api: int = 0
    ultimo_modulo: str = ""
    ultima_query: str = ""

    def resumen(self) -> str:
        """Arma el texto de cierre con conteos y si la corrida se detuvo.

        Variables:
            diario: `sí` o `no`, según `detenido_por_cuota_diaria`.
            disp: `sí` o `no`, según `detenido_por_disponibilidad`.

        Devuelve: dos líneas: los conteos y la estimación de llamadas (techo 500 al día).
        """
        diario = "sí" if self.detenido_por_cuota_diaria else "no"
        disp = "sí" if self.detenido_por_disponibilidad else "no"
        return (
            f"OK={self.ok}  omitidos_sin_rag={self.omitidos_sin_rag}  "
            f"omitidos_advertencia={self.omitidos_advertencia}  "
            f"fail_json={self.fail_json}  429_minuto={self.n_429_minuto}  "
            f"disponibilidad={self.n_disponibilidad}  "
            f"detenido_por_cuota_diaria={diario}  "
            f"detenido_por_disponibilidad={disp}\n"
            f"estimacion_llamadas_api={self.llamadas_api}  (techo RPD 500)"
        )


class LoteAbortado(Exception):
    """La corrida se cortó por cuota diaria, límite por minuto o API caída.

    Variables:
        motivo: `cuota_dia`, `cuota_minuto` o `disponibilidad`.
        resultado: el `ResultadoLote` con lo que ya se había guardado.
    """

    def __init__(self, motivo: str, resultado: ResultadoLote) -> None:
        """Guarda el motivo y el acumulado para que el script decida el código de salida.

        Variables:
            motivo: por qué se abortó.
            resultado: conteos e ids ya insertados.
        """
        self.motivo = motivo
        self.resultado = resultado
        super().__init__(motivo)


def cargar_queries(path: Path | None = None) -> dict[str, list[str]]:
    """Lee las consultas de generación, agrupadas por código de módulo.

    Cómo: abre el YAML (por defecto `manifests/queries_generacion.yaml`), toma
    el mapa `modulos` y se queda con las frases que no están vacías.

    Variables:
        path: otro YAML, si se quiere. None usa `QUERIES_PATH`.
        archivo: ruta que se lee de verdad.
        data: documento YAML.
        modulos: mapa código → lista de frases.
        out: el mismo mapa, ya limpiado.
        codigo: clave del módulo.
        queries: lista cruda de ese módulo.

    Devuelve: por ejemplo `{"esp_08": ["funciones del Procurador", ...]}`.
    """
    archivo = path or QUERIES_PATH
    data = yaml.safe_load(archivo.read_text(encoding="utf-8")) or {}
    modulos = data.get("modulos") or {}
    out: dict[str, list[str]] = {}
    for codigo, queries in modulos.items():
        if not isinstance(queries, list):
            continue
        out[str(codigo)] = [str(q).strip() for q in queries if str(q).strip()]
    return out


def hits_por_umbral(hits: list[Hit], min_score: float, max_inyectar: int = 1) -> list[Hit]:
    """Se queda con el artículo que supera el umbral, como máximo uno.

    Cómo: filtra los hits con `score >= min_score`. Chroma ya los trae del más
    parecido al menos parecido, así que el primero que pasa es el mejor.
    `max_inyectar` existe por compatibilidad, pero el corte final es siempre 1:
    cada ítem se redacta con un solo artículo.

    Variables:
        hits: resultados de `recuperar`, ordenados por score.
        min_score: umbral, normalmente `RAG_MIN_SCORE` (0.35).
        max_inyectar: tope pedido. El valor efectivo queda en 1.
        ok: hits que superan el umbral.

    Devuelve: una lista de 0 o 1 hit.
    """
    ok = [h for h in hits if h.score >= min_score]
    if not ok:
        return []
    return ok[: max(1, max_inyectar)][:1]


def _log(linea: str) -> None:
    """Añade una línea con fecha UTC a `data/logs/generation.log`.

    Cómo: crea la carpeta si falta y abre el archivo en modo añadir.

    Variables:
        linea: mensaje, por ejemplo un FAIL o un omitido.
        path: ruta del log.
        stamp: fecha UTC del renglón.
    """
    settings.ensure_logs_dir()
    path = settings.logs_dir / "generation.log"
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {linea}\n")


def _esperar_espaciado(ultimo_inicio: float | None) -> float:
    """Espera lo que falte para separar las llamadas a Gemini 7 segundos.

    Cómo: compara el reloj monotónico con `ultimo_inicio`. Si han pasado menos
    de `ESPACIADO_SEGUNDOS` (7), duerme la diferencia. La primera llamada, con
    `ultimo_inicio` en None, no espera.

    Variables:
        ultimo_inicio: instante monotónico en que empezó la llamada anterior, o None.
        ahora: instante actual.
        falta: segundos que todavía hay que dormir.

    Devuelve: el instante en que esta llamada puede empezar.
    """
    ahora = time.monotonic()
    if ultimo_inicio is not None:
        falta = ESPACIADO_SEGUNDOS - (ahora - ultimo_inicio)
        if falta > 0:
            time.sleep(falta)
            ahora = time.monotonic()
    return ahora


def generar_un_item(
    modulo_codigo: str,
    query: str,
    hits: list[Hit],
    system: str,
    *,
    entidad: str,
    dry_run: bool,
    ultimo_inicio: float | None,
) -> tuple[str, int | None, int, int, int, float | None]:
    """Redacta y guarda una pregunta a partir de una query y su artículo.

    Cómo: en dry-run no llama a la API. En una corrida real arma el mensaje,
    espera el espaciado de 7 segundos y pide JSON. Si la validación falla,
    reintenta hasta 3 veces (`MAX_INTENTOS_FORMATO`). Una advertencia del modelo
    omite el ítem. Un JSON válido se guarda con `guardar_item`.

    Variables:
        modulo_codigo: módulo de la query.
        query: frase de búsqueda que se usó en el RAG.
        hits: artículos que superaron el umbral. Se usa el primero.
        system: prompt maestro XML.
        entidad: organismo que se escribe en `items`.
        dry_run: True evita la llamada y el INSERT.
        ultimo_inicio: instante de la llamada anterior, para el espaciado.
        user: mensaje de usuario armado con el fragmento.
        llamadas: cuántas veces se llamó a Gemini en esta pregunta.
        n_429 / n_disp: reintentos por minuto y por disponibilidad.
        ultimo: instante actualizado tras cada espera.
        ultima_razon: `json` o `citas`, la del último fallo de formato.
        raw: texto devuelto por el modelo.
        item: ítem ya validado.
        item_id: id insertado cuando el estado es `ok`.

    Devuelve: `(estado, item_id, llamadas, n_429, n_disp, nuevo_ultimo_inicio)`.
    `estado` es `dry_run`, `ok`, `advertencia`, `fail_json`, `cuota_dia`,
    `cuota_minuto` o `disponibilidad`. `item_id` solo viene en `ok`.
    """
    if dry_run:
        return "dry_run", None, 0, 0, 0, ultimo_inicio

    user = armar_user_message(modulo_codigo, hits)
    llamadas = 0
    n_429 = 0
    n_disp = 0
    ultimo = ultimo_inicio
    ultima_razon = "json"

    for _intento in range(1, MAX_INTENTOS_FORMATO + 1):
        ultimo = _esperar_espaciado(ultimo)
        try:
            raw, extra_429, extra_disp = generar_json(system, user)
        except CuotaDia:
            return "cuota_dia", None, llamadas, n_429, n_disp, ultimo
        except CuotaMinutoAgotada:
            return "cuota_minuto", None, llamadas, n_429 + 3, n_disp, ultimo
        except DisponibilidadAgotada:
            return "disponibilidad", None, llamadas, n_429, n_disp + 3, ultimo
        except (GeneracionError, ProveedorNoSoportado):
            raise
        llamadas += 1
        n_429 += extra_429
        n_disp += extra_disp
        try:
            item = validar_respuesta(raw, modulo_codigo)
        except ItemInvalido as exc:
            ultima_razon = exc.razon
            _log(f"FAIL modulo={modulo_codigo} query={query!r} razon={exc.razon}")
            continue
        if item.advertencia:
            _log(
                f"omitido_contexto_modelo modulo={modulo_codigo} "
                f"query={query!r} advertencia={item.advertencia!r}"
            )
            return "advertencia", None, llamadas, n_429, n_disp, ultimo
        item_id = guardar_item(item, hits, entidad=entidad)
        return "ok", item_id, llamadas, n_429, n_disp, ultimo

    print(f"FAIL modulo={modulo_codigo} query={query} razon={ultima_razon}")
    return "fail_json", None, llamadas, n_429, n_disp, ultimo


def generar_lote(
    *,
    modulos: list[dict[str, Any]],
    queries_por_modulo: dict[str, list[str]],
    limit: int,
    k: int,
    entidad: str,
    dry_run: bool,
    offset: int = 0,
    min_score: float | None = None,
) -> ResultadoLote:
    """Recorre módulos y queries: busca, filtra por umbral, genera y acumula.

    Cómo: toma de cada módulo las queries desde `offset` hasta `offset + limit`.
    Recupera `k` artículos y se queda con uno si supera el umbral. Por debajo
    del umbral cuenta un omitido y sigue. En dry-run imprime el fragmento y no
    llama a Gemini. En corrida real delega en `generar_un_item`. Cuota diaria,
    límite por minuto o tres 5xx lanzan `LoteAbortado` con lo ya guardado.

    Variables:
        modulos: filas de `modulos`, cada una con `codigo`.
        queries_por_modulo: mapa código → frases, de `cargar_queries`.
        limit: cuántas queries usar por módulo.
        k: cuántos vecinos pide el RAG antes del umbral.
        entidad: organismo.
        dry_run: True muestra fragmentos y no llama a la API.
        offset: cuántas queries iniciales se saltan, para continuar un lote.
        min_score: umbral. None usa `settings.rag_min_score`.
        umbral: el número que se aplica de verdad.
        resultado: acumulado que se va llenando.
        system: XML maestro, o texto vacío en dry-run.
        ultimo_inicio: reloj para separar llamadas 7 segundos.
        codigo: módulo de este ciclo.
        seleccion: el recorte de queries de ese módulo.
        hits / usables: vecinos crudos y el que pasó el umbral.
        estado / item_id / llamadas / n_429 / n_disp: lo que devolvió una pregunta.

    Devuelve: el `ResultadoLote` al terminar todas las queries.
    """
    umbral = settings.rag_min_score if min_score is None else min_score
    resultado = ResultadoLote()
    system = "" if dry_run else cargar_system_prompt()
    ultimo_inicio: float | None = None

    if not dry_run and settings.provider_label != "gemini":
        raise ProveedorNoSoportado(
            f"GENERATION_PROVIDER={settings.generation_provider}. "
            "En esta fase solo está implementado gemini; no se llama a nada."
        )
    if not dry_run and not settings.has_google_api_key:
        raise GeneracionError("Falta GOOGLE_API_KEY.")

    for modulo in modulos:
        codigo = str(modulo["codigo"])
        queries = queries_por_modulo.get(codigo, [])
        seleccion = queries[offset : offset + limit]
        for query in seleccion:
            resultado.ultimo_modulo = codigo
            resultado.ultima_query = query
            hits = recuperar(codigo, query, k=k, entidad=entidad)
            usables = hits_por_umbral(hits, umbral)
            if not usables:
                resultado.omitidos_sin_rag += 1
                top = f"{hits[0].score:.3f}" if hits else "—"
                print(
                    f"omitido_sin_rag modulo={codigo} query={query!r} "
                    f"hits={len(hits)} top={top} umbral={umbral}"
                )
                _log(f"omitido_sin_rag modulo={codigo} query={query!r}")
                continue

            if dry_run:
                print(f"[dry-run] modulo={codigo} query={query!r}")
                for i, hit in enumerate(usables, start=1):
                    extracto = " ".join(hit.texto.split())
                    if len(extracto) > 220:
                        extracto = extracto[:217] + "..."
                    print(
                        f"  {i}. chunk_id={hit.chunk_id} art. {hit.articulo} "
                        f"| {hit.norma} | score={hit.score:.3f}"
                    )
                    print(f"     {extracto}")
                continue

            try:
                estado, item_id, llamadas, n_429, n_disp, ultimo_inicio = generar_un_item(
                    codigo,
                    query,
                    usables,
                    system,
                    entidad=entidad,
                    dry_run=False,
                    ultimo_inicio=ultimo_inicio,
                )
            except ProveedorNoSoportado:
                raise
            except GeneracionError as exc:
                resultado.fail_json += 1
                resultado.llamadas_api += 1
                print(f"FAIL modulo={codigo} query={query} razon=api ({exc})")
                _log(f"FAIL modulo={codigo} query={query!r} razon=api {exc}")
                continue

            resultado.llamadas_api += llamadas
            resultado.n_429_minuto += n_429
            resultado.n_disponibilidad += n_disp
            if estado == "ok" and item_id is not None:
                resultado.ok += 1
                resultado.ids_insertados.append(item_id)
                print(f"OK id={item_id} modulo={codigo} art. {usables[0].articulo}")
            elif estado == "advertencia":
                resultado.omitidos_advertencia += 1
                print(f"omitido_contexto_modelo modulo={codigo} query={query!r}")
            elif estado == "fail_json":
                resultado.fail_json += 1
            elif estado == "cuota_dia":
                resultado.detenido_por_cuota_diaria = True
                print(resultado.resumen())
                if resultado.ids_insertados:
                    print("ids=" + ",".join(str(i) for i in resultado.ids_insertados))
                print(
                    f"último modulo={resultado.ultimo_modulo} "
                    f"query={resultado.ultima_query!r}"
                )
                print("continúa mañana con --modulo y --limit (o --offset).")
                raise LoteAbortado(estado, resultado)
            elif estado in {"cuota_minuto", "disponibilidad"}:
                resultado.detenido_por_disponibilidad = estado == "disponibilidad"
                print(resultado.resumen())
                if resultado.ids_insertados:
                    print("ids=" + ",".join(str(i) for i in resultado.ids_insertados))
                print(
                    f"último modulo={resultado.ultimo_modulo} "
                    f"query={resultado.ultima_query!r}"
                )
                print(
                    "API saturada o rate limit por minuto; "
                    "reintenta más tarde con --modulo y --offset."
                )
                raise LoteAbortado(estado, resultado)

    return resultado
