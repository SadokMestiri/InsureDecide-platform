import dynamic from "next/dynamic";
const CarteContent = dynamic(() => import("../components/CarteContent"), { ssr: false });
export default function CartePage() { return <CarteContent />; }
