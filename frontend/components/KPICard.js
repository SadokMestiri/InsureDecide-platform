import { TrendingUp, TrendingDown, Minus } from "lucide-react";

const fmt = {
  tnd: (v) => v >= 1_000_000
    ? `${(v / 1_000_000).toFixed(2)}M TND`
    : v >= 1_000 ? `${(v / 1_000).toFixed(1)}K TND` : `${v.toFixed(0)} TND`,
  pct:  (v) => `${v.toFixed(1)}%`,
  num:  (v) => v >= 1_000 ? `${(v / 1_000).toFixed(1)}K` : `${v}`,
};

const colorMap = {
  neutral: { bg: "#f0f4f8", icon: "#2563eb", text: "#0f1f3d" },
  success: { bg: "#ecfdf5", icon: "#10b981", text: "#065f46" },
  warning: { bg: "#fffbeb", icon: "#f59e0b", text: "#92400e" },
  danger:  { bg: "#fef2f2", icon: "#ef4444", text: "#991b1b" },
};

export default function KPICard({ title, value, format = "num", unit, trend, variation, color = "neutral", icon: Icon, delay = 0 }) {
  const clr = colorMap[color];
  const formattedValue = format === "tnd" ? fmt.tnd(value)
    : format === "pct" ? fmt.pct(value)
    : fmt.num(value);

  return (
    <div
      className="animate-fade-up"
      style={{
        animationDelay: `${delay}ms`,
        background: "#fff",
        borderRadius: "14px",
        padding: "22px 24px",
        border: "1px solid #e2e8f0",
        boxShadow: "0 1px 4px rgba(15,31,61,0.06)",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        transition: "box-shadow 0.2s, transform 0.2s",
        cursor: "default",
      }}
      onMouseEnter={e => {
        e.currentTarget.style.boxShadow = "0 8px 24px rgba(37,99,235,0.10)";
        e.currentTarget.style.transform = "translateY(-2px)";
      }}
      onMouseLeave={e => {
        e.currentTarget.style.boxShadow = "0 1px 4px rgba(15,31,61,0.06)";
        e.currentTarget.style.transform = "translateY(0)";
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <span style={{ fontSize: "12px", fontWeight: 600, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.06em" }}>
          {title}
        </span>
        {Icon && (
          <div style={{ background: clr.bg, borderRadius: "8px", padding: "7px" }}>
            <Icon size={16} color={clr.icon} strokeWidth={2} />
          </div>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "baseline", gap: "6px" }}>
        <span style={{ fontSize: "28px", fontWeight: 700, color: clr.text, lineHeight: 1, letterSpacing: "-0.02em" }}>
          {formattedValue}
        </span>
        {unit && <span style={{ fontSize: "12px", color: "#94a3b8", fontWeight: 500 }}>{unit}</span>}
      </div>

      {trend && (
        <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
          {trend === "hausse" ? <TrendingUp size={13} color="#ef4444" /> :
           trend === "baisse" ? <TrendingDown size={13} color="#10b981" /> :
           <Minus size={13} color="#94a3b8" />}
          <span style={{
            fontSize: "12px", fontWeight: 600,
            color: trend === "hausse" ? "#ef4444" : trend === "baisse" ? "#10b981" : "#94a3b8"
          }}>
            {variation !== undefined ? `${variation > 0 ? "+" : ""}${variation.toFixed(1)}%` : "Stable"}
          </span>
          <span style={{ fontSize: "11px", color: "#94a3b8" }}>vs mois précédent</span>
        </div>
      )}
    </div>
  );
}
