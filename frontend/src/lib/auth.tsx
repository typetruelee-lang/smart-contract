import { type ReactNode, createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Loading } from "../components/ui";
import { api, onAuthError } from "./api";
import { IS_TOSS, tokenStore } from "./runtime";
import { getBridge } from "./tossBridge";

export interface User {
  id: string;
  name: string;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (testUser?: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthState>({} as AuthState);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const userRef = useRef<User | null>(null);
  userRef.current = user;
  const nav = useNavigate();
  const loc = useLocation();

  const refresh = useCallback(async () => {
    if (IS_TOSS && !tokenStore.get()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const r = await api.get<{ user: User }>("/api/auth/me");
      setUser(r.user);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // 세션 만료 → 로그인 화면으로 (돌아올 주소 기억)
  useEffect(() => {
    const off = onAuthError((e) => {
      const wasLoggedIn = userRef.current !== null;
      setUser(null);
      if (!wasLoggedIn && e.code !== "SESSION_EXPIRED") return; // 비로그인 상태의 401 은 각 화면이 처리
      if (window.location.pathname.startsWith("/login") || window.location.pathname.startsWith("/verify")) return;
        const next = encodeURIComponent(window.location.pathname + window.location.search);
        nav(`/login?next=${next}${e.code === "SESSION_EXPIRED" ? "&expired=1" : ""}`, { replace: true });
    });
    return () => {
      off();
    };
  }, [nav]);

  const login = useCallback(async (testUser?: string) => {
    const bridge = getBridge();
    const r = await bridge.appLogin(testUser);
    const res = await api.post<{ user: User; access_token?: string }>("/api/auth/toss/login", { authorization_code: r.authorizationCode, referrer: r.referrer });
    if (IS_TOSS && res.access_token) tokenStore.set(res.access_token);
    setUser(res.user);
  }, []);

  const logout = useCallback(async () => {
    await api.post("/api/auth/logout");
    tokenStore.set(null);
    setUser(null);
  }, []);

  void loc;
  return <Ctx.Provider value={{ user, loading, login, logout, refresh }}>{children}</Ctx.Provider>;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  return <>{children}</>;
}
