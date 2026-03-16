import dynamic from "next/dynamic";
const RisqueContent = dynamic(() => import("../components/RisqueContent"), { ssr: false });
export default function RisquePage() { return <RisqueContent />; }
