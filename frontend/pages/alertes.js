import { useState, useEffect } from "react";
import Layout from "../components/Layout";
import AlerteCard from "../components/AlerteCard";
import { api } from "../lib/api";
import { AlertTriangle, AlertCircle, Info } from "lucide-react";

export default function AlertesPage() {
  const [alertes, setAlertes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [nbMois, setNbMois]   = useState(3);

  useEffect(() => {
    setLoading(true);
    api.alertes(nbMois).then(data => { setAlertes(data); setLoading(false); });
  }, [nbMois]);

  const critiques = alertes.filter(a => a.severite === "critique");
  const warnings  = alertes.filter(a => a.severite === "warning");

  return (
    <Layout alertCount={critiques.length}>
      <div style={{ marginBottom:"32px" }} className="animate-fade-up">
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
          <div>
            <h1 style={{ fontSize:"24px", fontWeight:700, color:"#0f1f3d", letterSpacing:"-0.02em" }}>Alertes & Anomalies</h1>
            <p style={{ fontSize:"13px", color:"#94a3b8", marginTop:"4px" }}>Détection automatique sur les indicateurs critiques</p>
          </div>
          <select value={nbMois} onChange={e => setNbMois(Number(e.target.value))}
            style={{ padding:"8px 16px", borderRadius:"8px", border:"1px solid #e2e8f0", fontSize:"13px", background:"#fff", cursor:"pointer" }}>
            {[1,2,3,6,12].map(n => <option key={n} value={n}>Derniers {n} mois</option>)}
          </select>
        </div>
      </div>

      {/* Compteurs */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(3, 1fr)", gap:"16px", marginBottom:"36px" }}>
        {[
          { label:"Critiques", count:critiques.length, color:"#ef4444", bg:"#fef2f2", icon:AlertCircle },
          { label:"Warnings",  count:warnings.length,  color:"#f59e0b", bg:"#fffbeb", icon:AlertTriangle },
          { label:"Total",     count:alertes.length,   color:"#2563eb", bg:"#eff6ff", icon:Info },
        ].map(({ label, count, color, bg, icon:Icon }) => (
          <div key={label} style={{ background:bg, border:`1px solid ${color}30`, borderRadius:"12px", padding:"20px 24px", display:"flex", alignItems:"center", gap:"16px" }}>
            <div style={{ background:`${color}20`, borderRadius:"10px", padding:"10px" }}>
              <Icon size={20} color={color} />
            </div>
            <div>
              <div style={{ fontSize:"28px", fontWeight:700, color }}>{count}</div>
              <div style={{ fontSize:"12px", color:"#64748b", fontWeight:500 }}>{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Alertes critiques */}
      {critiques.length > 0 && (
        <section style={{ marginBottom:"32px" }}>
          <h2 style={{ fontSize:"14px", fontWeight:700, color:"#991b1b", marginBottom:"14px", display:"flex", alignItems:"center", gap:"8px" }}>
            <AlertCircle size={15} /> Alertes Critiques ({critiques.length})
          </h2>
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"12px" }}>
            {critiques.map((a,i) => <AlerteCard key={a.id} alerte={a} delay={i*40} />)}
          </div>
        </section>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <section>
          <h2 style={{ fontSize:"14px", fontWeight:700, color:"#92400e", marginBottom:"14px", display:"flex", alignItems:"center", gap:"8px" }}>
            <AlertTriangle size={15} /> Avertissements ({warnings.length})
          </h2>
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"12px" }}>
            {warnings.map((a,i) => <AlerteCard key={a.id} alerte={a} delay={i*40} />)}
          </div>
        </section>
      )}

      {alertes.length === 0 && !loading && (
        <div style={{ background:"#ecfdf5", border:"1px solid #a7f3d0", borderRadius:"12px", padding:"40px", textAlign:"center", color:"#065f46", fontSize:"14px" }}>
          ✅ Aucune anomalie détectée sur les {nbMois} derniers mois.
        </div>
      )}
    </Layout>
  );
}
