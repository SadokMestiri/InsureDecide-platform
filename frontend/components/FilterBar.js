import { useFilters } from "../lib/FilterContext";
import { Filter, X, ChevronDown, Calendar } from "lucide-react";

const MOIS_LABELS = [
  "","Janvier","Février","Mars","Avril","Mai","Juin",
  "Juillet","Août","Septembre","Octobre","Novembre","Décembre"
];

export default function FilterBar({ showGouvernorat = false }) {
  const {
    gouvernorat, setGouvernorat,
    annee, setAnnee,
    mois,  setMois,
    periodes, GOUVERNORATS,
  } = useFilters();

  if (!periodes || periodes.length === 0) return (
    <div style={{
      background:"#fff", border:"1px solid #e2e8f0", borderRadius:"12px",
      padding:"10px 16px", marginBottom:"24px", height:"42px",
      display:"flex", alignItems:"center", gap:"10px",
      boxShadow:"0 1px 4px rgba(15,31,61,0.04)",
    }}>
      <div style={{ width:60, height:16, background:"#f1f5f9", borderRadius:6 }}/>
      <div style={{ width:1, height:18, background:"#e2e8f0" }}/>
      <div style={{ width:120, height:28, background:"#f1f5f9", borderRadius:8 }}/>
      <div style={{ width:100, height:28, background:"#f1f5f9", borderRadius:8 }}/>
    </div>
  );

  const annees     = [...new Set(periodes.map(p => p.annee))].sort((a,b) => b-a);
  const moisDispo  = periodes
    .filter(p => p.annee === annee)
    .map(p => p.mois)
    .sort((a,b) => b-a);

  const isFiltered = gouvernorat || annee !== periodes[0]?.annee;

  const reset = () => {
    setGouvernorat("");
    setAnnee(periodes[0]?.annee);
    setMois(periodes[0]?.mois);
  };

  return (
    <div style={{
      background:"#fff", border:"1px solid #e2e8f0", borderRadius:"12px",
      padding:"10px 16px", marginBottom:"24px",
      display:"flex", alignItems:"center", gap:"10px", flexWrap:"wrap",
      boxShadow:"0 1px 4px rgba(15,31,61,0.04)",
    }}>
      <div style={{ display:"flex", alignItems:"center", gap:"6px",
        fontSize:"11px", fontWeight:700, color:"#94a3b8", textTransform:"uppercase" }}>
        <Filter size={12}/> Filtres
      </div>

      <div style={{ width:"1px", height:"18px", background:"#e2e8f0" }}/>

      {/* Gouvernorat — affiché seulement si showGouvernorat=true */}
      {showGouvernorat && (
        <div style={{ position:"relative" }}>
          <select value={gouvernorat} onChange={e => setGouvernorat(e.target.value)}
            style={{
              padding:"6px 28px 6px 10px", borderRadius:"8px", appearance:"none",
              border: gouvernorat ? "1px solid #2563eb" : "1px solid #e2e8f0",
              fontSize:"12px", fontWeight:500, cursor:"pointer",
              color: gouvernorat ? "#2563eb" : "#64748b",
              background: gouvernorat ? "#eff6ff" : "#f8fafc",
              minWidth:"160px",
            }}>
            <option value="">Tous les gouvernorats</option>
            {GOUVERNORATS.map(g => <option key={g} value={g}>{g}</option>)}
          </select>
          <ChevronDown size={12} style={{ position:"absolute", right:8, top:"50%",
            transform:"translateY(-50%)", pointerEvents:"none",
            color: gouvernorat ? "#2563eb" : "#94a3b8" }}/>
        </div>
      )}

      {/* Année */}
      <div style={{ display:"flex", alignItems:"center", gap:"6px" }}>
        <Calendar size={13} color="#94a3b8"/>
        <div style={{ position:"relative" }}>
          <select value={annee || ""} onChange={e => {
            const a = Number(e.target.value);
            setAnnee(a);
            const m = periodes.filter(p => p.annee===a).map(p=>p.mois).sort((a,b)=>b-a);
            setMois(m[0] || null);
          }} style={{
            padding:"6px 28px 6px 10px", borderRadius:"8px", appearance:"none",
            border:"1px solid #e2e8f0", fontSize:"12px", fontWeight:500,
            color:"#334155", background:"#f8fafc", cursor:"pointer",
          }}>
            {annees.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
          <ChevronDown size={12} style={{ position:"absolute", right:8, top:"50%",
            transform:"translateY(-50%)", pointerEvents:"none", color:"#94a3b8" }}/>
        </div>

        {/* Mois */}
        <div style={{ position:"relative" }}>
          <select value={mois || ""} onChange={e => setMois(Number(e.target.value))}
            style={{
              padding:"6px 28px 6px 10px", borderRadius:"8px", appearance:"none",
              border:"1px solid #e2e8f0", fontSize:"12px", fontWeight:500,
              color:"#334155", background:"#f8fafc", cursor:"pointer",
            }}>
            {moisDispo.map(m => (
              <option key={m} value={m}>{MOIS_LABELS[m]}</option>
            ))}
          </select>
          <ChevronDown size={12} style={{ position:"absolute", right:8, top:"50%",
            transform:"translateY(-50%)", pointerEvents:"none", color:"#94a3b8" }}/>
        </div>
      </div>

      {/* Reset */}
      {isFiltered && (
        <>
          <div style={{ width:"1px", height:"18px", background:"#e2e8f0" }}/>
          <button onClick={reset} style={{
            display:"flex", alignItems:"center", gap:"5px",
            padding:"5px 10px", borderRadius:"8px",
            border:"1px solid #fecaca", background:"#fef2f2",
            color:"#dc2626", fontSize:"11px", fontWeight:600, cursor:"pointer",
          }}>
            <X size={11}/> Réinitialiser
          </button>
        </>
      )}
    </div>
  );
}