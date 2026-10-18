import { redirect } from "next/navigation";

import { ClientRedirect } from "@/components/common/ClientRedirect";

export default function Home() {
  // a static export has no server to answer with a redirect
  if (process.env.ARGUS_STATIC_EXPORT === "1") return <ClientRedirect to="/overview" />;
  redirect("/overview");
}
