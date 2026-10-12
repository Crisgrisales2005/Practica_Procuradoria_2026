import { useCallback, useEffect, useState } from "react";
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

type Phase = "wake" | "login" | "modulos" | "practica";

const LAST_MOD_KEY = "procuradoria_ultimo_modulo";

export default function App() {
  const [phase, setPhase] = useState<Phase>("wake");
  const [wakeMsg, setWakeMsg] = useState("Despertando el servidor, un momento…");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [modulos, setModulos] = useState<Modulo[]>([]);
  const [modulo, setModulo] = useState<string | null>(null);
  const [progreso, setProgreso] = useState<Progreso | null>(null);

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
        setProgreso(await fetchProgreso(modulo));
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
    if (phase !== "practica" || feedback || !pregunta) return;
    function onKey(ev: KeyboardEvent) {
      const k = ev.key.toUpperCase();
      if (["A", "B", "C", "D"].includes(k)) {
        setLetra(k);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, feedback, pregunta]);

  if (phase === "wake") {
    return (
      <div className="wake">
        <p className="brand">Preparación Sustanciador 4SU-11</p>
        <p>{wakeMsg}</p>
      </div>
    );
  }

  if (phase === "login") {
    return (
      <div className="app login-box">
        <h1 className="brand">Preparación Sustanciador 4SU-11</h1>
        <p className="sub">Acceso con contraseña de estudio</p>
        <form onSubmit={onLogin}>
          <label htmlFor="pw">Contraseña</label>
          <input
            id="pw"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {err && <p className="err">{err}</p>}
          <button className="btn btn-primary" type="submit" disabled={busy || !password}>
            Entrar
          </button>
        </form>
        <p className="disclaimer">{DISCLAIMER}</p>
      </div>
    );
  }

  if (phase === "modulos") {
    return (
      <div className="app">
        <div className="topbar">
          <div>
            <h1 className="brand">Preparación Sustanciador 4SU-11</h1>
            <p className="sub">Elige un módulo para practicar</p>
          </div>
          <button
            type="button"
            className="linkish"
            onClick={async () => {
              await logout();
              setPhase("login");
            }}
          >
            Salir
          </button>
        </div>
        {err && <p className="err">{err}</p>}
        <ul className="mod-list">
          {modulos.map((m) => (
            <li key={m.codigo}>
              <button type="button" className="mod-btn" onClick={() => void openModulo(m.codigo)}>
                <span>
                  <strong>{m.codigo}</strong> — {m.nombre}
                </span>
                <span className={`badge ${m.en_banco ? "" : "empty"}`}>
                  {m.en_banco ? `${m.en_banco} preguntas` : "sin preguntas"}
                </span>
              </button>
            </li>
          ))}
        </ul>
        <p className="disclaimer">{DISCLAIMER}</p>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="topbar">
        <button type="button" className="linkish" onClick={() => setPhase("modulos")}>
          ← Módulos
        </button>
        <span className="sub" style={{ margin: 0 }}>
          {modulo}
        </span>
      </div>

      {progreso && (
        <section className="panel" aria-label="Progreso de práctica">
          <h2>Progreso de práctica</h2>
          {(() => {
            const total = progreso.intentos_totales || 0;
            const pctAcierto =
              total > 0
                ? Math.round((progreso.aciertos_optimos / total) * 100)
                : 0;
            return (
              <div className="acierto-bar" aria-label="Porcentaje de acierto">
                <div className="acierto-bar-head">
                  <span>Acierto óptimo</span>
                  <strong>{total === 0 ? "—" : `${pctAcierto}%`}</strong>
                </div>
                <div
                  className="acierto-bar-track"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={pctAcierto}
                >
                  <div
                    className="acierto-bar-fill"
                    style={{ width: `${pctAcierto}%` }}
                  />
                </div>
                <p className="acierto-bar-hint">
                  {total === 0
                    ? "Aún no hay respuestas en este módulo."
                    : `${progreso.aciertos_optimos} óptimas de ${total} intentos (parciales y fallos no cuentan como acierto).`}
                </p>
              </div>
            );
          })()}
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
              <span>Programados (próximos días)</span>
            </div>
            <div className="metric">
              <strong>{progreso.dudosos}</strong>
              <span>Dudosos</span>
            </div>
            <div className="metric">
              <strong>{progreso.aciertos_optimos}</strong>
              <span>Aciertos óptimos</span>
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
          {/* Disclaimer duplicado a propósito (bajo el panel + pie). No consolidar. */}
          <p className="disclaimer">{DISCLAIMER}</p>
        </section>
      )}

      {err && <p className="err">{err}</p>}
      {busy && <p className="loading-inline">Cargando…</p>}

      {vacio === "sin_banco" && (
        <p>Este módulo aún no tiene preguntas en el banco.</p>
      )}
      {vacio === "sin_pendientes" && (
        <p>
          No hay más pendientes <strong>para hoy</strong>.
          {progreso && progreso.programados > 0
            ? ` Hay ${progreso.programados} repaso${progreso.programados === 1 ? "" : "s"} agendado${progreso.programados === 1 ? "" : "s"} para próximos días (SRS).`
            : " Vuelve más tarde o elige otro módulo."}
        </p>
      )}

      {pregunta && !feedback && (
        <section>
          <p className="caso">{pregunta.caso}</p>
          <p className="enunciado">{pregunta.enunciado}</p>
          <div className="opciones" role="radiogroup" aria-label="Opciones">
            {pregunta.opciones.map((op) => (
              <button
                key={op.letra}
                type="button"
                className={`opcion ${letra === op.letra ? "selected" : ""}`}
                onClick={() => setLetra(op.letra)}
                aria-pressed={letra === op.letra}
              >
                <span className="letra">{op.letra}.</span>
                {op.texto}
              </button>
            ))}
          </div>
          <div className="actions">
            <button
              type="button"
              className="btn btn-primary"
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
          <p>
            <strong>{feedback.resultado}</strong>
            {feedback.proximo_repaso
              ? ` · Próximo repaso: ${feedback.proximo_repaso}`
              : null}
          </p>
          <p className="sub">
            Norma de apoyo: {feedback.cita.norma} · art. {feedback.cita.articulo}
          </p>
          {feedback.matriz.map((m) => (
            <div
              key={m.letra}
              className={`matriz-item ${m.rol.toLowerCase()}`}
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
              className="btn btn-ghost"
              disabled={busy || dudosoOk}
              onClick={() => void onDudoso()}
            >
              {dudosoOk ? "Marcado dudoso" : "Ítem dudoso"}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => void onSiguiente()}
            >
              Siguiente
            </button>
          </div>
        </section>
      )}

      {/* Disclaimer duplicado a propósito (bajo el panel + pie). No consolidar. */}
      <p className="disclaimer">{DISCLAIMER}</p>
    </div>
  );
}
