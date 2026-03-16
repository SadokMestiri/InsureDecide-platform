import { useState, useRef, useEffect } from "react";
import Layout from "./Layout";
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
  kpi_tool:    { label: "Données KPIs",         icon: Database,      color: "#2563eb" },
  rag_tool:    { label: "Base de connaissance",  icon: Search,        color: "#10b981" },
  alerte_tool: { label: "Alertes actives",       icon: AlertTriangle, color: "#f59e0b" },
};

function now() {
  return new Date().toLocaleTimeString("fr-TN", { hour: "2-digit", minute: "2-digit" });
}

function ToolBadge({ toolName }) {
  const cfg = TOOL_LABELS[toolName] || { label: toolName, icon: Zap, color: "#64748b" };
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

function Message({ msg }) {
  const isUser = msg.role === "user";
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
              {msg.tools_used.map(t => <ToolBadge key={t} toolName={t} />)}
            </div>
          )}
          <div style={{ fontSize: "14px", color: "#0f1f3d", lineHeight: "1.7", whiteSpace: "pre-wrap" }}>
            {msg.content}
          </div>
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
};

export default function AgentChat() {
  const [messages, setMessages] = useState([WELCOME]);
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const [status, setStatus]     = useState(null);
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
        time: now(),
      }]);
    } catch (err) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `⚠️ Erreur : ${err.message}\n\nVérifiez qu'Ollama est démarré (ollama serve) et que llama3 est installé (ollama pull llama3).`,
        tools_used: [],
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
                {Object.entries(TOOL_LABELS).map(([key, cfg]) => {
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
          </div>
        </div>
      </div>

      <style jsx global>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </Layout>
  );
}