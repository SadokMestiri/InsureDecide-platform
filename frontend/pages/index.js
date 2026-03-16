import { useState, useEffect, useCallback } from "react";
import Layout from "../components/Layout";
import KPICard from "../components/KPICard";
import AlerteCard from "../components/AlerteCard";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer
} from "recharts";
import { TrendingUp, DollarSign, Shield, Users, AlertTriangle, RefreshCw, ChevronDown, Wifi, WifiOff } from "lucide-react";
import { api } from "../lib/api";
import { useFilters } from "../lib/FilterContext";
import FilterBar from "../components/FilterBar";
import dynamic from "next/dynamic";
const CarteWidget = dynamic(() => import("../components/CarteWidget"), { ssr: false });
import { useWebSocket } from "../lib/useWebSocket";

const DEPT_COLORS = { Automobile: "#2563eb", Vie: "#10b981", Immobilier: "#f59e0b" };

const INDICATEURS = [
  { value: "ratio_combine_pct",    label: "Ratio Combiné (%)" },
  { value: "primes_acquises_tnd",  label: "Primes Acquises (TND)" },
  { value: "cout_sinistres_tnd",   label: "Coût Sinistres (TND)" },
  { value: "taux_resiliation_pct", label: "Taux Résiliation (%)" },
  { value: "nb_sinistres",         label: "Nombre Sinistres" },
  { value: "provision_totale_tnd", label: "Provisions (TND)" },
];

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background:"#fff", border:"1px solid #e2e8f0", borderRadius:"8px", padding:"10px 14px", boxShadow:"0 4px 16px rgba(0,0,0,0.08)" }}>
      <p style={{ fontSize:"11px", color:"#64748b", marginBottom:"6px", fontWeight:600 }}>{label}</p>
      {payload.map(p => (
        <div key={p.name} style={{ display:"flex", alignItems:"center", gap:"6px", marginBottom:"3px" }}>
          <div style={{ width:8, height:8, borderRadius:"50%", background:p.color }} />
          <span style={{ fontSize:"12px", color:"#334155" }}>{p.name}:</span>
          <span style={{ fontSize:"12px", fontWeight:600, color:"#0f1f3d" }}>{typeof p.value==="number" ? p.value.toFixed(1) : p.value}</span>
        </div>
      ))}
    </div>
  );
};

function SectionTitle({ children, sub }) {
  return (
    <div style={{ marginBottom:"20px" }}>
      <h2 style={{ fontSize:"16px", fontWeight:700, color:"#0f1f3d", letterSpacing:"-0.01em" }}>{children}</h2>
      {sub && <p style={{ fontSize:"12px", color:"#94a3b8", marginTop:"3px" }}>{sub}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const { annee, mois, gouvernorat } = useFilters();
  const [geoData, setGeoData] = useState([]);
  const [data, setData]           = useState(null);
  const [evolution, setEvolution] = useState(null);
  const [comparaison, setComparaison] = useState(null);
  const [indicateur, setIndicateur]   = useState("ratio_combine_pct");
  const [loading, setLoading]     = useState(true);
  const { data: wsData, connected: wsConnected, lastUpdate: wsUpdate, refresh: wsRefresh } = useWebSocket("dashboard");
  const [lastUpdate, setLastUpdate]   = useState(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [dash, evo, comp, geo] = await Promise.all([
        api.dashboard(annee, mois),
        api.evolution(indicateur, { annee_debut: 2022, annee_fin: 2024 }),
        api.comparaison(annee, mois),
        fetch(`${process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000"}/api/geo/sinistres`).then(r=>r.json()).catch(()=>({gouvernorats:[]})),
      ]);
      setData(dash); setEvolution(evo); setComparaison(comp);
      setGeoData(geo?.gouvernorats || []);
      setLastUpdate(new Date());
    } catch(e) { console.error(e); }
    finally { setLoading(false); }
  }, [indicateur, annee, mois]);

  useEffect(() => { loadData(); }, [loadData]);

  // Mise à jour automatique via WebSocket (toutes les 30s)
  // Le WS signale qu'il faut recharger → on recharge via HTTP (format garanti)
  useEffect(() => {
    if (!wsData) return;
    if (wsData.type === "kpi_update" || wsData.type === "pong") return; // ignorer pong
    loadData();
  }, [wsData]);

  // Pour le pong aussi on ignore, mais pour kpi_update on recharge
  useEffect(() => {
    if (!wsData || wsData.type !== "kpi_update") return;
    loadData();
  }, [wsData]);

  // Fallback polling toutes les 60s si WS déconnecté
  useEffect(() => {
    if (wsConnected) return; // WS actif → pas besoin de polling
    const t = setInterval(loadData, 60000);
    return () => clearInterval(t);
  }, [wsConnected, loadData]);

  const evolutionData = (() => {
    if (!evolution?.series) return [];
    const map = {};
    evolution.series.forEach(pt => {
      if (!map[pt.periode]) map[pt.periode] = { periode: pt.periode };
      map[pt.periode][pt.departement] = pt.valeur;
    });
    return Object.values(map).slice(-24);
  })();

  if (loading && !data) return (
    <Layout>
      <div style={{ display:"flex", alignItems:"center", justifyContent:"center", height:"60vh" }}>
        <div style={{ textAlign:"center" }}>
          <RefreshCw size={32} color="#2563eb" style={{ animation:"spin 1s linear infinite", margin:"0 auto 12px" }} />
          <p style={{ color:"#64748b", fontSize:"14px" }}>Chargement des données…</p>
        </div>
      </div>
    </Layout>
  );

  const { summary={}, par_departement=[], alertes=[] } = data || {};
  const alertesCritiques = alertes.filter(a => a.severite === "critique");

  return (
    <Layout alertCount={alertesCritiques.length}>
      {/* En-tête */}
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:"32px" }} className="animate-fade-up">
        <div>
          <h1 style={{ fontSize:"24px", fontWeight:700, color:"#0f1f3d", letterSpacing:"-0.02em" }}>Vue d'ensemble</h1>
          <p style={{ fontSize:"13px", color:"#94a3b8", marginTop:"4px" }}>
            Période : <strong style={{ color:"#64748b" }}>{summary.periode_label}</strong>
            {(wsUpdate || lastUpdate) && ` · Mis à jour ${(wsUpdate || lastUpdate).toLocaleTimeString("fr-TN")}`}
          </p>
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:"8px", fontSize:"11px",
              color: wsConnected ? "#10b981" : "#94a3b8" }}>
            {wsConnected ? <Wifi size={12}/> : <WifiOff size={12}/>}
            <span>{wsConnected ? `Temps réel · ${wsUpdate ? wsUpdate.toLocaleTimeString("fr-TN", {hour:"2-digit",minute:"2-digit",second:"2-digit"}) : ""}` : "Hors ligne"}</span>
          </div>
          <button onClick={loadData} style={{ display:"flex", alignItems:"center", gap:"7px", padding:"8px 16px", borderRadius:"8px", background:"#fff", border:"1px solid #e2e8f0", color:"#64748b", fontSize:"13px", fontWeight:500, cursor:"pointer" }}>
          <RefreshCw size={13} style={{ animation: loading ? "spin 1s linear infinite" : "none" }} />
          Actualiser
        </button>
      </div>

      <FilterBar />

      {/* Bannière alertes critiques */}
      {alertesCritiques.length > 0 && (
        <div className="animate-fade-up" style={{ background:"#fef2f2", border:"1px solid #fecaca", borderLeft:"4px solid #ef4444", borderRadius:"10px", padding:"12px 18px", display:"flex", alignItems:"center", gap:"10px", marginBottom:"28px" }}>
          <AlertTriangle size={16} color="#ef4444" />
          <span style={{ fontSize:"13px", color:"#991b1b", fontWeight:600 }}>{alertesCritiques.length} alerte{alertesCritiques.length>1?"s":""} critique{alertesCritiques.length>1?"s":""} détectée{alertesCritiques.length>1?"s":""}</span>
          <span style={{ fontSize:"12px", color:"#b91c1c", opacity:0.8 }}>— voir section Alertes ci-dessous</span>
        </div>
      )}

      {/* KPIs globaux */}
      <section style={{ marginBottom:"40px" }}>
        <SectionTitle sub="Consolidé tous départements">KPIs Globaux</SectionTitle>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(4, 1fr)", gap:"16px" }}>
          <KPICard title="Contrats Actifs"      value={summary.total_contrats_actifs||0}   format="num" icon={Users}      color="neutral" delay={50} />
          <KPICard title="Primes Acquises"       value={summary.total_primes_tnd||0}         format="tnd" icon={DollarSign} color="neutral" delay={100} />
          <KPICard title="Ratio Combiné Moyen"  value={summary.ratio_combine_moyen_pct||0} format="pct" icon={TrendingUp}
            color={summary.ratio_combine_moyen_pct>110?"danger":summary.ratio_combine_moyen_pct>95?"warning":"success"} delay={150} />
          <KPICard title="Suspicions Fraude"    value={summary.total_suspicions_fraude||0} format="num" icon={Shield}
            color={summary.total_suspicions_fraude>5?"warning":"neutral"} delay={200} />
        </div>
      </section>

      {/* Par département */}
      <section style={{ marginBottom:"40px" }}>
        <SectionTitle sub="Dernière période avec tendance vs mois précédent">Par Département</SectionTitle>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(3, 1fr)", gap:"16px" }}>
          {par_departement.map((dept, i) => (
            <div key={dept.departement} className="animate-fade-up" style={{ animationDelay:`${i*60+50}ms`, background:"#fff", borderRadius:"14px", padding:"22px", border:"1px solid #e2e8f0", boxShadow:"0 1px 4px rgba(15,31,61,0.06)", borderTop:`3px solid ${DEPT_COLORS[dept.departement]||"#2563eb"}` }}>
              <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"16px" }}>
                <h3 style={{ fontSize:"15px", fontWeight:700, color:"#0f1f3d" }}>{dept.departement}</h3>
                <span style={{ fontSize:"11px", fontWeight:600, padding:"3px 9px", borderRadius:"20px", background: dept.ratio_combine_pct>110?"#fef2f2":dept.ratio_combine_pct>95?"#fffbeb":"#ecfdf5", color: dept.ratio_combine_pct>110?"#991b1b":dept.ratio_combine_pct>95?"#92400e":"#065f46" }}>
                  RC: {dept.ratio_combine_pct.toFixed(1)}%
                </span>
              </div>
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"10px" }}>
                {[
                  { label:"Primes",      val: dept.primes_acquises_tnd>=1e6?`${(dept.primes_acquises_tnd/1e6).toFixed(2)}M`:`${(dept.primes_acquises_tnd/1000).toFixed(0)}K`, unit:"TND" },
                  { label:"Sinistres",   val: dept.nb_sinistres, unit:"cas" },
                  { label:"Résiliation", val: `${dept.taux_resiliation_pct.toFixed(1)}`, unit:"%" },
                  { label:"Provisions",  val: dept.provision_totale_tnd>=1e6?`${(dept.provision_totale_tnd/1e6).toFixed(2)}M`:`${(dept.provision_totale_tnd/1000).toFixed(0)}K`, unit:"TND" },
                ].map(item => (
                  <div key={item.label} style={{ background:"#f8fafc", borderRadius:"8px", padding:"10px 12px" }}>
                    <div style={{ fontSize:"10px", color:"#94a3b8", fontWeight:600, textTransform:"uppercase", marginBottom:"4px" }}>{item.label}</div>
                    <div style={{ fontSize:"17px", fontWeight:700, color:"#0f1f3d" }}>{item.val} <span style={{ fontSize:"11px", color:"#94a3b8" }}>{item.unit}</span></div>
                  </div>
                ))}
              </div>
              {dept.tendance_ratio && (
                <div style={{ marginTop:"12px", fontSize:"11px", color: dept.tendance_ratio==="hausse"?"#ef4444":dept.tendance_ratio==="baisse"?"#10b981":"#94a3b8" }}>
                  {dept.tendance_ratio==="hausse"?"↑":dept.tendance_ratio==="baisse"?"↓":"→"} RC {dept.tendance_ratio} de {Math.abs(dept.variation_ratio_pct||0).toFixed(1)}% vs mois précédent
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Graphiques */}
      <section style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"24px", marginBottom:"40px" }}>
        {/* Courbe évolution */}
        <div className="animate-fade-up stagger-3" style={{ background:"#fff", borderRadius:"14px", padding:"24px", border:"1px solid #e2e8f0", boxShadow:"0 1px 4px rgba(15,31,61,0.06)" }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"20px" }}>
            <div>
              <h3 style={{ fontSize:"14px", fontWeight:700, color:"#0f1f3d" }}>Évolution Temporelle</h3>
              <p style={{ fontSize:"11px", color:"#94a3b8", marginTop:"2px" }}>2022–2024 · 3 départements</p>
            </div>
            <div style={{ position:"relative" }}>
              <select value={indicateur} onChange={e => setIndicateur(e.target.value)}
                style={{ padding:"5px 28px 5px 10px", borderRadius:"7px", border:"1px solid #e2e8f0", fontSize:"11px", fontWeight:500, color:"#334155", background:"#f8fafc", cursor:"pointer", appearance:"none" }}>
                {INDICATEURS.map(i => <option key={i.value} value={i.value}>{i.label}</option>)}
              </select>
              <ChevronDown size={12} style={{ position:"absolute", right:8, top:"50%", transform:"translateY(-50%)", pointerEvents:"none", color:"#94a3b8" }} />
            </div>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={evolutionData} margin={{ top:5, right:10, left:-10, bottom:5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="periode" tick={{ fontSize:10, fill:"#94a3b8" }} interval={5} />
              <YAxis tick={{ fontSize:10, fill:"#94a3b8" }} />
              <Tooltip content={<CustomTooltip />} />
              <Legend iconSize={8} wrapperStyle={{ fontSize:"11px" }} />
              {Object.entries(DEPT_COLORS).map(([dept, color]) => (
                <Line key={dept} type="monotone" dataKey={dept} stroke={color} strokeWidth={2} dot={false} activeDot={{ r:4 }} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Barres comparaison */}
        <div className="animate-fade-up stagger-4" style={{ background:"#fff", borderRadius:"14px", padding:"24px", border:"1px solid #e2e8f0", boxShadow:"0 1px 4px rgba(15,31,61,0.06)" }}>
          <div style={{ marginBottom:"20px" }}>
            <h3 style={{ fontSize:"14px", fontWeight:700, color:"#0f1f3d" }}>Comparaison Départements</h3>
            <p style={{ fontSize:"11px", color:"#94a3b8", marginTop:"2px" }}>Primes vs Coût sinistres — {summary.periode_label}</p>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={comparaison||[]} margin={{ top:5, right:10, left:-10, bottom:5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="departement" tick={{ fontSize:11, fill:"#94a3b8" }} />
              <YAxis tick={{ fontSize:10, fill:"#94a3b8" }} tickFormatter={v => v>=1e6?`${(v/1e6).toFixed(1)}M`:`${(v/1000).toFixed(0)}K`} />
              <Tooltip formatter={v => `${(v/1000).toFixed(1)}K TND`} />
              <Legend iconSize={8} wrapperStyle={{ fontSize:"11px" }} />
              <Bar dataKey="primes_acquises_tnd"  name="Primes"          fill="#2563eb" radius={[4,4,0,0]} />
              <Bar dataKey="cout_sinistres_tnd"    name="Coût Sinistres"  fill="#f59e0b" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Widget Carte */}
      <section style={{ marginBottom:"40px" }} className="animate-fade-up stagger-5">
        <SectionTitle sub="Top gouvernorats par nombre de sinistres">Analyse Géographique</SectionTitle>
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"24px" }}>
          <CarteWidget />
          {/* Stats rapides sinistres par gouvernorat */}
          <div style={{ background:"#fff", borderRadius:"14px", border:"1px solid #e2e8f0",
            padding:"22px", boxShadow:"0 1px 4px rgba(15,31,61,0.06)" }}>
            <h3 style={{ fontSize:"14px", fontWeight:700, color:"#0f1f3d", marginBottom:"6px" }}>
              Insights Géographiques
            </h3>
            <p style={{ fontSize:"12px", color:"#94a3b8", marginBottom:"18px" }}>
              Analyse des risques par région
            </p>
            {[
              ...(geoData.length > 0 ? (() => {
                const sorted = [...geoData].sort((a,b) => (b.nb_sinistres||0)-(a.nb_sinistres||0));
                const top    = sorted[0];
                const low    = sorted[sorted.length-1];
                const avgCout = geoData.reduce((s,g)=>s+(g.cout_moyen||0),0) / geoData.length;
                const critiques = sorted.filter(g => (g.nb_sinistres||0) > (top.nb_sinistres||0)*0.7);
                return [
                  { icon:"🔴", label:`${top?.gouvernorat} — Priorité 1`, desc:`${top?.nb_sinistres} sinistres · coût moyen ${Math.round(top?.cout_moyen||0).toLocaleString("fr-TN")} TND`, color:"#fef2f2", border:"#fecaca" },
                  { icon:"📊", label:`${critiques.length} gouvernorats critiques`, desc:`Sinistralité > 70% du pic — intervention recommandée`, color:"#fff7ed", border:"#fed7aa" },
                  { icon:"✅", label:`${low?.gouvernorat} — Faible risque`, desc:`${low?.nb_sinistres} sinistres seulement — profil stable`, color:"#ecfdf5", border:"#a7f3d0" },
                  { icon:"⚠️", label:"Action CEO", desc:`Ajuster les primes dans les ${critiques.length} gouvernorats à risque élevé`, color:"#fffbeb", border:"#fde68a" },
                ];
              })() : [
                { icon:"⏳", label:"Chargement...", desc:"Calcul des insights en cours", color:"#f8fafc", border:"#e2e8f0" },
              ]),
            ].map(({ icon, label, desc, color, border }) => (
              <div key={label} style={{ background:color, border:`1px solid ${border}`,
                borderRadius:"10px", padding:"12px 14px", marginBottom:"10px",
                display:"flex", alignItems:"flex-start", gap:"10px" }}>
                <span style={{ fontSize:"18px", flexShrink:0 }}>{icon}</span>
                <div>
                  <div style={{ fontSize:"12px", fontWeight:700, color:"#0f1f3d" }}>{label}</div>
                  <div style={{ fontSize:"11px", color:"#64748b", marginTop:"2px" }}>{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Alertes */}
      <section className="animate-fade-up stagger-5">
        <SectionTitle sub={`${alertes.length} anomalies détectées sur les 3 derniers mois`}>Alertes & Anomalies</SectionTitle>
        {alertes.length === 0 ? (
          <div style={{ background:"#ecfdf5", border:"1px solid #a7f3d0", borderRadius:"10px", padding:"20px", textAlign:"center", color:"#065f46", fontSize:"13px" }}>
            ✅ Aucune anomalie détectée — tous les indicateurs sont dans les seuils normaux.
          </div>
        ) : (
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"12px" }}>
            {alertes.slice(0,8).map((a,i) => <AlerteCard key={a.id} alerte={a} delay={i*40} />)}
          </div>
        )}
      </section>

      <style jsx global>{`@keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }`}</style>
    </Layout>
  );
}