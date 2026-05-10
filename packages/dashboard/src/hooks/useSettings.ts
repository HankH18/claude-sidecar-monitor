import { useEffect, useState } from "react";
import { apiGet, apiPatch } from "../api/client";
import { getMockSettings, patchMockSettings } from "../api/mock";
import { useMock } from "../api/mode";
import type { Settings } from "../api/types";

export function useSettings(): {
  settings: Settings | null;
  loading: boolean;
  error: string | null;
  save: (partial: Partial<Settings>) => Promise<Settings>;
} {
  const mock = useMock();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (mock) {
      setSettings(getMockSettings());
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    apiGet<Settings>("/api/settings")
      .then((res) => {
        if (cancelled) return;
        setSettings(res);
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

  async function save(partial: Partial<Settings>): Promise<Settings> {
    if (mock) {
      const next = patchMockSettings(partial);
      setSettings(next);
      return next;
    }
    const next = await apiPatch<Settings>("/api/settings", partial);
    setSettings(next);
    return next;
  }

  return { settings, loading, error, save };
}
