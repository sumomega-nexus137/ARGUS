"use client";

import dynamic from "next/dynamic";
import { useParams, usePathname } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { AreaProvider } from "@/components/area/AreaContext";
import { Timeline } from "@/components/timeline/Timeline";
import { useUi } from "@/lib/store";

const OpsMap = dynamic(() => import("@/components/map/OpsMap").then((m) => m.OpsMap), { ssr: false });
const MapControls = dynamic(() => import("@/components/map/MapControls").then((m) => m.MapControls), { ssr: false });

// panel width per map screen (the map dominates analysis screens)
const MAP_SCREENS: Record<string, string> = {
  situation: "w-[400px]",
  impact: "w-[440px]",
  windows: "w-[560px]",
  bottlenecks: "w-[480px]",
  plan: "w-[min(880px,62%)]",
  operations: "w-[min(720px,56%)]",
};

export default function AreaLayout({ children }: { children: ReactNode }) {
  const { areaId } = useParams<{ areaId: string }>();
  const pathname = usePathname();
  const screen = pathname.split("/")[3] || "situation";
  const panel = MAP_SCREENS[screen];
  const setCursor = useUi((s) => s.setCursor);
  const setPlaying = useUi((s) => s.setPlaying);

  useEffect(() => {
    setCursor(null);
    setPlaying(false);
  }, [areaId, setCursor, setPlaying]);

  return (
    <AreaProvider areaId={areaId}>
      {panel ? (
        <div className="flex h-full flex-col">
          <div className="flex min-h-0 flex-1">
            <div className="relative min-w-0 flex-1">
              <OpsMap key={areaId} />
              <MapControls />
            </div>
            <aside className={`${panel} min-w-[320px] max-w-full shrink-0 overflow-y-auto border-l border-line bg-bg`}>{children}</aside>
          </div>
          <Timeline />
        </div>
      ) : (
        <div className="h-full overflow-y-auto">{children}</div>
      )}
    </AreaProvider>
  );
}
