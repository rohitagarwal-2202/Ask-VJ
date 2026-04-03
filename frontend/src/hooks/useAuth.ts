import { useState, useEffect, useCallback } from "react";
import type { UserInfo, TokenResponse } from "../types/api";
import { apiFetch, setToken, clearToken, getToken } from "../lib/api";

export function useAuth() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const isAuthenticated = user !== null;

  // Validate existing token on mount
  useEffect(() => {
    async function checkAuth() {
      const token = getToken();
      if (!token) {
        setIsLoading(false);
        return;
      }

      try {
        const res = await apiFetch("/auth/me");
        if (res.ok) {
          const data: UserInfo = await res.json();
          setUser(data);
        } else {
          clearToken();
        }
      } catch {
        clearToken();
      } finally {
        setIsLoading(false);
      }
    }

    checkAuth();
  }, []);

  // Listen for forced logout from 401 responses
  useEffect(() => {
    function handleLogout() {
      setUser(null);
    }

    window.addEventListener("auth:logout", handleLogout);
    return () => window.removeEventListener("auth:logout", handleLogout);
  }, []);

  const requestOtp = useCallback(async (phone: string): Promise<void> => {
    const res = await apiFetch("/auth/request-otp", {
      method: "POST",
      body: JSON.stringify({ phone }),
    });

    if (!res.ok) {
      const body = await res.json().catch(() => null);
      const detail = body?.detail;
      const msg = typeof detail === "string" ? detail : "Failed to send OTP";
      throw new Error(msg);
    }
  }, []);

  const verifyOtp = useCallback(
    async (phone: string, otp: string): Promise<void> => {
      const res = await apiFetch("/auth/verify-otp", {
        method: "POST",
        body: JSON.stringify({ phone, otp_code: otp }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const detail = body?.detail;
        const msg = typeof detail === "string" ? detail : "Invalid OTP";
        throw new Error(msg);
      }

      const data: TokenResponse = await res.json();
      setToken(data.access_token);
      setUser(data.user);
    },
    [],
  );

  const logout = useCallback(async (): Promise<void> => {
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      // Logout even if the request fails
    } finally {
      clearToken();
      setUser(null);
    }
  }, []);

  return { user, isAuthenticated, isLoading, requestOtp, verifyOtp, logout };
}
