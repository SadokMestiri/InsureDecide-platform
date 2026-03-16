import { useState, useEffect } from "react";
import Layout from "./Layout";
import { useWebSocket } from "../lib/useWebSocket";
import {
  RefreshCw, Wifi, WifiOff, Filter,
  TrendingUp, TrendingDown, AlertTriangle,
  AlertCircle, CheckCircle, Info, Clock
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const SEV_CONFIG = {
  critique: { bg: "#fef2f2", border: "#fecaca", dot: "#ef4444", label: "Critique", icon: AlertCircle },
  warning:  { bg: "#fffbeb", border: "#fde68a", dot: "#f59e0b", label: "Warning",  icon: AlertTriangle },
  info:     { bg: "#eff6ff", border: "#bfdbfe", dot: "#2563eb", label: "Info",     icon: Info },
};

const DEPT_COLORS = { Automobile: "#2563eb", Vie: "#10b981", Immobilier: "#f59e0b" };

function EventCard({ event, delay = 0 }) {
  const sev  = SEV_CONFIG[event.severite] || SEV_CONFIG.info;
  const Icon = sev.icon;
  const ts   = event.timestamp
    ? new Date(event.timestamp).toLocaleString("fr-TN", { day:"2-digit", month:"short", hour:"2-digit", minute:"2-digit" })
    : "";

  return (
    <div className="animate-fade-up" style={{
      animationDelay: `${delay}ms`,
      background: sev.bg,
      border: `1px solid ${sev.border}`,
      borderLeft: `4px solid ${sev.dot}`,
      borderRadius: "10px",
      padding: "14px 18px",
      display: "flex", gap: "14px", alignItems: "flex-start",
      transition: "box-shadow 0.2s",
    }}
    onMouseEnter={e => e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.08)"}
    onMouseLeave={e => e.currentTarget.style.boxShadow = "none"}
    >
      {/* Icône */}
      <div style={{ marginTop: "2px", flexShrink: 0 }}>
        <Icon size={16} color={sev.dot} />
      </div>

      {/* Contenu */}
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {/* Badge département */}
            <span style={{
              fontSize: "10px", fontWeight: 700, padding: "2px 8px", borderRadius: "20px",
              background: `${DEPT_COLORS[event.departement] || "#64748b"}20`,
              color: DEPT_COLORS[event.departement] || "#64748b",
              border: `1px solid ${DEPT_COLORS[event.departement] || "#64748b"}40`,
            }}>
              {event.departement}
            </span>
            {/* Badge sévérité */}
            <span style={{
              fontSize: "10px", fontWeight: 600, padding: "2px 7px", borderRadius: "20px",
              background: `${sev.dot}15`, color: sev.dot,
            }}>
              {sev.label}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "4px", color: "#94a3b8", fontSize: "11px" }}>
            <Clock size={10} />
            <span>{ts}</span>
          </div>
        </div>

        <h3 style={{ fontSize: "13px", fontWeight: 700, color: "#0f1f3d", marginBottom: "4px" }}>
          {event.icon} {event.titre}
        </h3>
        <p style={{ fontSize: "12px", color: "#64748b", lineHeight: 1.5 }}>
          {event.message}
        </p>

        {/* Valeur vs seuil */}
        {event.valeur !== undefined && (
          <div style={{ marginTop: "8px", display: "flex", alignItems: "center", gap: "6px" }}>
            <div style={{ height: "4px", flex: 1, background: "#e2e8f0", borderRadius: "2px", overflow: "hidden" }}>
              <div style={{
                height: "100%",
                width: `${Math.min((event.valeur / (event.seuil * 1.5)) * 100, 100)}%`,
                background: sev.dot, borderRadius: "2px",
                transition: "width 0.5s ease",
              }} />
            </div>
            <span style={{ fontSize: "11px", color: "#64748b", whiteSpace: "nowrap" }}>
              {typeof event.valeur === "number" ? event.valeur.toFixed(1) : event.valeur}
              {event.type?.includes("ratio") || event.type?.includes("resiliation") ? "%" : ""}
              {" "}/ seuil {event.seuil}
              {event.type?.includes("ratio") || event.type?.includes("resiliation") ? "%" : ""}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function WsBadge({ connected }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px",
      color: connected ? "#10b981" : "#ef4444" }}>
      {connected ? <Wifi size={13} /> : <WifiOff size={13} />}
      {connected ? "Temps réel actif" : "Reconnexion…"}
    </div>
  );
}

export default function FeedContent() {
  const [events, setEvents]     = useState([]);
  const [loading, setLoading]   = useState(true);
  const [filter, setFilter]     = useState("tous");
  const [deptFilter, setDept]   = useState("tous");
  const { connected, data }     = useWebSocket("alertes");

  const fetchFeed = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/api/events/feed?limit=50`);
      const json = await res.json();
      setEvents(json.events || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const forceRefresh = async () => {
    try {
      await fetch(`${API_BASE}/api/events/refresh`, { method: "POST" });
      await fetchFeed();
    } catch(e) { console.error(e); }
  };

  useEffect(() => { fetchFeed(); }, []);

  // Mise à jour WS → rafraîchir le feed
  useEffect(() => {
    if (data?.type === "alertes_update") fetchFeed();
  }, [data]);

  // Filtrer
  const filtered = events.filter(e => {
    const sevOk  = filter   === "tous" || e.severite   === filter;
    const deptOk = deptFilter === "tous" || e.departement === deptFilter;
    return sevOk && deptOk;
  });

  const counts = {
    critique: events.filter(e => e.severite === "critique").length,
    warning:  events.filter(e => e.severite === "warning").length,
    info:     events.filter(e => e.severite === "info").length,
  };

  return (
    <Layout>
      {/* En-tête */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "28px" }}>
        <div>
          <h1 style={{ fontSize: "24px", fontWeight: 700, color: "#0f1f3d", letterSpacing: "-0.02em" }}>
            Fil d'Événements
          </h1>
          <p style={{ fontSize: "13px", color: "#94a3b8", marginTop: "4px" }}>
            Détection automatique des événements métier significatifs
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <WsBadge connected={connected} />
          <button onClick={forceRefresh} style={{
            display: "flex", alignItems: "center", gap: "7px",
            padding: "8px 16px", borderRadius: "8px",
            background: "#fff", border: "1px solid #e2e8f0",
            color: "#64748b", fontSize: "13px", cursor: "pointer",
          }}>
            <RefreshCw size={13} />
            Actualiser
          </button>
        </div>
      </div>

      {/* Compteurs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px", marginBottom: "28px" }}>
        {[
          { label: "Critiques", count: counts.critique, color: "#ef4444", bg: "#fef2f2", icon: AlertCircle },
          { label: "Warnings",  count: counts.warning,  color: "#f59e0b", bg: "#fffbeb", icon: AlertTriangle },
          { label: "Infos",     count: counts.info,     color: "#2563eb", bg: "#eff6ff", icon: Info },
        ].map(({ label, count, color, bg, icon: Icon }) => (
          <div key={label} style={{ background: bg, border: `1px solid ${color}30`,
            borderRadius: "12px", padding: "18px 22px",
            display: "flex", alignItems: "center", gap: "14px",
            cursor: "pointer" }}
            onClick={() => setFilter(label.toLowerCase().replace("s","").replace("critiques","critique").replace("warnings","warning").replace("infos","info"))}
          >
            <div style={{ background: `${color}20`, borderRadius: "9px", padding: "9px" }}>
              <Icon size={18} color={color} />
            </div>
            <div>
              <div style={{ fontSize: "26px", fontWeight: 700, color }}>{count}</div>
              <div style={{ fontSize: "12px", color: "#64748b" }}>{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Filtres */}
      <div style={{ display: "flex", gap: "10px", marginBottom: "20px", flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#64748b", fontSize: "12px" }}>
          <Filter size={12} /> Filtres :
        </div>
        {["tous", "critique", "warning", "info"].map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            padding: "5px 14px", borderRadius: "20px", fontSize: "12px", fontWeight: 500,
            border: `1px solid ${filter === f ? "#2563eb" : "#e2e8f0"}`,
            background: filter === f ? "#eff6ff" : "#fff",
            color: filter === f ? "#2563eb" : "#64748b",
            cursor: "pointer", textTransform: "capitalize",
          }}>
            {f === "tous" ? "Tous" : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
        <div style={{ width: "1px", background: "#e2e8f0", margin: "0 4px" }} />
        {["tous", "Automobile", "Vie", "Immobilier"].map(d => (
          <button key={d} onClick={() => setDept(d)} style={{
            padding: "5px 14px", borderRadius: "20px", fontSize: "12px", fontWeight: 500,
            border: `1px solid ${deptFilter === d ? (DEPT_COLORS[d]||"#2563eb") : "#e2e8f0"}`,
            background: deptFilter === d ? `${DEPT_COLORS[d]||"#2563eb"}15` : "#fff",
            color: deptFilter === d ? (DEPT_COLORS[d]||"#2563eb") : "#64748b",
            cursor: "pointer",
          }}>
            {d}
          </button>
        ))}
      </div>

      {/* Liste des événements */}
      {loading ? (
        <div style={{ textAlign: "center", padding: "60px", color: "#94a3b8" }}>
          <RefreshCw size={24} style={{ animation: "spin 1s linear infinite", marginBottom: "12px" }} />
          <p>Chargement des événements…</p>
        </div>
      ) : filtered.length === 0 ? (
        <div style={{ background: "#ecfdf5", border: "1px solid #a7f3d0", borderRadius: "12px",
          padding: "40px", textAlign: "center", color: "#065f46", fontSize: "14px" }}>
          <CheckCircle size={32} color="#10b981" style={{ marginBottom: "12px" }} />
          <p>Aucun événement pour ces filtres.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {filtered.map((event, i) => (
            <EventCard key={`${event.type}-${event.departement}-${i}`} event={event} delay={i * 30} />
          ))}
        </div>
      )}

      <style jsx global>{`
        @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
      `}</style>
    </Layout>
  );
}
