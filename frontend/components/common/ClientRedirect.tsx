"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export function ClientRedirect({ to }: { to: string }) {
  const router = useRouter();
  useEffect(() => router.replace(to), [router, to]);
  return null;
}
