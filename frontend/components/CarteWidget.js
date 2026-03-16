import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/router";
import { MapPin, ExternalLink } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getColor(nb, max) {
  if (!nb || max === 0) return "#93c5fd";
  const r = nb / max;
  if (r > 0.75) return "#dc2626";
  if (r > 0.50) return "#f97316";
  if (r > 0.25) return "#fbbf24";
  return "#34d399";
}

export default function CarteWidget() {
  const router     = useRouter();
  const mapRef     = useRef(null);
  const markersRef = useRef([]);
  const [geoData,  setGeoData]  = useState([]);
  const [mapReady, setMapReady] = useState(false);

  const maxVal = geoData.length > 0 ? Math.max(...geoData.map(g => g.nb_sinistres||0)) : 1;
  const top3   = geoData.slice(0, 3);

  useEffect(() => {
    fetch(`${API}/api/geo/sinistres`)
      .then(r => r.json())
      .then(d => setGeoData(d.gouvernorats || []))
      .catch(console.error);
  }, []);

  // Init carte
  useEffect(() => {
    if (mapRef.current) return;
    const L = require("leaflet");
    require("leaflet/dist/leaflet.css");
    const map = L.map("carte-widget-map", {
      center: [33.8, 9.5], zoom: 5,
      zoomControl: false,
      attributionControl: false,
      dragging: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
      touchZoom: false,
    });
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png", {
      subdomains: "abcd", maxZoom: 19,
    }).addTo(map);
    mapRef.current = map;
    setMapReady(true);
    return () => { if(mapRef.current){ mapRef.current.remove(); mapRef.current = null; } };
  }, []);

  // Cercles
  useEffect(() => {
    if (!mapReady || !mapRef.current || geoData.length === 0) return;
    const L = require("leaflet");
    markersRef.current.forEach(m => m.remove());
    markersRef.current = [];

    geoData.forEach(g => {
      if (!g.lat || !g.lng) return;
      const color  = getColor(g.nb_sinistres, maxVal);
      const radius = 6 + (g.nb_sinistres / maxVal) * 18;

      const circle = L.circleMarker([g.lat, g.lng], {
        radius, fillColor: color,
        color: "rgba(255,255,255,0.8)", weight: 1.5,
        fillOpacity: 0.85, opacity: 1,
      }).addTo(mapRef.current);

      circle.bindTooltip(
        `<strong>${g.gouvernorat}</strong><br/>${g.nb_sinistres} sinistres`,
        { direction:"top", className:"widget-tooltip" }
      );

      markersRef.current.push(circle);
    });
  }, [geoData, mapReady]);

  return (
    <div style={{ background:"#fff", borderRadius:"14px", border:"1px solid #e2e8f0",
      boxShadow:"0 1px 4px rgba(15,31,61,0.06)", overflow:"hidden" }}>

      {/* Header */}
      <div style={{ padding:"16px 20px", display:"flex", justifyContent:"space-between",
        alignItems:"center", borderBottom:"1px solid #f1f5f9" }}>
        <div style={{ display:"flex", alignItems:"center", gap:"8px" }}>
          <MapPin size={15} color="#2563eb"/>
          <h3 style={{ fontSize:"14px", fontWeight:700, color:"#0f1f3d" }}>Sinistres par Gouvernorat</h3>
        </div>
        <button onClick={() => router.push("/carte")} style={{
          display:"flex", alignItems:"center", gap:"5px",
          fontSize:"11px", color:"#2563eb", fontWeight:600,
          background:"#eff6ff", border:"none", borderRadius:"6px",
          padding:"5px 10px", cursor:"pointer",
        }}>
          Voir la carte <ExternalLink size={11}/>
        </button>
      </div>

      {/* Carte miniature */}
      <div id="carte-widget-map" style={{ height:"200px", width:"100%" }}/>

      {/* Top 3 */}
      <div style={{ padding:"12px 16px", borderTop:"1px solid #f1f5f9" }}>
        <div style={{ fontSize:"10px", fontWeight:700, color:"#94a3b8",
          textTransform:"uppercase", letterSpacing:"0.05em", marginBottom:"8px" }}>
          Top gouvernorats
        </div>
        <div style={{ display:"flex", flexDirection:"column", gap:"6px" }}>
          {top3.map((g, i) => {
            const pct = (g.nb_sinistres / maxVal) * 100;
            const medals = ["🥇","🥈","🥉"];
            return (
              <div key={g.gouvernorat}>
                <div style={{ display:"flex", justifyContent:"space-between",
                  alignItems:"center", marginBottom:"3px" }}>
                  <div style={{ display:"flex", alignItems:"center", gap:"6px" }}>
                    <span style={{ fontSize:"13px" }}>{medals[i]}</span>
                    <span style={{ fontSize:"12px", fontWeight:600, color:"#0f1f3d" }}>
                      {g.gouvernorat}
                    </span>
                  </div>
                  <span style={{ fontSize:"12px", fontWeight:700,
                    color:getColor(g.nb_sinistres, maxVal) }}>
                    {g.nb_sinistres}
                  </span>
                </div>
                <div style={{ height:"3px", background:"#f1f5f9", borderRadius:"4px" }}>
                  <div style={{ height:"100%", width:`${pct}%`,
                    background:getColor(g.nb_sinistres, maxVal),
                    borderRadius:"4px", transition:"width 0.6s ease" }}/>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <style jsx global>{`
        .widget-tooltip {
          border-radius:8px !important;
          border:1px solid #e2e8f0 !important;
          box-shadow:0 4px 12px rgba(0,0,0,0.1) !important;
          font-family:-apple-system,sans-serif !important;
          font-size:12px !important;
        }
      `}</style>
    </div>
  );
}
