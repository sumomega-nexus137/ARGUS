"use client";

import { CrashCard } from "@/components/common/CrashCard";

export default function AreaScreenError({ error, retry, reset }: { error: Error & { digest?: string }; retry?: () => void; reset?: () => void }) {
  return <div className="h-full overflow-auto"><CrashCard error={error} retry={retry ?? reset} /></div>;
}
