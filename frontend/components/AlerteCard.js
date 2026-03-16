import { AlertTriangle, AlertCircle, Info, Car, Heart, Home } from "lucide-react";

const deptIcon = { Automobile: Car, Vie: Heart, Immobilier: Home };
const sevConfig = {
  critique: { bg: "#fef2f2", border: "#fecaca", text: "#991b1b", icon: AlertCircle, dot: "#ef4444" },
  warning:  { bg: "#fffbeb", border: "#fde68a", text: "#92400e", icon: AlertTriangle, dot: "#f59e0b" },
  info:     { bg: "#eff6ff", border: "#bfdbfe", text: "#1e40af", icon: Info, dot: "#3b82f6" },
};

export default function AlerteCard({ alerte, delay = 0 }) {
  const sev = sevConfig[alerte.severite] || sevConfig.info;
  const SevIcon = sev.icon;
  const DeptIcon = deptIcon[alerte.departement] || Info;

  return (
    <div
      className="animate-fade-up"
      style={{
        animationDelay: `${delay}ms`,
        background: sev.bg,
        border: `1px solid ${sev.border}`,
        borderLeft: `3px solid ${sev.dot}`,
        borderRadius: "10px",
        padding: "14px 16px",
        display: "flex", gap: "12px", alignItems: "flex-start",
      }}
    >
      <SevIcon size={16} color={sev.dot} style={{ marginTop: "2px", flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <DeptIcon size={12} color={sev.text} />
            <span style={{ fontSize: "11px", fontWeight: 700, color: sev.text, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              {alerte.departement}
            </span>
          </div>
          <span style={{ fontSize: "10px", color: sev.text, opacity: 0.6 }}>{alerte.periode}</span>
        </div>
        <p style={{ fontSize: "13px", fontWeight: 500, color: sev.text, marginBottom: "5px" }}>
          {alerte.message}
        </p>
        <p style={{ fontSize: "11px", color: sev.text, opacity: 0.7, fontStyle: "italic" }}>
          → {alerte.recommandation}
        </p>
      </div>
    </div>
  );
}
