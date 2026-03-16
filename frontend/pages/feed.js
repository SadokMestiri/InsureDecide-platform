import dynamic from "next/dynamic";
const FeedContent = dynamic(() => import("../components/FeedContent"), { ssr: false });
export default function FeedPage() { return <FeedContent />; }
