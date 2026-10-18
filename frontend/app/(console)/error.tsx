"use client";

import { CrashCard } from "@/components/common/CrashCard";

export default function ConsoleError({ error, retry, reset }: { error: Error & { digest?: string }; retry?: () => void; reset?: () => void }) {
  return <CrashCard error={error} retry={retry ?? reset} />;
}
