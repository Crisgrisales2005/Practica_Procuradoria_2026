import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Feedback,
  Modulo,
  Pregunta,
  Progreso,
  fetchModulos,
  fetchProgreso,
  fetchSiguiente,
  health,
  login,
  logout,
  me,
  postDudoso,
  postIntento,
} from "./api";

const DISCLAIMER =
  "Herramienta de estudio. No garantiza un porcentaje de éxito en el examen oficial.";
// Disclaimer duplicado a propósito (bajo el panel + pie). No consolidar.

const SCORES_KEY = "procuradoria_scores_v1";
const LAST_MOD_KEY = "procuradoria_ultimo_modulo";

type Phase = "wake" | "login" | "modulos" | "practica";
type Filter = "all" | "esp" | "com";

function loadScores(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(SCORES_KEY) || "{}") as Record<
      string,
      number
    >;
  } catch {
    return {};
  }
}

function saveScore(codigo: string, pct: number) {
  const cur = loadScores();
  cur[codigo] = Math.max(cur[codigo] || 0, pct);
  localStorage.setItem(SCORES_KEY, JSON.stringify(cur));
}

function Ring({
  pct,
  size = "lg",
}: {
  pct: number;
  size?: "lg" | "sm";
}) {
  const p = Math.max(0, Math.min(100, pct));
  return (
    <div
      className={`ring ${size === "sm" ? "sm" : ""}`}
      style={{ ["--p" as string]: p }}
      data-l={`${p}%`}
      aria-label={`${p} por ciento`}
    />
  );
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("wake");
  const [wakeMsg, setWakeMsg] = useState("Despertando el servidor, un momento…");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [modulos, setModulos] = useState<Modulo[]>([]);
  const [modulo, setModulo] = useState<string | null>(null);
  const [progreso, setProgreso] = useState<Progreso | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [scores, setScores] = useState<Record<string, number>>(loadScores);

  const [pregunta, setPregunta] = useState<Pregunta | null>(null);
  const [vacio, setVacio] = useState<"sin_banco" | "sin_pendientes" | null>(null);
  const [letra, setLetra] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [dudosoOk, setDudosoOk] = useState(false);

  const boot = useCallback(async () => {
    setPhase("wake");
    let delay = 1000;
    for (let i = 0; i < 20; i++) {
      try {
        const h = await health();
        if (h.db === "warming") {
          setWakeMsg("Conectando con la base de datos…");
          await new Promise((r) => setTimeout(r, delay));
          delay = Math.min(delay * 1.5, 8000);
          continue;
        }
        const ok = await me();
        if (ok) {
          setPhase("modulos");
          return;
        }
        setPhase("login");
        return;
      } catch {
        setWakeMsg("Despertando el servidor, un momento…");
        await new Promise((r) => setTimeout(r, delay));
        delay = Math.min(delay * 1.5, 8000);
      }
    }
    setWakeMsg("No se pudo conectar. Recarga la página en un minuto.");
  }, []);

  useEffect(() => {
    void boot();
  }, [boot]);

  useEffect(() => {
    if (phase !== "modulos") return;
    void (async () => {
      try {
        const list = await fetchModulos();
        setModulos(list);
      } catch (e) {
        setErr(String(e));
      }
    })();
  }, [phase]);

  useEffect(() => {
    if (!modulo || phase !== "practica") return;
    void (async () => {
      try {
        const p = await fetchProgreso(modulo);
        setProgreso(p);
        if (p.intentos_totales > 0) {
          const pct = Math.round(
            (p.aciertos_optimos / p.intentos_totales) * 100
          );
          saveScore(modulo, pct);
          setScores(loadScores());
        }
      } catch {
        /* ignore */
      }
    })();
  }, [modulo, phase, feedback]);

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await login(password);
      setPhase("modulos");
    } catch (ex) {
      setErr(String(ex));
    } finally {
      setBusy(false);
    }
  }

  async function openModulo(codigo: string) {
    setErr(null);
    setModulo(codigo);
    localStorage.setItem(LAST_MOD_KEY, codigo);
    setFeedback(null);
    setPregunta(null);
    setLetra(null);
    setVacio(null);
    setDudosoOk(false);
    setPhase("practica");
    setBusy(true);
    try {
      const s = await fetchSiguiente(codigo);
      if (s.estado === "pregunta") {
        setPregunta(s);
      } else {
        setVacio(s.estado);
      }
      setProgreso(await fetchProgreso(codigo));
    } catch (ex) {
      setErr(String(ex));
    } finally {
      setBusy(false);
    }
  }

  async function onResponder() {
    if (!pregunta || !letra) return;
    setBusy(true);
    setErr(null);
    try {
      const fb = await postIntento(pregunta.presentacion_token, letra);
      setFeedback(fb);
      setPregunta(null);
    } catch (ex) {
      setErr(String(ex));
    } finally {
      setBusy(false);
    }
  }

  async function onDudoso() {
    if (!feedback) return;
    setBusy(true);
    try {
      await postDudoso(feedback.item_id, true);
      setDudosoOk(true);
    } catch (ex) {
      setErr(String(ex));
    } finally {
      setBusy(false);
    }
  }

  async function onSiguiente() {
    if (!modulo) return;
    setFeedback(null);
    setLetra(null);
    setDudosoOk(false);
    setBusy(true);
    setErr(null);
    try {
      const s = await fetchSiguiente(modulo);
      if (s.estado === "pregunta") {
        setPregunta(s);
        setVacio(null);
      } else {
        setPregunta(null);
        setVacio(s.estado);
      }
      setProgreso(await fetchProgreso(modulo));
    } catch (ex) {
      setErr(String(ex));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    function onKey(ev: KeyboardEvent) {
      if (
        phase === "modulos" &&
        ev.key === "/" &&
        (ev.target as HTMLElement)?.tagName !== "INPUT"
      ) {
        ev.preventDefault();
        document
          .querySelector<HTMLInputElement>('input[type="search"]')
          ?.focus();
        return;
      }
      if (phase !== "practica" || feedback || !pregunta) return;
      const k = ev.key.toUpperCase();
      if (["A", "B", "C", "D"].includes(k)) {
        setLetra(k);
      }
      const n = Number(ev.key);
      if (n >= 1 && n <= 4) {
        const op = pregunta.opciones[n - 1];
        if (op) setLetra(op.letra);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, feedback, pregunta]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return modulos.filter((m) => {
      const kind = m.codigo.startsWith("esp") ? "esp" : "com";
      if (filter !== "all" && kind !== filter) return false;
      if (!q) return true;
      return `${m.codigo} ${m.nombre} ${m.tipo}`.toLowerCase().includes(q);
    });
  }, [modulos, filter, query]);

  const avgScore = useMemo(() => {
    if (!modulos.length) return 0;
    const sum = modulos.reduce((a, m) => a + (scores[m.codigo] || 0), 0);
    return Math.round(sum / modulos.length);
  }, [modulos, scores]);

  const doneCount = useMemo(
    () => modulos.filter((m) => (scores[m.codigo] || 0) > 0).length,
    [modulos, scores]
  );

  const totalQ = useMemo(
    () => modulos.reduce((a, m) => a + (m.en_banco || 0), 0),
    [modulos]
  );

  const prepMsg =
    doneCount === 0
      ? "Empieza tu primer módulo"
      : avgScore >= 70
        ? "Vas por muy buen camino"
        : "Sigue practicando, vas avanzando";

  if (phase === "wake") {
    return (
      <div className="wake">
        <div className="brand">
          <span className="mark">P</span>
          Preparación Sustanciador 4SU-11
        </div>
        <p>{wakeMsg}</p>
      </div>
    );
  }

  if (phase === "login") {
    return (
      <section className="login">
        <div className="hero">
          <div className="brand">
            <span className="mark">P</span>
            Procuraduría · 4SU-11
          </div>
          <h1>
            Practica con las preguntas institucionales de la PGN y sé de los{" "}
            <em>más opcionados</em> a ganar.
          </h1>
          <p>
            Concurso Abierto de Méritos 2026 · Sustanciador grado 11. Entrena
            por módulos, recibe retroalimentación inmediata y mide tu nivel de
            preparación.
          </p>
        </div>
        <div className="login-panel">
          <form className="box" onSubmit={onLogin}>
            <h2>Ingresar</h2>
            <p className="lead">Accede a tu simulador de práctica.</p>
            <label htmlFor="pw">Contraseña</label>
            <input
              id="pw"
              type="password"
              placeholder="••••••••"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {err && <p className="err">{err}</p>}
            <button
              className="cta"
              type="submit"
              disabled={busy || !password}
            >
              Entrar
            </button>
            <p className="disclaimer">{DISCLAIMER}</p>
          </form>
        </div>
      </section>
    );
  }

  if (phase === "modulos") {
    const especificos = filtered.filter((m) => m.codigo.startsWith("esp"));
    const comunes = filtered.filter((m) => m.codigo.startsWith("com"));

    function ModCard({ m }: { m: Modulo }) {
      const pct = scores[m.codigo] || 0;
      return (
        <button
          type="button"
          className="mod"
          onClick={() => void openModulo(m.codigo)}
        >
          <div className="row">
            <div>
              <span className="code">{m.codigo.toUpperCase()}</span>
              <h3>{m.nombre}</h3>
              <small>{m.tipo === "especifico" ? "Específico" : "Común"}</small>
            </div>
            <Ring pct={pct} size="sm" />
          </div>
          <div className="foot">
            <span>
              {m.en_banco
                ? `${m.en_banco} pregunta${m.en_banco === 1 ? "" : "s"}`
                : "Sin preguntas"}
            </span>
            <span className="go">Practicar →</span>
          </div>
        </button>
      );
    }

    return (
      <div className="wrap">
        <div className="top">
          <div className="brand">
            <span className="mark">P</span>
            Sustanciador 4SU-11
          </div>
          <button
            type="button"
            className="pill"
            onClick={async () => {
              await logout();
              setPhase("login");
            }}
          >
            Salir
          </button>
        </div>

        <div className="bento">
          <div className="tile t-hero">
            <Ring pct={avgScore} />
            <div>
              <div className="code">ÍNDICE DE PREPARACIÓN</div>
              <h2>{prepMsg}</h2>
              <p>Promedio de tu mejor acierto óptimo por módulo (en este dispositivo).</p>
            </div>
          </div>
          <div className="tile t-s">
            <div className="kpi">
              <b>{modulos.length}</b>
              <span>Módulos</span>
            </div>
            <div className="kpi">
              <b>{totalQ}</b>
              <span>Preguntas</span>
            </div>
            <div className="kpi">
              <b>{doneCount}</b>
              <span>Con práctica</span>
            </div>
            <div className="kpi">
              <b>{filtered.length}</b>
              <span>Mostrando</span>
            </div>
          </div>
        </div>

        <div className="tools">
          <input
            type="search"
            placeholder="Buscar módulo o norma…  ( / )"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Buscar módulo"
          />
          {(
            [
              ["all", "Todos"],
              ["esp", "Específicos"],
              ["com", "Comunes"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`pill ${filter === id ? "on" : ""}`}
              onClick={() => setFilter(id)}
            >
              {label}
            </button>
          ))}
        </div>

        {err && <p className="err">{err}</p>}

        {especificos.length > 0 && (
          <>
            <div className="sec">Módulos específicos</div>
            <div className="grid">
              {especificos.map((m) => (
                <ModCard key={m.codigo} m={m} />
              ))}
            </div>
          </>
        )}
        {comunes.length > 0 && (
          <>
            <div className="sec">Módulos comunes</div>
            <div className="grid">
              {comunes.map((m) => (
                <ModCard key={m.codigo} m={m} />
              ))}
            </div>
          </>
        )}
        {!filtered.length && (
          <p className="sub">Sin resultados.</p>
        )}

        <p className="disclaimer">{DISCLAIMER}</p>
      </div>
    );
  }

  const pctAcierto =
    progreso && progreso.intentos_totales > 0
      ? Math.round(
          (progreso.aciertos_optimos / progreso.intentos_totales) * 100
        )
      : 0;

  const cola =
    (progreso?.para_hoy || 0) + (progreso?.nuevos || 0);
  const barW =
    progreso && cola + (progreso.programados || 0) > 0
      ? Math.round(
          ((progreso.intentos_totales || 0) /
            Math.max(
              1,
              (progreso.intentos_totales || 0) + cola
            )) *
            100
        )
      : 0;

  return (
    <div className="wrap">
      <div className="qwrap">
        <div className="top">
          <button
            type="button"
            className="pill"
            onClick={() => setPhase("modulos")}
          >
            ← Módulos
          </button>
          <span className="demo">{modulo?.toUpperCase()}</span>
        </div>

        {progreso && (
          <section className="panel" aria-label="Progreso de práctica">
            <div className="t-hero" style={{ display: "flex", gap: 20 }}>
              <Ring pct={pctAcierto} />
              <div style={{ flex: 1 }}>
                <div className="code">ACIERTO ÓPTIMO</div>
                <h2 style={{ margin: "4px 0 8px", fontSize: 24 }}>
                  {progreso.intentos_totales === 0
                    ? "Aún sin respuestas"
                    : `${pctAcierto}% en este módulo`}
                </h2>
                <p className="sub" style={{ margin: 0 }}>
                  {progreso.intentos_totales === 0
                    ? "Responde para empezar a medir tu nivel."
                    : `${progreso.aciertos_optimos} óptimas de ${progreso.intentos_totales} intentos.`}
                </p>
              </div>
            </div>
            <div className="bar" aria-hidden>
              <i style={{ width: `${Math.min(100, barW)}%` }} />
            </div>
            <div className="metrics">
              <div className="metric">
                <strong>{progreso.para_hoy}</strong>
                <span>Para hoy</span>
              </div>
              <div className="metric">
                <strong>{progreso.nuevos}</strong>
                <span>Nuevos</span>
              </div>
              <div className="metric">
                <strong>{progreso.programados}</strong>
                <span>Programados</span>
              </div>
              <div className="metric">
                <strong>{progreso.dudosos}</strong>
                <span>Dudosos</span>
              </div>
              <div className="metric">
                <strong>{progreso.aciertos_optimos}</strong>
                <span>Óptimas</span>
              </div>
              <div className="metric">
                <strong>{progreso.parciales}</strong>
                <span>Parciales</span>
              </div>
              <div className="metric">
                <strong>{progreso.fallos}</strong>
                <span>Fallos</span>
              </div>
            </div>
            {progreso.ultimos_intentos.length > 0 && (
              <div className="racha" aria-label="Últimos intentos">
                {progreso.ultimos_intentos.map((p, i) => (
                  <span key={i} className={`chip s${p}`} title={`${p}`}>
                    {p}
                  </span>
                ))}
              </div>
            )}
            <p className="disclaimer">{DISCLAIMER}</p>
          </section>
        )}

        {err && <p className="err">{err}</p>}
        {busy && <p className="loading-inline">Cargando…</p>}

        {vacio === "sin_banco" && (
          <p className="sub">Este módulo aún no tiene preguntas en el banco.</p>
        )}
        {vacio === "sin_pendientes" && (
          <p className="sub">
            No hay más pendientes <strong>para hoy</strong>.
            {progreso && progreso.programados > 0
              ? ` Hay ${progreso.programados} repaso${progreso.programados === 1 ? "" : "s"} agendado${progreso.programados === 1 ? "" : "s"} para próximos días.`
              : " Vuelve más tarde o elige otro módulo."}
          </p>
        )}

        {pregunta && !feedback && (
          <section>
            {pregunta.caso ? <p className="caso">{pregunta.caso}</p> : null}
            <h2 className="enunciado">{pregunta.enunciado}</h2>
            <div className="opciones" role="radiogroup" aria-label="Opciones">
              {pregunta.opciones.map((op, idx) => (
                <button
                  key={op.letra}
                  type="button"
                  className={`opt ${letra === op.letra ? "selected" : ""}`}
                  onClick={() => setLetra(op.letra)}
                  aria-pressed={letra === op.letra}
                >
                  <kbd>{idx + 1}</kbd>
                  <span>
                    <strong>{op.letra}.</strong> {op.texto}
                  </span>
                </button>
              ))}
            </div>
            <div className="actions">
              <button
                type="button"
                className="cta inline"
                disabled={!letra || busy}
                onClick={() => void onResponder()}
              >
                Responder
              </button>
            </div>
          </section>
        )}

        {feedback && (
          <section>
            <div className="why">
              <b>{feedback.resultado}. </b>
              {feedback.proximo_repaso
                ? `Próximo repaso: ${feedback.proximo_repaso}. `
                : null}
              Norma de apoyo: {feedback.cita.norma} · art.{" "}
              {feedback.cita.articulo}.
            </div>
            {feedback.matriz.map((m) => (
              <div
                key={m.letra}
                className={`matriz-item ${m.rol.toLowerCase()} ${
                  m.es_optima ? "ok" : ""
                } ${m.es_eleccion && !m.es_optima ? "bad" : ""}`}
              >
                <div className="meta">
                  {m.letra}. {m.rol}
                  {m.es_eleccion ? " · Tu elección" : ""}
                  {m.es_optima ? " · Óptima" : ""}
                </div>
                <p>{m.texto}</p>
                <p className="sub">{m.justificacion}</p>
              </div>
            ))}
            <div className="actions">
              <button
                type="button"
                className="btn-ghost"
                disabled={busy || dudosoOk}
                onClick={() => void onDudoso()}
              >
                {dudosoOk ? "Marcado dudoso" : "Ítem dudoso"}
              </button>
              <button
                type="button"
                className="cta inline"
                disabled={busy}
                onClick={() => void onSiguiente()}
              >
                Siguiente
              </button>
            </div>
          </section>
        )}

        <p className="disclaimer">{DISCLAIMER}</p>
      </div>
    </div>
  );
}
