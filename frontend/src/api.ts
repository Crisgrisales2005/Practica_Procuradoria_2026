export type Modulo = {
  id: number;
  codigo: string;
  nombre: string;
  tipo: string;
  en_banco: number;
};

export type Progreso = {
  para_hoy: number;
  nuevos: number;
  programados: number;
  dudosos: number;
  aciertos_optimos: number;
  parciales: number;
  fallos: number;
  intentos_totales: number;
  ultimos_intentos: number[];
};

export type Pregunta = {
  estado: "pregunta";
  presentacion_token: string;
  item_id: number;
  caso: string;
  enunciado: string;
  opciones: { letra: string; texto: string }[];
};

export type Feedback = {
  estado: "feedback";
  item_id: number;
  letra_elegida: string;
  puntaje: number;
  resultado: string;
  matriz: {
    letra: string;
    texto: string;
    rol: string;
    es_eleccion: boolean;
    es_optima: boolean;
    justificacion: string;
  }[];
  cita: { norma: string; articulo: string };
  proximo_repaso: string | null;
};

async function parse(res: Response) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err =
      (data && (data.detail?.error || data.error || data.detail)) ||
      `HTTP ${res.status}`;
    throw new Error(typeof err === "string" ? err : JSON.stringify(err));
  }
  return data;
}

export async function health(): Promise<{ ok: boolean; db?: string }> {
  const res = await fetch("/api/health");
  const data = await res.json().catch(() => ({ ok: false, db: "warming" }));
  return data;
}

export async function login(password: string) {
  return parse(
    await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    })
  );
}

export async function logout() {
  return parse(await fetch("/api/auth/logout", { method: "POST" }));
}

export async function me(): Promise<boolean> {
  const res = await fetch("/api/auth/me");
  return res.ok;
}

export async function fetchModulos(): Promise<Modulo[]> {
  return parse(await fetch("/api/modulos"));
}

export async function fetchProgreso(codigo: string): Promise<Progreso> {
  return parse(await fetch(`/api/modulos/${codigo}/progreso`));
}

export async function fetchSiguiente(
  codigo: string
): Promise<Pregunta | { estado: "sin_banco" | "sin_pendientes" }> {
  return parse(await fetch(`/api/modulos/${codigo}/siguiente`));
}

export async function postIntento(
  presentacion_token: string,
  letra: string
): Promise<Feedback> {
  return parse(
    await fetch("/api/intentos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ presentacion_token, letra }),
    })
  );
}

export async function postDudoso(itemId: number, dudoso = true) {
  return parse(
    await fetch(`/api/items/${itemId}/dudoso`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dudoso }),
    })
  );
}
