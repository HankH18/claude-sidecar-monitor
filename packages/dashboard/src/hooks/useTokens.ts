import { useEffect, useState } from "react";
import { apiGet } from "../api/client";
import { mockTokens } from "../api/mock";
import { useMock } from "../api/mode";
import type { TokensResponse } from "../api/types";

export function useTokens(): {
  data: TokensResponse | null;
  loading: boolean;
  error: string | null;
} {
  const mock = useMock();
  const [data, setData] = useState<TokensResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (mock) {
      setData(mockTokens());
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    apiGet<TokensResponse>("/api/tokens")
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setLoading(false);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setError(e.message);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [mock]);

  return { data, loading, error };
}
