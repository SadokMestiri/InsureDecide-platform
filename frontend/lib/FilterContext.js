import { createContext, useContext, useState, useEffect } from "react";

const FilterContext = createContext(null);

const GOUVERNORATS = [
  "Tunis","Ariana","Ben Arous","Manouba","Nabeul","Zaghouan","Bizerte",
  "Béja","Jendouba","Kef","Siliana","Sousse","Monastir","Mahdia","Sfax",
  "Kairouan","Kasserine","Sidi Bouzid","Gabès","Médenine","Tataouine",
  "Gafsa","Tozeur","Kébili",
];

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function FilterProvider({ children }) {
  const [gouvernorat, setGouvernorat] = useState("");
  const [annee,       setAnnee]       = useState(null);
  const [mois,        setMois]        = useState(null);
  const [periodes,    setPeriodes]    = useState([]);

  useEffect(() => {
    fetch(`${API}/api/kpis/periodes`)
      .then(r => r.json())
      .then(data => {
        if (!Array.isArray(data) || data.length === 0) return;
        setPeriodes(data);
        // Dernière période par défaut
        setAnnee(data[0].annee);
        setMois(data[0].mois);
      })
      .catch(console.error);
  }, []);

  return (
    <FilterContext.Provider value={{
      gouvernorat, setGouvernorat,
      annee, setAnnee,
      mois,  setMois,
      periodes, GOUVERNORATS,
    }}>
      {children}
    </FilterContext.Provider>
  );
}

export function useFilters() {
  const ctx = useContext(FilterContext);
  if (!ctx) throw new Error("useFilters must be inside FilterProvider");
  return ctx;
}