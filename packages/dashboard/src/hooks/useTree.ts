import { useEffect, useState } from "react";
import { apiGet } from "../api/client";
import { mockTree } from "../api/mock";
import { useMock } from "../api/mode";
import type { TreeNode } from "../api/types";

export function useTree(worktreeRoot: string | undefined): {
  tree: TreeNode | null;
  loading: boolean;
  error: string | null;
} {
  const mock = useMock();
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!worktreeRoot) {
      setTree(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    if (mock) {
      setTree(mockTree(worktreeRoot));
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    apiGet<TreeNode>(`/api/tree?worktree=${encodeURIComponent(worktreeRoot)}`)
      .then((res) => {
        if (cancelled) return;
        setTree(res);
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
  }, [mock, worktreeRoot]);

  return { tree, loading, error };
}
