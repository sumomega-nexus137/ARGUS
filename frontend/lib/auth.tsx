"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, getToken, post, setToken } from "./api";
import type { User } from "./types";

interface AuthCtx {
  user: User | null;
  ready: boolean;
  login: (username: string, password: string) => Promise<User>;
  logout: () => void;
  can: (permission: string) => boolean;
}

const Ctx = createContext<AuthCtx>({
  user: null,
  ready: false,
  login: async () => {
    throw new Error("no auth provider");
  },
  logout: () => {},
  can: () => false,
});

export function useAuth(): AuthCtx {
  return useContext(Ctx);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const qc = useQueryClient();

  useEffect(() => {
    let alive = true;
    if (!getToken()) {
      setReady(true);
      return;
    }
    api<User>("/api/auth/me")
      .then((u) => alive && setUser(u))
      .catch(() => alive && setUser(null))
      .finally(() => alive && setReady(true));
    const onUnauth = () => setUser(null);
    window.addEventListener("argus:unauthorized", onUnauth);
    return () => {
      alive = false;
      window.removeEventListener("argus:unauthorized", onUnauth);
    };
  }, []);

  const login = useCallback(
    async (username: string, password: string) => {
      const res = await post<{ token: string; user: User }>("/api/auth/login", { username, password });
      setToken(res.token);
      qc.clear();
      setUser(res.user);
      return res.user;
    },
    [qc],
  );

  const logout = useCallback(() => {
    setToken(null);
    qc.clear();
    setUser(null);
  }, [qc]);

  const can = useCallback((p: string) => !!user?.permissions.includes(p), [user]);
  const value = useMemo(() => ({ user, ready, login, logout, can }), [user, ready, login, logout, can]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
