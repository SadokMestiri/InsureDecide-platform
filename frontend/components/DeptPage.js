import { useState, useEffect, useCallback } from "react";
import Layout from "../components/Layout";
import KPICard from "../components/KPICard";
import AlerteCard from "../components/AlerteCard";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, AreaChart, Area, Legend
} from "recharts";
import { RefreshCw, TrendingUp, DollarSign, Shield, Users, ChevronDown } from "lucide-react";
import { api } from "../lib/api";
import { useFilters } from "../lib/FilterContext";
import FilterBar from "../components/FilterBar";

const DEPT_COLOR = { Automobile: "#2563eb", Vie: "#10b981", Immobilier: "#f59e0b" };

const INDICATEURS = [
  { value: "ratio_combine_pct",    label: "Ratio Combiné (%)" },
  { value: "primes_acquises_tnd",  label: "Primes Acquises (TND)" },
  { value: "cout_sinistres_tnd",   label: "Coût Sinistres (TND)" },
  { value: "taux_resiliation_pct", label: "Taux Résiliation (%)" },
  { value: "nb_sinistres",         label: "Nombre Sinistres" },
  { value: "provision_totale_tnd", label: "Provisions (TND)" },
  { value: "cout_moyen_sinistre_tnd", label: "Coût Moyen Sinistre (TND)" },
  { value: "nb_suspicions_fraude", label: "Suspicions Fraude" },
];

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background:"#fff", border:"1px solid #e2e8f0", borderRadius:"8px", padding:"10px 14px", boxShadow:"0 4px 16px rgba(0,0,0,0.08)" }}>
      <p style={{ fontSize:"11px", color:"#64748b", marginBottom:"6px", fontWeight:600 }}>{label}</p>
      {payload.map(p => (
        <div key={p.name} style={{ display:"flex", alignItems:"center", gap:"6px", marginBottom:"2px" }}>
          <div style={{ width:8, height:8, borderRadius:"50%", background:p.color||p.stroke }} />
          <span style={{ fontSize:"12px", fontWeight:600, color:"#0f1f3d" }}>
            {typeof p.value === "number" ? p.value.toFixed(2) : p.value}
          </span>
        </div>
      ))}
    </div>
  );
};

export default function DeptPage({ departement }) {
  const { annee, mois } = useFilters();
  const [kpi, setKpi]             = useState(null);
  const [evolution, setEvolution] = useState([]);
  const [alertes, setAlertes]     = useState([]);
  const [indicateur, setIndicateur] = useState("ratio_combine_pct");
  const [loading, setLoading]     = useState(true);
  const color = DEPT_COLOR[departement] || "#2563eb";

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [depts, evo, alts] = await Promise.all([
        api.departements(annee, mois),
        api.evolution(indicateur, { departement, annee_debut: 2020, annee_fin: 2024 }),
        api.alertes(6),
      ]);
      const found = depts.find(d => d.departement === departement);
      setKpi(found || null);
      // Pivot série temporelle
      const map = {};
      (evo.series || []).forEach(pt => {
        if (!map[pt.periode]) map[pt.periode] = { periode: pt.periode };
        map[pt.periode].valeur = pt.valeur;
      });
      setEvolution(Object.values(map));
      setAlertes(alts.filter(a => a.departement === departement));
    } catch(e) { console.error(e); }
    finally { setLoading(false); }
  }, [departement, indicateur]);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading && !kpi) return (
    <Layout>
      <div style={{ display:"flex", alignItems:"center", justifyContent:"center", height:"60vh" }}>
        <RefreshCw size={28} color={color} style={{ animation:"spin 1s linear infinite" }} />
      </div>
    </Layout>
  );

  const indicLabel = INDICATEURS.find(i => i.value === indicateur)?.label || "";

  return (
    <Layout alertCount={alertes.filter(a=>a.severite==="critique").length}>
      {/* En-tête */}
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:"32px" }} className="animate-fade-up">
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:"12px" }}>
            <div style={{ width:4, height:32, background:color, borderRadius:2 }} />
            <h1 style={{ fontSize:"24px", fontWeight:700, color:"#0f1f3d", letterSpacing:"-0.02em" }}>
              Département {departement}
            </h1>
          </div>
          <p style={{ fontSize:"13px", color:"#94a3b8", marginTop:"6px", marginLeft:"16px" }}>
            Période : <strong style={{ color:"#64748b" }}>{kpi?.periode}</strong>
          </p>
        </div>
        <button onClick={loadData} style={{ display:"flex", alignItems:"center", gap:"7px", padding:"8px 16px", borderRadius:"8px", background:"#fff", border:"1px solid #e2e8f0", color:"#64748b", fontSize:"13px", cursor:"pointer" }}>
          <RefreshCw size={13} style={{ animation: loading?"spin 1s linear infinite":"none" }} />
          Actualiser
        </button>
      </div>

      {/* KPI Cards */}
      <section style={{ marginBottom:"36px" }}>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(4, 1fr)", gap:"16px" }}>
          <KPICard title="Contrats Actifs"    value={kpi?.nb_contrats_actifs||0}    format="num" icon={Users}      color="neutral" delay={50} />
          <KPICard title="Primes Acquises"    value={kpi?.primes_acquises_tnd||0}   format="tnd" icon={DollarSign} color="neutral" delay={100} />
          <KPICard title="Ratio Combiné"      value={kpi?.ratio_combine_pct||0}     format="pct" icon={TrendingUp}
            color={kpi?.ratio_combine_pct>110?"danger":kpi?.ratio_combine_pct>95?"warning":"success"}
            trend={kpi?.tendance_ratio} variation={kpi?.variation_ratio_pct} delay={150} />
          <KPICard title="Suspicions Fraude"  value={kpi?.nb_suspicions_fraude||0}  format="num" icon={Shield}
            color={kpi?.nb_suspicions_fraude>5?"warning":"neutral"} delay={200} />
        </div>
      </section>

      {/* Ligne 2 : métriques secondaires */}
      <section style={{ marginBottom:"36px" }}>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(4, 1fr)", gap:"16px" }}>
          {[
            { title:"Coût Sinistres",     value:kpi?.cout_sinistres_tnd||0,      format:"tnd" },
            { title:"Nb. Sinistres",      value:kpi?.nb_sinistres||0,             format:"num" },
            { title:"Coût Moyen/Sinistre",value:kpi?.cout_moyen_sinistre_tnd||0, format:"tnd" },
            { title:"Provisions Totales", value:kpi?.provision_totale_tnd||0,    format:"tnd" },
          ].map((item, i) => (
            <KPICard key={item.title} {...item} color="neutral" delay={i*50+50} />
          ))}
        </div>
      </section>

      {/* Graphique évolution */}
      <section style={{ marginBottom:"36px" }}>
        <div className="animate-fade-up stagger-3" style={{ background:"#fff", borderRadius:"14px", padding:"28px", border:"1px solid #e2e8f0", boxShadow:"0 1px 4px rgba(15,31,61,0.06)" }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"24px" }}>
            <div>
              <h3 style={{ fontSize:"15px", fontWeight:700, color:"#0f1f3d" }}>Évolution — {indicLabel}</h3>
              <p style={{ fontSize:"11px", color:"#94a3b8", marginTop:"2px" }}>2020–2024 · 60 mois de données</p>
            </div>
            <div style={{ position:"relative" }}>
              <select value={indicateur} onChange={e => setIndicateur(e.target.value)}
                style={{ padding:"6px 30px 6px 12px", borderRadius:"8px", border:"1px solid #e2e8f0", fontSize:"12px", fontWeight:500, color:"#334155", background:"#f8fafc", cursor:"pointer", appearance:"none" }}>
                {INDICATEURS.map(i => <option key={i.value} value={i.value}>{i.label}</option>)}
              </select>
              <ChevronDown size={12} style={{ position:"absolute", right:10, top:"50%", transform:"translateY(-50%)", pointerEvents:"none", color:"#94a3b8" }} />
            </div>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={evolution} margin={{ top:5, right:10, left:0, bottom:5 }}>
              <defs>
                <linearGradient id="colorGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={color} stopOpacity={0.15} />
                  <stop offset="95%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="periode" tick={{ fontSize:10, fill:"#94a3b8" }} interval={5} />
              <YAxis tick={{ fontSize:10, fill:"#94a3b8" }} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="valeur" name={indicLabel}
                stroke={color} strokeWidth={2.5}
                fill="url(#colorGrad)" dot={false} activeDot={{ r:5, fill:color }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Alertes département */}
      <section className="animate-fade-up stagger-4">
        <div style={{ marginBottom:"20px" }}>
          <h2 style={{ fontSize:"16px", fontWeight:700, color:"#0f1f3d" }}>Alertes — {departement}</h2>
          <p style={{ fontSize:"12px", color:"#94a3b8", marginTop:"3px" }}>{alertes.length} anomalie{alertes.length!==1?"s":""} sur les 6 derniers mois</p>
        </div>
        {alertes.length === 0 ? (
          <div style={{ background:"#ecfdf5", border:"1px solid #a7f3d0", borderRadius:"10px", padding:"20px", textAlign:"center", color:"#065f46", fontSize:"13px" }}>
            ✅ Aucune anomalie — indicateurs dans les seuils normaux.
          </div>
        ) : (
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"12px" }}>
            {alertes.map((a, i) => <AlerteCard key={a.id} alerte={a} delay={i*50} />)}
          </div>
        )}
      </section>

      <style jsx global>{`@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}`}</style>
    </Layout>
  );
}