import dynamic from "next/dynamic";
import Layout from "../components/Layout";

const MLOpsContent = dynamic(() => import("../components/MLOpsContent"), { ssr: false });

export default function MLOpsPage() {
  return (
    <Layout>
      <MLOpsContent />
    </Layout>
  );
}