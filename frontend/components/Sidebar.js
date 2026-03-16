import { useRouter } from "next/router";
import { useState, useEffect } from "react";
import { LayoutDashboard, Car, Heart, Home, Bell, MessageSquare, Activity, Rss, FlaskConical, Map, ShieldAlert } from "lucide-react";

const navItems = [
  { href: "/",           label: "Dashboard",  icon: LayoutDashboard },
  { href: "/automobile", label: "Automobile", icon: Car },
  { href: "/vie",        label: "Vie",        icon: Heart },
  { href: "/immobilier", label: "Immobilier", icon: Home },
  { href: "/alertes",    label: "Alertes",    icon: Bell, badge: true },
  { href: "/feed",       label: "Événements", icon: Rss },
  { href: "/carte",      label: "Carte",       icon: Map },
  { href: "/agent",      label: "Agent IA",   icon: MessageSquare },
  { href: "/mlops",      label: "MLOps",      icon: FlaskConical },
  { href: "/risque",     label: "Clients Risque", icon: ShieldAlert },
];

export default function Sidebar({ alertCount = 0 }) {
  const router = useRouter();
  const [currentPath, setCurrentPath] = useState("");

  // Lire le pathname uniquement côté client pour éviter le mismatch SSR
  useEffect(() => {
    setCurrentPath(router.pathname);
  }, [router.pathname]);

  return (
    <aside style={{
      width: "220px", minHeight: "100vh", flexShrink: 0,
      background: "#0f1f3d",
      display: "flex", flexDirection: "column",
      position: "fixed", left: 0, top: 0, bottom: 0,
      zIndex: 100,
    }}>
      {/* Logo */}
      <div style={{ padding: "28px 24px 20px", borderBottom: "1px solid rgba(255,255,255,0.07)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{ background: "#2563eb", borderRadius: "9px", padding: "7px", display: "flex" }}>
            <Activity size={16} color="#fff" strokeWidth={2.5} />
          </div>
          <div>
            <div style={{ color: "#fff", fontWeight: 700, fontSize: "15px", letterSpacing: "-0.01em" }}>
              InsureDecide
            </div>
            <div style={{ color: "rgba(255,255,255,0.4)", fontSize: "10px", fontWeight: 500 }}>
              CEO Dashboard
            </div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: "16px 12px", display: "flex", flexDirection: "column", gap: "2px" }}>
        {navItems.map(({ href, label, icon: Icon, badge }) => {
          const active = currentPath === href;
          return (
            <button
              key={href}
              onClick={() => router.push(href)}
              style={{
                display: "flex", alignItems: "center", gap: "10px",
                padding: "9px 12px", borderRadius: "8px",
                background: active ? "rgba(37,99,235,0.25)" : "transparent",
                border: active ? "1px solid rgba(37,99,235,0.4)" : "1px solid transparent",
                color: active ? "#93c5fd" : "rgba(255,255,255,0.65)",
                cursor: "pointer", textAlign: "left", width: "100%",
                fontSize: "13px", fontWeight: active ? 600 : 400,
                transition: "all 0.15s",
              }}
              onMouseEnter={e => { if (!active) e.currentTarget.style.background = "rgba(255,255,255,0.06)"; }}
              onMouseLeave={e => { if (!active) e.currentTarget.style.background = "transparent"; }}
            >
              <Icon size={15} strokeWidth={active ? 2.5 : 2} />
              <span style={{ flex: 1 }}>{label}</span>
              {badge && alertCount > 0 && (
                <span style={{
                  background: "#ef4444", color: "#fff",
                  borderRadius: "10px", padding: "1px 6px",
                  fontSize: "10px", fontWeight: 700,
                }}>
                  {alertCount}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      <div style={{ padding: "16px 20px", borderTop: "1px solid rgba(255,255,255,0.07)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span className="live-dot" />
          <span style={{ color: "rgba(255,255,255,0.4)", fontSize: "11px" }}>Données en direct</span>
        </div>
      </div>
    </aside>
  );
}
