import { useState, useEffect, useRef } from "react";
import Layout from "./Layout";
import { Filter, RefreshCw } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const DEPT_COLORS = { tous:"#2563eb", Automobile:"#2563eb", Immobilier:"#f59e0b" };

function getColor(nb, max) {
  if (!nb || max === 0) return "#93c5fd";
  const r = nb / max;
  if (r > 0.75) return "#dc2626";
  if (r > 0.50) return "#f97316";
  if (r > 0.25) return "#fbbf24";
  return "#34d399";
}

export default function CarteContent() {
  const mapRef     = useRef(null);
  const markersRef = useRef([]);
  const [geoData,  setGeoData]  = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [dept,     setDept]     = useState("tous");
  const [selected, setSelected] = useState(null);
  const [detail,   setDetail]   = useState(null);
  const [mapReady, setMapReady] = useState(false);

  const maxVal   = geoData.length > 0 ? Math.max(...geoData.map(g => g.nb_sinistres||0)) : 1;
  const totalSin = geoData.reduce((s,g) => s + (g.nb_sinistres||0), 0);
  const totalFrau= geoData.reduce((s,g) => s + (g.nb_fraudes||0), 0);
  const maxGov   = geoData[0];
  const govMap   = Object.fromEntries(geoData.map(g => [g.gouvernorat, g]));

  const fetchData = async (d = "tous") => {
    setLoading(true);
    try {
      const url = d === "tous" ? `${API}/api/geo/sinistres` : `${API}/api/geo/sinistres?departement=${d}`;
      const r = await fetch(url);
      const json = await r.json();
      setGeoData(json.gouvernorats || []);
    } catch(e) { console.error(e); }
    finally { setLoading(false); }
  };

  const fetchDetail = async (gov) => {
    try {
      const r = await fetch(`${API}/api/geo/gouvernorat/${encodeURIComponent(gov)}`);
      setDetail(await r.json());
    } catch(e) { console.error(e); }
  };

  // Init carte Leaflet une seule fois
  useEffect(() => {
    if (mapRef.current) return;
    const L = require("leaflet");
    require("leaflet/dist/leaflet.css");

    const map = L.map("tunisia-map", {
      center: [33.8, 9.5], zoom: 6,
      zoomControl: true,
      attributionControl: false,
    });

    // Tile CartoDB Positron — fond blanc très épuré
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png", {
      subdomains: "abcd", maxZoom: 19,
    }).addTo(map);

    // Noms de lieux discrets par dessus
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png", {
      subdomains: "abcd", maxZoom: 19, opacity: 0.5,
    }).addTo(map);

    mapRef.current = map;
    setMapReady(true);
    return () => { if(mapRef.current){ mapRef.current.remove(); mapRef.current = null; } };
  }, []);

  // Mise à jour des cercles à chaque changement de données
  useEffect(() => {
    if (!mapReady || !mapRef.current || geoData.length === 0) return;
    const L = require("leaflet");

    markersRef.current.forEach(m => m.remove());
    markersRef.current = [];

    geoData.forEach(g => {
      if (!g.lat || !g.lng) return;
      const color  = getColor(g.nb_sinistres, maxVal);
      const radius = 10 + (g.nb_sinistres / maxVal) * 36;
      const isSel  = g.gouvernorat === selected;

      const circle = L.circleMarker([g.lat, g.lng], {
        radius,
        fillColor:   color,
        color:       isSel ? "#1e3a8a" : "rgba(255,255,255,0.9)",
        weight:      isSel ? 3 : 2,
        opacity:     1,
        fillOpacity: isSel ? 1 : 0.82,
      }).addTo(mapRef.current);

      circle.bindTooltip(`
        <div style="font-family:-apple-system,sans-serif;min-width:175px">
          <div style="font-size:14px;font-weight:700;color:#0f1f3d;margin-bottom:6px;border-bottom:1px solid #e2e8f0;padding-bottom:5px">
            📍 ${g.gouvernorat}
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:3px">
            <span style="color:#64748b;font-size:12px">Sinistres</span>
            <span style="color:#ef4444;font-weight:700;font-size:12px">${g.nb_sinistres}</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:3px">
            <span style="color:#64748b;font-size:12px">Coût moyen</span>
            <span style="color:#0f1f3d;font-weight:600;font-size:12px">${(g.cout_moyen||0).toLocaleString("fr-TN")} TND</span>
          </div>
          ${g.nb_fraudes > 0 ? `
          <div style="display:flex;justify-content:space-between">
            <span style="color:#64748b;font-size:12px">Fraudes</span>
            <span style="color:#f59e0b;font-weight:700;font-size:12px">⚠️ ${g.nb_fraudes}</span>
          </div>` : ""}
          <div style="margin-top:6px;font-size:10px;color:#94a3b8;text-align:center">Cliquer pour le détail</div>
        </div>
      `, {
        direction: "top",
        offset: L.point(0, -radius),
        className: "insure-tooltip",
      });

      circle.on("mouseover", function() {
        this.setStyle({ fillOpacity: 1, weight: 2.5 });
        this.bringToFront();
      });
      circle.on("mouseout", function() {
        this.setStyle({ fillOpacity: isSel ? 1 : 0.82, weight: isSel ? 3 : 2 });
      });
      circle.on("click", () => {
        setSelected(g.gouvernorat);
        fetchDetail(g.gouvernorat);
      });

      markersRef.current.push(circle);
    });
  }, [geoData, mapReady, selected]);

  useEffect(() => { fetchData(dept); }, [dept]);

  return (
    <Layout>
      {/* En-tête */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:"22px"}}>
        <div>
          <h1 style={{fontSize:"24px",fontWeight:700,color:"#0f1f3d",letterSpacing:"-0.02em"}}>
            Carte des Sinistres
          </h1>
          <p style={{fontSize:"13px",color:"#94a3b8",marginTop:"3px"}}>
            Analyse géographique par gouvernorat — Tunisie
          </p>
        </div>
        <div style={{display:"flex",alignItems:"center",gap:"8px"}}>
          <Filter size={13} color="#64748b"/>
          {["tous","Automobile","Immobilier"].map(d => (
            <button key={d} onClick={() => setDept(d)} style={{
              padding:"7px 16px", borderRadius:"20px", fontSize:"12px", fontWeight:600,
              border:`1.5px solid ${dept===d ? (DEPT_COLORS[d]||"#2563eb") : "#e2e8f0"}`,
              background: dept===d ? (DEPT_COLORS[d]||"#2563eb") : "#fff",
              color: dept===d ? "#fff" : "#64748b",
              cursor:"pointer", transition:"all 0.2s",
            }}>{d === "tous" ? "Tous" : d}</button>
          ))}
        </div>
      </div>

      {/* KPI Cards */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:"14px",marginBottom:"22px"}}>
        {[
          { label:"Total Sinistres",    value:totalSin.toLocaleString("fr-TN"),  color:"#ef4444", bg:"#fef2f2", icon:"⚠️", sub:"tous gouvernorats" },
          { label:"Fraudes Suspectées", value:totalFrau.toLocaleString("fr-TN"), color:"#f59e0b", bg:"#fffbeb", icon:"🔍", sub:"à investiguer" },
          { label:"Gouvernorat N°1",    value:maxGov?.gouvernorat||"—",          color:"#2563eb", bg:"#eff6ff", icon:"📍", sub:maxGov?`${maxGov.nb_sinistres} sinistres`:"" },
        ].map(({label,value,color,bg,icon,sub}) => (
          <div key={label} style={{background:bg,borderRadius:"14px",padding:"18px 22px",
            border:`1px solid ${color}22`,display:"flex",alignItems:"center",gap:"16px",
            boxShadow:"0 2px 8px rgba(0,0,0,0.04)"}}>
            <div style={{fontSize:"28px"}}>{icon}</div>
            <div>
              <div style={{fontSize:"22px",fontWeight:800,color,lineHeight:1}}>{value}</div>
              <div style={{fontSize:"12px",color:"#64748b",fontWeight:600,marginTop:"3px"}}>{label}</div>
              {sub && <div style={{fontSize:"11px",color:"#94a3b8",marginTop:"1px"}}>{sub}</div>}
            </div>
          </div>
        ))}
      </div>

      {/* Carte + Classement */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 285px",gap:"20px"}}>

        {/* Carte Leaflet */}
        <div style={{background:"#fff",borderRadius:"16px",border:"1px solid #e2e8f0",
          overflow:"hidden",position:"relative",boxShadow:"0 4px 20px rgba(0,0,0,0.05)"}}>
          {loading && (
            <div style={{position:"absolute",inset:0,display:"flex",alignItems:"center",
              justifyContent:"center",background:"rgba(255,255,255,0.85)",zIndex:1000}}>
              <div style={{display:"flex",alignItems:"center",gap:"10px",background:"#fff",
                padding:"14px 22px",borderRadius:"12px",boxShadow:"0 4px 16px rgba(0,0,0,0.1)"}}>
                <RefreshCw size={16} color="#2563eb" style={{animation:"spin 1s linear infinite"}}/>
                <span style={{fontSize:"13px",color:"#64748b",fontWeight:500}}>Chargement…</span>
              </div>
            </div>
          )}
          <div id="tunisia-map" style={{height:"530px",width:"100%"}}/>

          {/* Légende */}
          <div style={{position:"absolute",bottom:"20px",left:"20px",
            background:"rgba(255,255,255,0.97)",borderRadius:"12px",padding:"14px 16px",
            zIndex:500,border:"1px solid #e2e8f0",boxShadow:"0 4px 16px rgba(0,0,0,0.08)"}}>
            <div style={{fontSize:"11px",fontWeight:700,color:"#0f1f3d",marginBottom:"10px",
              textTransform:"uppercase",letterSpacing:"0.05em"}}>
              Sinistres
            </div>
            {[["#34d399","Faible"],["#fbbf24","Modéré"],["#f97316","Élevé"],["#dc2626","Critique"]].map(([c,l]) => (
              <div key={l} style={{display:"flex",alignItems:"center",gap:"8px",marginBottom:"6px"}}>
                <div style={{width:14,height:14,borderRadius:"50%",background:c,
                  boxShadow:`0 0 0 2px ${c}40`}}/>
                <span style={{fontSize:"11px",color:"#64748b"}}>{l}</span>
              </div>
            ))}
            <div style={{fontSize:"10px",color:"#94a3b8",marginTop:"8px",borderTop:"1px solid #f1f5f9",paddingTop:"8px"}}>
              Taille ∝ nombre de sinistres
            </div>
          </div>
        </div>

        {/* Classement */}
        <div style={{background:"#fff",borderRadius:"16px",border:"1px solid #e2e8f0",
          overflow:"hidden",boxShadow:"0 4px 20px rgba(0,0,0,0.05)"}}>
          <div style={{padding:"16px 18px",
            background:"linear-gradient(135deg,#0f1f3d 0%,#1e3a8a 100%)"}}>
            <h3 style={{fontSize:"14px",fontWeight:700,color:"#fff"}}>🏆 Classement</h3>
            <p style={{fontSize:"11px",color:"#93c5fd",marginTop:"2px"}}>Cliquer pour le détail</p>
          </div>
          <div style={{overflowY:"auto",maxHeight:"466px"}}>
            {geoData.slice(0,15).map((g,i) => {
              const pct  = (g.nb_sinistres / maxVal) * 100;
              const isSel = selected === g.gouvernorat;
              const medal = i===0?"🥇":i===1?"🥈":i===2?"🥉":`#${i+1}`;
              return (
                <div key={g.gouvernorat}
                  onClick={() => { setSelected(g.gouvernorat); fetchDetail(g.gouvernorat); }}
                  style={{padding:"11px 16px",cursor:"pointer",
                    background: isSel ? "#eff6ff" : "#fff",
                    borderLeft:`3px solid ${isSel?"#2563eb":"transparent"}`,
                    borderBottom:"1px solid #f8fafc",transition:"all 0.15s"}}>
                  <div style={{display:"flex",justifyContent:"space-between",
                    alignItems:"center",marginBottom:"6px"}}>
                    <div style={{display:"flex",alignItems:"center",gap:"8px"}}>
                      <span style={{fontSize:i<3?"14px":"11px",width:"20px",
                        color:i<3?"inherit":"#94a3b8",fontWeight:700}}>{medal}</span>
                      <span style={{fontSize:"12px",fontWeight:600,color:"#0f1f3d"}}>{g.gouvernorat}</span>
                    </div>
                    <span style={{fontSize:"13px",fontWeight:700,
                      color:getColor(g.nb_sinistres,maxVal)}}>
                      {g.nb_sinistres}
                    </span>
                  </div>
                  <div style={{height:"4px",background:"#f1f5f9",borderRadius:"4px",overflow:"hidden"}}>
                    <div style={{height:"100%",width:`${pct}%`,
                      background:getColor(g.nb_sinistres,maxVal),
                      borderRadius:"4px",transition:"width 0.6s ease"}}/>
                  </div>
                  {g.nb_fraudes > 0 &&
                    <div style={{fontSize:"10px",color:"#f59e0b",marginTop:"4px",fontWeight:500}}>
                      🔍 {g.nb_fraudes} fraudes suspectées
                    </div>}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Panneau détail */}
      {detail && (
        <div style={{marginTop:"20px",background:"#fff",borderRadius:"16px",
          border:"1px solid #e2e8f0",padding:"26px",
          boxShadow:"0 4px 20px rgba(0,0,0,0.05)"}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:"20px"}}>
            <div>
              <h2 style={{fontSize:"17px",fontWeight:700,color:"#0f1f3d"}}>
                📍 {detail.gouvernorat}
              </h2>
              <p style={{fontSize:"12px",color:"#94a3b8",marginTop:"3px"}}>
                {detail.nb_clients?.toLocaleString("fr-TN")} clients assurés dans ce gouvernorat
              </p>
            </div>
            <button onClick={() => { setDetail(null); setSelected(null); }} style={{
              border:"1px solid #e2e8f0",background:"#fff",borderRadius:"10px",
              padding:"8px 18px",cursor:"pointer",color:"#64748b",fontSize:"12px",fontWeight:600,
              transition:"all 0.15s"}}>
              ✕ Fermer
            </button>
          </div>
          <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:"14px",marginBottom:"20px"}}>
            {[
              {label:"Total sinistres",    val:detail.sinistres_dept?.reduce((s,d)=>s+d.nb_sinistres,0)||0, color:"#ef4444",bg:"#fef2f2"},
              {label:"Fraudes suspectées", val:detail.sinistres_dept?.reduce((s,d)=>s+d.nb_fraudes,0)||0,  color:"#f59e0b",bg:"#fffbeb"},
              {label:"Clients assurés",    val:(detail.nb_clients||0).toLocaleString("fr-TN"),             color:"#2563eb",bg:"#eff6ff"},
            ].map(({label,val,color,bg}) => (
              <div key={label} style={{background:bg,borderRadius:"12px",padding:"16px",
                textAlign:"center",border:`1px solid ${color}22`}}>
                <div style={{fontSize:"26px",fontWeight:800,color}}>{val}</div>
                <div style={{fontSize:"11px",color:"#64748b",marginTop:"4px",fontWeight:500}}>{label}</div>
              </div>
            ))}
          </div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"16px"}}>
            <div>
              <h4 style={{fontSize:"11px",fontWeight:700,color:"#64748b",textTransform:"uppercase",
                letterSpacing:"0.06em",marginBottom:"10px"}}>Par Département</h4>
              {detail.sinistres_dept?.map(d => (
                <div key={d.departement} style={{background:"#f8fafc",borderRadius:"10px",
                  padding:"12px 16px",marginBottom:"8px",
                  borderLeft:`3px solid ${DEPT_COLORS[d.departement]||"#2563eb"}`}}>
                  <div style={{display:"flex",justifyContent:"space-between"}}>
                    <span style={{fontSize:"13px",fontWeight:600,color:"#0f1f3d"}}>{d.departement}</span>
                    <span style={{fontSize:"13px",color:"#ef4444",fontWeight:700}}>{d.nb_sinistres} sin.</span>
                  </div>
                  <div style={{fontSize:"11px",color:"#64748b",marginTop:"4px"}}>
                    Coût moyen : {d.cout_moyen?.toLocaleString("fr-TN")} TND
                    {d.nb_fraudes > 0 &&
                      <span style={{color:"#f59e0b",marginLeft:"10px",fontWeight:600}}>
                        ⚠️ {d.nb_fraudes} fraudes
                      </span>}
                  </div>
                </div>
              ))}
            </div>
            <div>
              <h4 style={{fontSize:"11px",fontWeight:700,color:"#64748b",textTransform:"uppercase",
                letterSpacing:"0.06em",marginBottom:"10px"}}>Sinistres les plus coûteux</h4>
              {detail.top_sinistres?.map((s,i) => (
                <div key={i} style={{background:"#f8fafc",borderRadius:"10px",
                  padding:"12px 16px",marginBottom:"8px",border:"1px solid #e2e8f0"}}>
                  <div style={{display:"flex",justifyContent:"space-between"}}>
                    <span style={{fontSize:"11px",color:"#94a3b8",fontFamily:"monospace"}}>{s.contrat_id}</span>
                    <span style={{fontSize:"13px",fontWeight:700,color:"#ef4444"}}>
                      {s.cout?.toLocaleString("fr-TN")} TND
                    </span>
                  </div>
                  <div style={{fontSize:"11px",color:"#94a3b8",marginTop:"3px"}}>
                    {s.departement} · {s.type} · {s.date}
                    {s.fraude && <span style={{color:"#f59e0b",marginLeft:"8px",fontWeight:600}}>⚠️ Fraude</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <style jsx global>{`
        @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        .insure-tooltip {
          background:#fff !important;
          border:1px solid #e2e8f0 !important;
          border-radius:12px !important;
          box-shadow:0 8px 24px rgba(0,0,0,0.12) !important;
          padding:12px 16px !important;
          font-family:-apple-system,sans-serif !important;
        }
        .insure-tooltip::before { display:none !important; }
        .leaflet-container { font-family:-apple-system,sans-serif !important; }
        .leaflet-control-attribution { display:none !important; }
      `}</style>
    </Layout>
  );
}