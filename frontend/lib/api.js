const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI(path) {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

function buildParams(base = {}) {
  const p = new URLSearchParams();
  Object.entries(base).forEach(([k, v]) => { if (v !== null && v !== undefined && v !== "") p.set(k, v); });
  return p.toString() ? "?" + p.toString() : "";
}

export const api = {
  dashboard:    (annee, mois)         => fetchAPI(`/api/dashboard${buildParams({annee, mois})}`),
  summary:      (annee, mois)         => fetchAPI(`/api/kpis/summary${buildParams({annee, mois})}`),
  departements: (annee, mois)         => fetchAPI(`/api/kpis/departements${buildParams({annee, mois})}`),
  evolution:    (ind, opts)           => {
    const p = new URLSearchParams({ indicateur: ind, ...opts });
    return fetchAPI(`/api/kpis/evolution?${p}`);
  },
  comparaison:  (annee, mois)         => fetchAPI(`/api/kpis/comparaison${buildParams({annee, mois})}`),
  alertes:      (nb)                  => fetchAPI(`/api/dashboard/alertes?nb_mois=${nb || 3}`),
  periodes:     ()                    => fetchAPI(`/api/kpis/periodes`),
};