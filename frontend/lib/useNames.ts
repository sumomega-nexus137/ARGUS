"use client";

import { useMemo } from "react";

import { pickName } from "./format";
import { useLocale } from "./i18n";
import { useActions, useSites } from "./queries";

/** Localised names for approved actions and task sites (multilingual data fields with fallback). */
export function useNames(areaId: string) {
  const { locale } = useLocale();
  const actions = useActions(areaId);
  const sites = useSites(areaId);
  return useMemo(() => {
    const a = new Map((actions.data || []).map((x) => [x.id, x]));
    const s = new Map((sites.data || []).map((x) => [x.id, x]));
    return {
      action: (id: string) => (a.get(id) ? pickName(a.get(id)!.names, locale, id) : id),
      site: (id: string) => (s.get(id) ? pickName(s.get(id)!.names, locale, id) : id),
      siteObj: (id: string) => s.get(id),
      actionObj: (id: string) => a.get(id),
      actions: actions.data || [],
      sites: sites.data || [],
    };
  }, [actions.data, sites.data, locale]);
}
