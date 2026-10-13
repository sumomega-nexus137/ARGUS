"use client";

import { create } from "zustand";

export type Theme = "light" | "dark";

const KEY = "argus.theme";

/** Runs in <head> before first paint so a saved dark theme never flashes light. */
export const THEME_SCRIPT = `try{if(localStorage.getItem("${KEY}")==="dark")document.documentElement.classList.add("dark")}catch(e){}`;

interface ThemeState {
  theme: Theme;
  setTheme: (t: Theme) => void;
  /** read the class the head script applied (call once after hydration) */
  sync: () => void;
}

export const useTheme = create<ThemeState>((set) => ({
  theme: "light",
  setTheme: (theme) => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      /* private mode: the choice simply is not remembered */
    }
    set({ theme });
  },
  sync: () => set({ theme: document.documentElement.classList.contains("dark") ? "dark" : "light" }),
}));
