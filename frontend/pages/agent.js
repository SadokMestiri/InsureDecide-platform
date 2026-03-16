import dynamic from "next/dynamic";

// Désactive le SSR pour toute la page — évite les erreurs d'hydratation
// causées par les timestamps et l'état dynamique du chat
const AgentChat = dynamic(() => import("../components/AgentChat"), { ssr: false });

export default function AgentPage() {
  return <AgentChat />;
}