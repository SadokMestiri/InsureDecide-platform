import { useState, useRef, useEffect } from "react";
import Layout from "./Layout";
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar,
  CartesianGrid, XAxis, YAxis, Tooltip, Legend,
  PieChart, Pie, Cell, AreaChart, Area,
} from "recharts";
import {
  Send, Bot, User, Loader, Zap,
  Database, Search, AlertTriangle,
  CheckCircle, XCircle
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const SUGGESTIONS = [
  "Quel est l'état de santé financière de la compagnie en décembre 2024 ?",
  "Pourquoi le département Vie est-il déficitaire ?",
  "Quelles actions urgentes recommandes-tu pour l'Automobile ?",
  "Compare les performances des 3 départements sur 2024",
  "Quels sont les risques de fraude actuels ?",
  "Explique-moi le ratio combiné et comment l'améliorer",
];

const TOOL_LABELS = {
  data_query_tool: { label: "Data Query", icon: Database, color: "#0f766e" },
  rag_tool:    { label: "Base de connaissance",  icon: Search,        color: "#10b981" },
  alerte_tool: { label: "Alertes actives",       icon: AlertTriangle, color: "#f59e0b" },
  forecast_tool: { label: "Prévisions ML",       icon: Zap,           color: "#7c3aed" },
  anomaly_tool:  { label: "Détection anomalies", icon: AlertTriangle, color: "#dc2626" },
  drift_tool:    { label: "Data drift",          icon: Search,        color: "#0ea5e9" },
  explain_tool:  { label: "Explicabilité SHAP",  icon: Bot,           color: "#16a34a" },
  segmentation_tool: { label: "Segmentation clients", icon: Database,  color: "#9333ea" },
  client_tool: { label: "Analyse clients", icon: User, color: "#b91c1c" },
};

const LEGACY_TOOL_ALIASES = {
  kpi_tool: "data_query_tool",
  sql_tool: "data_query_tool",
};

const AVAILABLE_TOOLS = [
  "data_query_tool",
  "rag_tool",
  "alerte_tool",
  "forecast_tool",
  "anomaly_tool",
  "drift_tool",
  "explain_tool",
  "segmentation_tool",
  "client_tool",
];

function now() {
  return new Date().toLocaleTimeString("fr-TN", { hour: "2-digit", minute: "2-digit" });
}

function ToolBadge({ toolName }) {
  const normalizedTool = LEGACY_TOOL_ALIASES[toolName] || toolName;
  const cfg = TOOL_LABELS[normalizedTool] || { label: normalizedTool, icon: Zap, color: "#64748b" };
  const Icon = cfg.icon;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: "4px",
      padding: "2px 8px", borderRadius: "20px",
      background: `${cfg.color}15`, border: `1px solid ${cfg.color}40`,
      fontSize: "10px", fontWeight: 600, color: cfg.color,
      marginRight: "6px", marginBottom: "4px",
    }}>
      <Icon size={10} /> {cfg.label}
    </span>
  );
}

function IntentBadge({ intent, confidence }) {
  if (!intent) return null;
  const pct = typeof confidence === "number" ? Math.round(confidence * 100) : null;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: "4px",
      padding: "2px 8px", borderRadius: "20px",
      background: "#0f172a0f", border: "1px solid #0f172a2e",
      fontSize: "10px", fontWeight: 700, color: "#0f172a",
      marginRight: "6px", marginBottom: "4px",
      textTransform: "uppercase",
      letterSpacing: "0.03em",
    }}>
      Intent: {intent}{pct !== null ? ` (${pct}%)` : ""}
    </span>
  );
}

function ChatChart({ chart }) {
  if (!chart?.data?.length) return null;

  const pieColors = chart.colors || ["#7c3aed", "#0ea5e9", "#16a34a", "#f59e0b", "#dc2626", "#14b8a6"];

  const commonProps = {
    data: chart.data,
    margin: { top: 10, right: 16, left: 0, bottom: 0 },
  };

  return (
    <div style={{ marginTop: "12px", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "10px", padding: "10px" }}>
      <div style={{ fontSize: "12px", fontWeight: 700, color: "#334155", marginBottom: "8px" }}>
        {chart.title || "Visualisation"}
      </div>
      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer>
          {chart.type === "bar" ? (
            <BarChart {...commonProps}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey={chart.xKey || "name"} tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              {(chart.series || []).map((s) => (
                <Bar key={s.key} dataKey={s.key} name={s.name || s.key} fill={s.color || "#2563eb"} radius={[4, 4, 0, 0]} />
              ))}
            </BarChart>
          ) : chart.type === "pie" ? (
            <PieChart>
              <Tooltip />
              <Legend />
              <Pie
                data={chart.data}
                dataKey={chart.valueKey || "value"}
                nameKey={chart.nameKey || "name"}
                cx="50%"
                cy="50%"
                innerRadius={chart.innerRadius || 0}
                outerRadius={chart.outerRadius || 80}
                label
              >
                {chart.data.map((_, idx) => (
                  <Cell key={`cell-${idx}`} fill={pieColors[idx % pieColors.length]} />
                ))}
              </Pie>
            </PieChart>
          ) : chart.type === "area" ? (
            <AreaChart {...commonProps}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey={chart.xKey || "name"} tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              {(chart.series || []).map((s) => (
                <Area
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.name || s.key}
                  stroke={s.color || "#2563eb"}
                  fill={s.color || "#2563eb"}
                  fillOpacity={0.28}
                />
              ))}
            </AreaChart>
          ) : (
            <LineChart {...commonProps}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey={chart.xKey || "name"} tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              {(chart.series || []).map((s) => (
                <Line
                  key={s.key}
                  dataKey={s.key}
                  name={s.name || s.key}
                  stroke={s.color || "#2563eb"}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
              ))}
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function parseStandardTable(content) {
  const marker = "Tableau standardise:";
  const idx = (content || "").indexOf(marker);
  if (idx === -1) return null;

  const before = content.slice(0, idx).trimEnd();
  const tablePart = content.slice(idx + marker.length).trim();
  const lines = tablePart
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  if (lines.length < 2) return { before, headers: [], rows: [] };

  const headers = lines[0].split(";").map((x) => x.trim()).filter(Boolean);
  const rows = lines.slice(1)
    .map((line) => line.split(";").map((x) => x.trim()))
    .filter((cols) => cols.length > 1);

  return { before, headers, rows };
}

function StandardTable({ headers, rows }) {
  if (!headers?.length || !rows?.length) return null;

  return (
    <div style={{ marginTop: "12px", border: "1px solid #e2e8f0", borderRadius: "10px", overflow: "hidden", background: "#fff" }}>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
          <thead>
            <tr style={{ background: "#f8fafc" }}>
              {headers.map((h) => (
                <th key={h} style={{ textAlign: "left", padding: "8px 10px", borderBottom: "1px solid #e2e8f0", color: "#334155", fontWeight: 700 }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} style={{ borderBottom: i === rows.length - 1 ? "none" : "1px solid #f1f5f9" }}>
                {headers.map((_, j) => (
                  <td key={j} style={{ padding: "8px 10px", color: "#0f172a", whiteSpace: "nowrap" }}>
                    {r[j] || "-"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Message({ msg }) {
  const isUser = msg.role === "user";
  const parsedTable = !isUser ? parseStandardTable(msg.content) : null;
  const displayContent = parsedTable ? parsedTable.before : msg.content;

  return (
    <div style={{
      display: "flex", gap: "12px", padding: "16px 0",
      flexDirection: isUser ? "row-reverse" : "row",
      borderBottom: "1px solid #f1f5f9",
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: "10px", flexShrink: 0,
        background: isUser ? "#2563eb" : "#0f1f3d",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        {isUser ? <User size={16} color="#fff" /> : <Bot size={16} color="#93c5fd" />}
      </div>
      <div style={{ flex: 1, maxWidth: "85%" }}>
        <div style={{
          background: isUser ? "#eff6ff" : "#fff",
          border: `1px solid ${isUser ? "#bfdbfe" : "#e2e8f0"}`,
          borderRadius: isUser ? "14px 4px 14px 14px" : "4px 14px 14px 14px",
          padding: "12px 16px",
        }}>
          {msg.tools_used?.length > 0 && (
            <div style={{ marginBottom: "10px" }}>
              <IntentBadge intent={msg.intent} confidence={msg.intent_confidence} />
              {msg.tools_used.map(t => <ToolBadge key={t} toolName={t} />)}
            </div>
          )}
          <div style={{ fontSize: "14px", color: "#0f1f3d", lineHeight: "1.7", whiteSpace: "pre-wrap" }}>
            {displayContent}
          </div>
          {parsedTable?.headers?.length > 0 && parsedTable?.rows?.length > 0 && (
            <StandardTable headers={parsedTable.headers} rows={parsedTable.rows} />
          )}
          {Array.isArray(msg.charts) && msg.charts.map((c) => (
            <ChatChart key={c.id || c.title} chart={c} />
          ))}
        </div>
        {msg.time && (
          <div style={{ fontSize: "10px", color: "#94a3b8", marginTop: "4px", textAlign: isUser ? "right" : "left" }}>
            {msg.time}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  if (!status) return null;
  const ok = status?.ready;
  const Icon = ok ? CheckCircle : XCircle;
  const color = ok ? "#10b981" : "#ef4444";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color }}>
      <Icon size={13} />
      {ok ? `Agent prêt · ${status.model || "llama3"}` : "Agent indisponible — vérifier Ollama"}
    </div>
  );
}

const WELCOME = {
  role: "assistant",
  content: "Bonjour ! Je suis votre assistant décisionnel InsureDecide.\n\nJe peux analyser vos KPIs en temps réel, expliquer les tendances, détecter les risques et vous recommander des actions stratégiques.\n\nQue souhaitez-vous savoir ?",
  time: "",
  tools_used: [],
  charts: [],
  intent: null,
  intent_confidence: null,
};

export default function AgentChat() {
  const [messages, setMessages] = useState([WELCOME]);
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const [status, setStatus]     = useState(null);
  const [smokeLoading, setSmokeLoading] = useState(false);
  const [smokeEval, setSmokeEval] = useState(null);
  const bottomRef = useRef(null);
  const inputRef  = useRef(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/agent/status`)
      .then(r => r.json())
      .then(setStatus)
      .catch(() => setStatus({ ready: false }));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (text) => {
    const question = (text || input).trim();
    if (!question || loading) return;

    setMessages(prev => [...prev, { role: "user", content: question, time: now(), tools_used: [] }]);
    setInput("");
    setLoading(true);

    try {
      const history = messages
        .filter(m => m.content !== WELCOME.content)
        .map(m => ({ role: m.role, content: m.content }));

      const res = await fetch(`${API_BASE}/api/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      setMessages(prev => [...prev, {
        role: "assistant",
        content: data.answer,
        tools_used: data.tools_used || [],
        charts: data.charts || [],
        intent: data.intent || null,
        intent_confidence: typeof data.intent_confidence === "number" ? data.intent_confidence : null,
        time: now(),
      }]);
    } catch (err) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `⚠️ Erreur : ${err.message}\n\nVérifiez qu'Ollama est démarré (ollama serve) et que llama3 est installé (ollama pull llama3).`,
        tools_used: [],
        charts: [],
        intent: null,
        intent_confidence: null,
        time: now(),
      }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const runSmokeEval = async () => {
    if (smokeLoading) return;
    setSmokeLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/agent/eval/smoke`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSmokeEval(data);
    } catch (err) {
      setSmokeEval({
        status: "error",
        passed: 0,
        total: 0,
        success_rate: 0,
        details: [],
        message: err.message,
      });
    } finally {
      setSmokeLoading(false);
    }
  };

  return (
    <Layout fullHeight>
      <div style={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden" }}>

        {/* En-tête */}
        <div style={{ marginBottom: "20px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexShrink: 0 }}>
          <div>
            <h1 style={{ fontSize: "24px", fontWeight: 700, color: "#0f1f3d", letterSpacing: "-0.02em" }}>
              Agent Décisionnel IA
            </h1>
            <p style={{ fontSize: "13px", color: "#94a3b8", marginTop: "4px" }}>
              Llama3 · LangGraph · RAG · Données temps réel
            </p>
          </div>
          <StatusBadge status={status} />
        </div>

        {/* Contenu */}
        <div style={{ flex: 1, display: "flex", gap: "24px", overflow: "hidden" }}>

          {/* Zone chat */}
          <div style={{
            flex: 1, display: "flex", flexDirection: "column",
            background: "#fff", borderRadius: "16px",
            border: "1px solid #e2e8f0",
            boxShadow: "0 1px 4px rgba(15,31,61,0.06)", overflow: "hidden",
          }}>
            {/* Messages */}
            <div style={{ flex: 1, overflowY: "auto", padding: "8px 24px" }}>
              {messages.map((msg, i) => <Message key={i} msg={msg} />)}

              {loading && (
                <div style={{ display: "flex", gap: "12px", padding: "16px 0", alignItems: "flex-start" }}>
                  <div style={{ width:36, height:36, borderRadius:"10px", background:"#0f1f3d", flexShrink:0,
                    display:"flex", alignItems:"center", justifyContent:"center" }}>
                    <Bot size={16} color="#93c5fd" />
                  </div>
                  <div style={{ background:"#fff", border:"1px solid #e2e8f0",
                    borderRadius:"4px 14px 14px 14px", padding:"14px 18px",
                    display:"flex", alignItems:"center", gap:"10px" }}>
                    <Loader size={14} color="#2563eb" style={{ animation:"spin 1s linear infinite" }} />
                    <span style={{ fontSize:"13px", color:"#64748b" }}>
                      Analyse en cours…
                    </span>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* Saisie */}
            <div style={{ padding: "16px 20px", borderTop: "1px solid #f1f5f9", background: "#fafbfc" }}>
              <div style={{ display: "flex", gap: "10px", alignItems: "flex-end" }}>
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKey}
                  placeholder="Posez votre question stratégique… (Entrée pour envoyer)"
                  rows={2}
                  style={{
                    flex: 1, padding: "10px 14px", borderRadius: "10px",
                    border: "1px solid #e2e8f0", fontSize: "14px", color: "#0f1f3d",
                    resize: "none", outline: "none", fontFamily: "'DM Sans', sans-serif",
                    background: "#fff", lineHeight: 1.5,
                  }}
                  onFocus={e => e.target.style.borderColor = "#2563eb"}
                  onBlur={e => e.target.style.borderColor = "#e2e8f0"}
                />
                <button
                  onClick={() => sendMessage()}
                  disabled={!input.trim() || loading}
                  style={{
                    width: 44, height: 44, borderRadius: "10px",
                    background: (!input.trim() || loading) ? "#e2e8f0" : "#2563eb",
                    border: "none", cursor: (!input.trim() || loading) ? "default" : "pointer",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    transition: "background 0.2s", flexShrink: 0,
                  }}
                >
                  <Send size={17} color={(!input.trim() || loading) ? "#94a3b8" : "#fff"} />
                </button>
              </div>
              <p style={{ fontSize: "10px", color: "#94a3b8", marginTop: "8px" }}>
                Entrée pour envoyer · Shift+Entrée pour nouvelle ligne
              </p>
            </div>
          </div>

          {/* Panneau droit */}
          <div style={{ width: "260px", flexShrink: 0, display: "flex", flexDirection: "column", gap: "16px", overflowY: "auto" }}>

            {/* Suggestions */}
            <div style={{ background: "#fff", borderRadius: "14px", border: "1px solid #e2e8f0",
              boxShadow: "0 1px 4px rgba(15,31,61,0.06)", padding: "20px" }}>
              <h3 style={{ fontSize: "12px", fontWeight: 700, color: "#64748b",
                textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "14px" }}>
                Questions suggérées
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {SUGGESTIONS.map((s, i) => (
                  <button key={i} onClick={() => sendMessage(s)} disabled={loading}
                    style={{
                      textAlign: "left", padding: "9px 12px", borderRadius: "8px",
                      background: "#f8fafc", border: "1px solid #e2e8f0",
                      fontSize: "12px", color: "#334155",
                      cursor: loading ? "default" : "pointer",
                      lineHeight: 1.4, transition: "all 0.15s",
                    }}
                    onMouseEnter={e => { if (!loading) { e.currentTarget.style.background="#eff6ff"; e.currentTarget.style.borderColor="#bfdbfe"; }}}
                    onMouseLeave={e => { e.currentTarget.style.background="#f8fafc"; e.currentTarget.style.borderColor="#e2e8f0"; }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            {/* Outils */}
            <div style={{ background: "#fff", borderRadius: "14px", border: "1px solid #e2e8f0",
              boxShadow: "0 1px 4px rgba(15,31,61,0.06)", padding: "20px" }}>
              <h3 style={{ fontSize: "12px", fontWeight: 700, color: "#64748b",
                textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "14px" }}>
                Outils disponibles
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {AVAILABLE_TOOLS.map((key) => {
                  const cfg = TOOL_LABELS[key];
                  const Icon = cfg.icon;
                  return (
                    <div key={key} style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <div style={{ background: `${cfg.color}15`, borderRadius: "7px", padding: "6px" }}>
                        <Icon size={13} color={cfg.color} />
                      </div>
                      <span style={{ fontSize: "12px", color: "#334155" }}>{cfg.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Smoke Eval */}
            <div style={{ background: "#fff", borderRadius: "14px", border: "1px solid #e2e8f0",
              boxShadow: "0 1px 4px rgba(15,31,61,0.06)", padding: "20px" }}>
              <h3 style={{ fontSize: "12px", fontWeight: 700, color: "#64748b",
                textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "12px" }}>
                AI Smoke Eval
              </h3>
              <button
                onClick={runSmokeEval}
                disabled={smokeLoading}
                style={{
                  width: "100%", border: "none", borderRadius: "8px",
                  padding: "9px 12px", fontSize: "12px", fontWeight: 700,
                  background: smokeLoading ? "#cbd5e1" : "#0f1f3d",
                  color: "#fff", cursor: smokeLoading ? "default" : "pointer",
                }}
              >
                {smokeLoading ? "Exécution..." : "Run Smoke Eval"}
              </button>

              {smokeEval && (
                <div style={{ marginTop: "12px", fontSize: "12px", color: "#334155", lineHeight: 1.5 }}>
                  <div style={{ fontWeight: 700 }}>
                    {smokeEval.status === "ok" ? "OK" : "Warning"} · {smokeEval.passed}/{smokeEval.total} ({smokeEval.success_rate}%)
                  </div>
                  {smokeEval.message && (
                    <div style={{ color: "#dc2626", marginTop: "6px" }}>{smokeEval.message}</div>
                  )}
                  {Array.isArray(smokeEval.details) && smokeEval.details.filter(d => !d.passed).slice(0, 3).map((d, i) => (
                    <div key={i} style={{ marginTop: "6px", color: "#b91c1c" }}>
                      {d.name}: intent={d.got_intent || "?"}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <style jsx global>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </Layout>
  );
}