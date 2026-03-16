import Sidebar from "./Sidebar";

export default function Layout({ children, alertCount = 0, fullHeight = false }) {
  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Sidebar alertCount={alertCount} />
      <main style={{
        marginLeft: "220px",
        flex: 1,
        height: "100vh",
        overflowY: fullHeight ? "hidden" : "auto",
        padding: fullHeight ? "28px 32px" : "32px 36px",
        background: "#f0f4f8",
        display: "flex",
        flexDirection: "column",
      }}>
        {children}
      </main>
    </div>
  );
}