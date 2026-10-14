import type { ReactNode } from "react";

import { AreaLayoutClient } from "@/components/area/AreaLayoutClient";

// Both data profiles (DEMO and real-data) use these two operational areas; listing them lets the console be
// pre-rendered, which the static online demo requires.
export function generateStaticParams() {
  return [{ areaId: "atbasar" }, { areaId: "kokshetau" }];
}

export const dynamicParams = false;

export default function AreaLayout({ children }: { children: ReactNode }) {
  return <AreaLayoutClient>{children}</AreaLayoutClient>;
}
