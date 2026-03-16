import { useState, useEffect, useCallback } from "react";
import Layout from "./Layout";
import { AlertTriangle, Filter, RefreshCw, ChevronDown, ChevronUp, X, User } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const GOUVERNORATS = [
  "Tunis","Ariana","Ben Arous","Manouba","Nabeul","Zaghouan","Bizerte",
  "Béja","Jendouba","Kef","Siliana","Sousse","Monastir","Mahdia","Sfax",
  "Kairouan","Kasserine","Sidi Bouzid","Gabès","Médenine","Tataouine",
  "Gafsa","Tozeur","Kébili",
];

function ScoreBadge({ score }) {
  const color = score >= 75 ? "#dc2626" : score >= 50 ? "#f97316" : score >= 30 ? "#f59e0b" : "#10b981";
  const bg    = score >= 75 ? "#fef2f2" : score >= 50 ? "#fff7ed" : score >= 30 ? "#fffbeb" : "#ecfdf5";
  return (
    <div style={{ display:"inline-flex", alignItems:"center", gap:"6px" }}>
      <div style={{ position:"relative", width:38, height:38 }}>
        <svg width="38" height="38" viewBox="0 0 38 38">
          <circle cx="19" cy="19" r="15" fill="none" stroke="#f1f5f9" strokeWidth="3"/>
          <circle cx="19" cy="19" r="15" fill="none" stroke={color} strokeWidth="3"
            strokeDasharray={`${(score/100)*94.2} 94.2`}
            strokeLinecap="round"
            transform="rotate(-90 19 19)"/>
        </svg>
        <span style={{ position:"absolute", inset:0, display:"flex", alignItems:"center",
          justifyContent:"center", fontSize:"10px", fontWeight:800, color }}>{score}</span>
      </div>
    </div>
  );
}

function ActionBadge({ action, color, bg, icon }) {
  return (
    <span style={{ background:bg, color, border:`1px solid ${color}30`,
      borderRadius:"20px", padding:"4px 10px", fontSize:"11px", fontWeight:600,
      display:"inline-flex", alignItems:"center", gap:"4px", whiteSpace:"nowrap" }}>
      {icon} {action}
    </span>
  );
}

function StatCard({ label, value, color, bg, icon }) {
  return (
    <div style={{ background:bg, border:`1px solid ${color}25`, borderRadius:"12px",
      padding:"16px 20px", display:"flex", alignItems:"center", gap:"14px" }}>
      <span style={{ fontSize:"24px" }}>{icon}</span>
      <div>
        <div style={{ fontSize:"22px", fontWeight:800, color }}>{value}</div>
        <div style={{ fontSize:"11px", color:"#64748b", fontWeight:600 }}>{label}</div>
      </div>
    </div>
  );
}

function DetailPanel({ client, onClose }) {
  if (!client) return null;
  return (
    <div style={{ position:"fixed", right:0, top:0, bottom:0, width:"420px",
      background:"#fff", borderLeft:"1px solid #e2e8f0",
      boxShadow:"-8px 0 32px rgba(0,0,0,0.1)", zIndex:1000, overflowY:"auto" }}>
      <div style={{ padding:"24px", borderBottom:"1px solid #f1f5f9",
        display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:"10px", marginBottom:"4px" }}>
            <div style={{ background:"#eff6ff", borderRadius:"10px", padding:"8px" }}>
              <User size={18} color="#2563eb"/>
            </div>
            <div>
              <h2 style={{ fontSize:"16px", fontWeight:700, color:"#0f1f3d" }}>{client.nom}</h2>
              <p style={{ fontSize:"12px", color:"#94a3b8" }}>
                {client.age} ans · {client.gouvernorat} · {client.profession}
              </p>
            </div>
          </div>
        </div>
        <button onClick={onClose} style={{ border:"none", background:"#f1f5f9",
          borderRadius:"8px", padding:"6px 10px", cursor:"pointer", color:"#64748b" }}>
          <X size={16}/>
        </button>
      </div>

      <div style={{ padding:"20px" }}>
        {/* Score + Action */}
        <div style={{ background:client.action_bg, border:`1px solid ${client.action_color}30`,
          borderRadius:"12px", padding:"16px", marginBottom:"20px",
          display:"flex", alignItems:"center", justifyContent:"space-between" }}>
          <div>
            <div style={{ fontSize:"13px", fontWeight:700, color:client.action_color }}>
              {client.action_icon} {client.action}
            </div>
            <div style={{ fontSize:"11px", color:"#64748b", marginTop:"2px" }}>
              Score de risque : {client.score}/100
            </div>
          </div>
          <ScoreBadge score={client.score}/>
        </div>

        {/* KPIs */}
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"10px", marginBottom:"20px" }}>
          {[
            { label:"Sinistres",    val:client.nb_sinistres,   color:"#ef4444" },
            { label:"Coût total",   val:`${(client.cout_total||0).toLocaleString("fr-TN")} TND`, color:"#f97316" },
            { label:"Fraudes",      val:client.nb_fraudes,     color:"#f59e0b" },
            { label:"Revenu",       val:`${(client.revenu||0).toLocaleString("fr-TN")} TND`, color:"#2563eb" },
          ].map(({label,val,color}) => (
            <div key={label} style={{ background:"#f8fafc", borderRadius:"8px", padding:"12px" }}>
              <div style={{ fontSize:"16px", fontWeight:700, color }}>{val}</div>
              <div style={{ fontSize:"10px", color:"#94a3b8", marginTop:"2px", textTransform:"uppercase", fontWeight:600 }}>{label}</div>
            </div>
          ))}
        </div>

        {/* Contrats */}
        <h4 style={{ fontSize:"11px", fontWeight:700, color:"#64748b", textTransform:"uppercase",
          letterSpacing:"0.05em", marginBottom:"8px" }}>Contrats actifs</h4>
        {client.contrats?.map(c => (
          <div key={c.id} style={{ background:"#f8fafc", borderRadius:"8px", padding:"10px 14px",
            marginBottom:"6px", borderLeft:"3px solid #2563eb",
            display:"flex", justifyContent:"space-between" }}>
            <div>
              <div style={{ fontSize:"11px", fontFamily:"monospace", color:"#94a3b8" }}>{c.id}</div>
              <div style={{ fontSize:"12px", fontWeight:600, color:"#0f1f3d" }}>{c.dept}</div>
            </div>
            <div style={{ textAlign:"right" }}>
              <div style={{ fontSize:"12px", fontWeight:700, color:"#2563eb" }}>
                {c.prime.toLocaleString("fr-TN")} TND/an
              </div>
              <div style={{ fontSize:"10px", color:"#94a3b8" }}>{c.gouvernorat}</div>
            </div>
          </div>
        ))}

        {/* Historique sinistres */}
        <h4 style={{ fontSize:"11px", fontWeight:700, color:"#64748b", textTransform:"uppercase",
          letterSpacing:"0.05em", margin:"16px 0 8px" }}>Historique sinistres</h4>
        {client.sinistres?.slice(0,6).map((s,i) => (
          <div key={i} style={{ background:"#fff", borderRadius:"8px", padding:"10px 14px",
            marginBottom:"6px", border:"1px solid #e2e8f0" }}>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
              <span style={{ fontSize:"12px", fontWeight:600, color:"#0f1f3d" }}>{s.type}</span>
              <span style={{ fontSize:"12px", fontWeight:700, color:"#ef4444" }}>
                {s.cout.toLocaleString("fr-TN")} TND
              </span>
            </div>
            <div style={{ fontSize:"11px", color:"#94a3b8", marginTop:"3px" }}>
              {s.dept} · {s.date}
              {s.fraude && <span style={{ color:"#f59e0b", marginLeft:"8px", fontWeight:600 }}>⚠️ Fraude</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function RisqueContent() {
  const [data,      setData]      = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [detail,    setDetail]    = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [sortCol,   setSortCol]   = useState("score");
  const [sortDir,   setSortDir]   = useState("desc");
  const [page,      setPage]      = useState(0);

  // Filtres
  const [dept,      setDept]      = useState("");
  const [gouv,      setGouv]      = useState("");
  const [seuil,     setSeuil]     = useState(1);
  const [actionFilter, setActionFilter] = useState("");

  const LIMIT = 20;

  const fetchData = useCallback(async (offset = 0) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ seuil_sinistres: seuil, limit: LIMIT, offset });
      if (dept) params.set("departement", dept);
      if (gouv) params.set("gouvernorat", gouv);
      const r = await fetch(`${API}/api/risque/clients?${params}`);
      setData(await r.json());
    } catch(e) { console.error(e); }
    finally { setLoading(false); }
  }, [dept, gouv, seuil]);

  useEffect(() => { setPage(0); fetchData(0); }, [fetchData]);

  const fetchDetail = async (clientId) => {
    setLoadingDetail(true);
    try {
      const r = await fetch(`${API}/api/risque/client/${clientId}`);
      setDetail(await r.json());
    } catch(e) { console.error(e); }
    finally { setLoadingDetail(false); }
  };

  const handleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("desc"); }
  };

  const SortIcon = ({ col }) => {
    if (sortCol !== col) return <ChevronDown size={11} color="#cbd5e1"/>;
    return sortDir === "asc" ? <ChevronUp size={11} color="#2563eb"/> : <ChevronDown size={11} color="#2563eb"/>;
  };

  const clients = data?.clients || [];
  const stats   = data?.stats   || {};
  const total   = data?.total   || 0;

  // Trier côté client
  const sorted = [...clients]
    .filter(c => !actionFilter || c.action === actionFilter)
    .sort((a, b) => {
      const va = a[sortCol], vb = b[sortCol];
      if (typeof va === "number") return sortDir === "asc" ? va - vb : vb - va;
      return sortDir === "asc" ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
    });

  return (
    <Layout>
      {/* En-tête */}
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:"24px" }}>
        <div>
          <h1 style={{ fontSize:"24px", fontWeight:700, color:"#0f1f3d", letterSpacing:"-0.02em" }}>
            Clients à Risque
          </h1>
          <p style={{ fontSize:"13px", color:"#94a3b8", marginTop:"4px" }}>
            Score de risque automatique · Recommandations CEO
          </p>
        </div>
        <button onClick={() => fetchData(page * LIMIT)} style={{
          display:"flex", alignItems:"center", gap:"7px", padding:"8px 16px",
          borderRadius:"8px", background:"#fff", border:"1px solid #e2e8f0",
          color:"#64748b", fontSize:"13px", cursor:"pointer" }}>
          <RefreshCw size={13} style={{ animation: loading ? "spin 1s linear infinite" : "none" }}/>
          Actualiser
        </button>
      </div>

      {/* Stats */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:"14px", marginBottom:"24px" }}>
        <StatCard label="À résilier"    value={stats.resilier||0}   color="#dc2626" bg="#fef2f2" icon="🚫"/>
        <StatCard label="Prime +20%"    value={stats.augmenter||0}  color="#f97316" bg="#fff7ed" icon="📈"/>
        <StatCard label="À surveiller"  value={stats.surveiller||0} color="#f59e0b" bg="#fffbeb" icon="👁️"/>
        <StatCard label="Total clients" value={total}               color="#2563eb" bg="#eff6ff" icon="👥"/>
      </div>

      {/* Filtres */}
      <div style={{ background:"#fff", borderRadius:"12px", border:"1px solid #e2e8f0",
        padding:"16px 20px", marginBottom:"20px",
        display:"flex", alignItems:"center", gap:"12px", flexWrap:"wrap" }}>
        <Filter size={14} color="#64748b"/>

        <select value={dept} onChange={e => setDept(e.target.value)} style={{
          padding:"7px 12px", borderRadius:"8px", border:"1px solid #e2e8f0",
          fontSize:"12px", color:"#334155", background:"#f8fafc", cursor:"pointer" }}>
          <option value="">Tous départements</option>
          <option value="Automobile">Automobile</option>
          <option value="Vie">Vie</option>
          <option value="Immobilier">Immobilier</option>
        </select>

        <select value={gouv} onChange={e => setGouv(e.target.value)} style={{
          padding:"7px 12px", borderRadius:"8px", border:"1px solid #e2e8f0",
          fontSize:"12px", color:"#334155", background:"#f8fafc", cursor:"pointer" }}>
          <option value="">Tous gouvernorats</option>
          {GOUVERNORATS.map(g => <option key={g} value={g}>{g}</option>)}
        </select>

        <div style={{ display:"flex", alignItems:"center", gap:"8px" }}>
          <span style={{ fontSize:"12px", color:"#64748b" }}>Seuil sinistres ≥</span>
          <input type="number" min={1} max={20} value={seuil}
            onChange={e => setSeuil(Number(e.target.value))}
            style={{ width:"52px", padding:"6px 8px", borderRadius:"8px",
              border:"1px solid #e2e8f0", fontSize:"12px", textAlign:"center" }}/>
        </div>

        <select value={actionFilter} onChange={e => setActionFilter(e.target.value)} style={{
          padding:"7px 12px", borderRadius:"8px", border:"1px solid #e2e8f0",
          fontSize:"12px", color:"#334155", background:"#f8fafc", cursor:"pointer" }}>
          <option value="">Toutes actions</option>
          <option value="Résilier le contrat">🚫 Résilier</option>
          <option value="Augmenter la prime +20%">📈 Augmenter prime</option>
          <option value="Surveiller">👁️ Surveiller</option>
        </select>

        {(dept || gouv || actionFilter || seuil !== 1) && (
          <button onClick={() => { setDept(""); setGouv(""); setActionFilter(""); setSeuil(2); }}
            style={{ display:"flex", alignItems:"center", gap:"5px", padding:"6px 12px",
              borderRadius:"8px", border:"1px solid #fecaca", background:"#fef2f2",
              color:"#dc2626", fontSize:"12px", cursor:"pointer" }}>
            <X size={12}/> Réinitialiser
          </button>
        )}
      </div>

      {/* Table */}
      <div style={{ background:"#fff", borderRadius:"14px", border:"1px solid #e2e8f0",
        overflow:"hidden", boxShadow:"0 4px 20px rgba(0,0,0,0.04)" }}>

        {/* Header table */}
        <div style={{ display:"grid",
          gridTemplateColumns:"2fr 1fr 1fr 80px 1fr 1fr 1fr",
          padding:"12px 20px", background:"#f8fafc",
          borderBottom:"1px solid #e2e8f0" }}>
          {[
            { label:"Client",       col:"nom" },
            { label:"Gouvernorat",  col:"gouvernorat" },
            { label:"Département",  col:null },
            { label:"Score",        col:"score" },
            { label:"Sinistres",    col:"nb_sinistres" },
            { label:"Coût total",   col:"cout_total" },
            { label:"Action",       col:"action" },
          ].map(({ label, col }) => (
            <div key={label}
              onClick={() => col && handleSort(col)}
              style={{ fontSize:"11px", fontWeight:700, color:"#64748b",
                textTransform:"uppercase", letterSpacing:"0.05em",
                cursor: col ? "pointer" : "default",
                display:"flex", alignItems:"center", gap:"4px",
                userSelect:"none" }}>
              {label}
              {col && <SortIcon col={col}/>}
            </div>
          ))}
        </div>

        {/* Rows */}
        {loading ? (
          <div style={{ padding:"60px", textAlign:"center" }}>
            <RefreshCw size={24} color="#2563eb" style={{ animation:"spin 1s linear infinite", margin:"0 auto 12px" }}/>
            <p style={{ color:"#94a3b8" }}>Chargement…</p>
          </div>
        ) : sorted.length === 0 ? (
          <div style={{ padding:"60px", textAlign:"center", color:"#94a3b8" }}>
            Aucun client à risque avec ces critères
          </div>
        ) : sorted.map((c, i) => (
          <div key={c.client_id}
            onClick={() => fetchDetail(c.client_id)}
            style={{ display:"grid",
              gridTemplateColumns:"2fr 1fr 1fr 80px 1fr 1fr 1fr",
              padding:"14px 20px", cursor:"pointer",
              background: i % 2 === 0 ? "#fff" : "#fafafa",
              borderBottom:"1px solid #f8fafc",
              transition:"background 0.1s" }}
            onMouseEnter={e => e.currentTarget.style.background = "#f0f7ff"}
            onMouseLeave={e => e.currentTarget.style.background = i%2===0?"#fff":"#fafafa"}>

            <div style={{ display:"flex", alignItems:"center", gap:"10px" }}>
              <div style={{ width:32, height:32, borderRadius:"50%",
                background:`hsl(${c.score * 2.4}, 70%, 92%)`,
                display:"flex", alignItems:"center", justifyContent:"center",
                fontSize:"12px", fontWeight:700, color:`hsl(${c.score * 2.4}, 50%, 35%)`,
                flexShrink:0 }}>
                {c.nom?.charAt(0)}
              </div>
              <div>
                <div style={{ fontSize:"13px", fontWeight:600, color:"#0f1f3d" }}>{c.nom}</div>
                <div style={{ fontSize:"10px", color:"#94a3b8" }}>{c.client_id}</div>
              </div>
            </div>

            <div style={{ display:"flex", alignItems:"center",
              fontSize:"12px", color:"#64748b" }}>{c.gouvernorat}</div>

            <div style={{ display:"flex", alignItems:"center", gap:"4px", flexWrap:"wrap" }}>
              {c.departements?.map(d => (
                <span key={d} style={{ fontSize:"10px", padding:"2px 7px", borderRadius:"10px",
                  background: d==="Automobile"?"#eff6ff":"#fffbeb",
                  color: d==="Automobile"?"#2563eb":"#92400e", fontWeight:600 }}>{d}</span>
              ))}
            </div>

            <div style={{ display:"flex", alignItems:"center" }}>
              <ScoreBadge score={c.score}/>
            </div>

            <div style={{ display:"flex", alignItems:"center",
              fontSize:"13px", fontWeight:600, color:"#ef4444" }}>
              {c.nb_sinistres}
              {c.nb_fraudes > 0 &&
                <span style={{ fontSize:"10px", color:"#f59e0b", marginLeft:"6px" }}>
                  +{c.nb_fraudes}⚠️
                </span>}
            </div>

            <div style={{ display:"flex", alignItems:"center",
              fontSize:"12px", color:"#64748b" }}>
              {(c.cout_total||0).toLocaleString("fr-TN")} TND
            </div>

            <div style={{ display:"flex", alignItems:"center" }}>
              <ActionBadge action={c.action} color={c.action_color}
                bg={c.action_bg} icon={c.action_icon}/>
            </div>
          </div>
        ))}

        {/* Pagination */}
        {total > LIMIT && (
          <div style={{ padding:"14px 20px", borderTop:"1px solid #f1f5f9",
            display:"flex", justifyContent:"space-between", alignItems:"center" }}>
            <span style={{ fontSize:"12px", color:"#94a3b8" }}>
              {page*LIMIT + 1}–{Math.min((page+1)*LIMIT, total)} sur {total} clients
            </span>
            <div style={{ display:"flex", gap:"8px" }}>
              <button disabled={page===0}
                onClick={() => { setPage(p=>p-1); fetchData((page-1)*LIMIT); }}
                style={{ padding:"6px 14px", borderRadius:"7px", fontSize:"12px",
                  border:"1px solid #e2e8f0", background: page===0?"#f8fafc":"#fff",
                  color: page===0?"#cbd5e1":"#334155", cursor: page===0?"not-allowed":"pointer" }}>
                ← Préc.
              </button>
              <button disabled={(page+1)*LIMIT >= total}
                onClick={() => { setPage(p=>p+1); fetchData((page+1)*LIMIT); }}
                style={{ padding:"6px 14px", borderRadius:"7px", fontSize:"12px",
                  border:"1px solid #e2e8f0",
                  background:(page+1)*LIMIT>=total?"#f8fafc":"#fff",
                  color:(page+1)*LIMIT>=total?"#cbd5e1":"#334155",
                  cursor:(page+1)*LIMIT>=total?"not-allowed":"pointer" }}>
                Suiv. →
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Panneau détail */}
      {loadingDetail && (
        <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,0.2)", zIndex:999,
          display:"flex", alignItems:"center", justifyContent:"center" }}>
          <RefreshCw size={28} color="#fff" style={{ animation:"spin 1s linear infinite" }}/>
        </div>
      )}
      <DetailPanel client={detail} onClose={() => setDetail(null)}/>

      <style jsx global>{`
        @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
      `}</style>
    </Layout>
  );
}