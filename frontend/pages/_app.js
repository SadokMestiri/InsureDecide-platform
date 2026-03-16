import "../styles/globals.css";
import { useEffect, useState } from "react";
import { FilterProvider } from "../lib/FilterContext";

export default function App({ Component, pageProps }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  // Toujours wrapper dans FilterProvider — même pendant le SSR placeholder
  return (
    <FilterProvider>
      {!mounted ? (
        <div style={{ display: "flex", minHeight: "100vh" }}>
          <aside style={{
            width: "220px", minHeight: "100vh",
            background: "#0f1f3d", position: "fixed",
            left: 0, top: 0, bottom: 0, zIndex: 100,
          }} />
          <main style={{ marginLeft: "220px", flex: 1, background: "#f0f4f8" }} />
        </div>
      ) : (
        <Component {...pageProps} />
      )}
    </FilterProvider>
  );
}