import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, withRetry } from "../api/client";
import { mockTokens } from "../api/mock";
import { useMock } from "../api/mode";
import type { TokensResponse } from "../api/types";
import { useStream } from "./useStream";

const REFETCH_DEBOUNCE_MS = 5_000;

export function useTokens(): {
  data: TokensResponse | null;
  loading: boolean;
  error: string | null;
} {
  const mock = useMock();
  const [data, setData] = useState<TokensResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // No `kind` filter — we want both session_update and transcript_message.
  const { lastEvent } = useStream();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastFetchRef = useRef(0);

  const fetchTokens = useCallback(async (signal: { cancelled: boolean }) => {
    try {
      const res = await withRetry(() => apiGet<TokensResponse>("/api/tokens"));
      if (signal.cancelled) return;
      setData(res);
      setLoading(false);
      lastFetchRef.current = Date.now();
    } catch (e) {
      if (signal.cancelled) return;
      setError((e as Error).message);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const signal = { cancelled: false };
    setLoading(true);
    setError(null);
    if (mock) {
      setData(mockTokens());
      setLoading(false);
      return () => {
        signal.cancelled = true;
      };
    }
    fetchTokens(signal);
    return () => {
      signal.cancelled = true;
    };
  }, [mock, fetchTokens]);

  // Debounced refetch on token-affecting stream events. We trail-edge: schedule
  // a fetch ~5s after the latest event, so a flurry collapses into one call.
  useEffect(() => {
    if (mock) return;
    if (!lastEvent) return;
    if (lastEvent.kind !== "session_update" && lastEvent.kind !== "transcript_message") return;

    if (debounceRef.current) clearTimeout(debounceRef.current);
    const elapsed = Date.now() - lastFetchRef.current;
    const delay = Math.max(REFETCH_DEBOUNCE_MS - elapsed, 0);
    const signal = { cancelled: false };
    debounceRef.current = setTimeout(() => {
      fetchTokens(signal);
    }, delay);
    return () => {
      signal.cancelled = true;
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
    };
  }, [mock, lastEvent, fetchTokens]);

  return { data, loading, error };
}
