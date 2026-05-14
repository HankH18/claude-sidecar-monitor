import { useCallback, useMemo, useRef } from "react";
import { Tree, type TreeApi } from "react-arborist";
import { Link, useNavigate } from "react-router";
import { useTree } from "../hooks/useTree";
import { TreeSkeleton } from "./Skeleton";
import TreeRow, { TREE_ROW_HEIGHT, toRowData, type TreeRowData } from "./TreeNode";

const TREE_STATE_PREFIX = "csm.tree.openIds.";

function loadOpenIds(worktreeRoot: string): Record<string, boolean> | undefined {
  if (typeof localStorage === "undefined") return undefined;
  try {
    const raw = localStorage.getItem(`${TREE_STATE_PREFIX}${worktreeRoot}`);
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object") return parsed as Record<string, boolean>;
  } catch {
    /* corrupt entry — overwrite on next save */
  }
  return undefined;
}

function saveOpenIds(worktreeRoot: string, ids: Record<string, boolean>): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(`${TREE_STATE_PREFIX}${worktreeRoot}`, JSON.stringify(ids));
  } catch {
    /* quota / disabled — best effort */
  }
}

function countNodes(rows: TreeRowData[]): number {
  let n = 0;
  const walk = (rs: TreeRowData[]) => {
    for (const r of rs) {
      n++;
      if (r.children?.length) walk(r.children);
    }
  };
  walk(rows);
  return Math.max(n, 1);
}

interface ProjectTreeSectionProps {
  worktreeRoot: string;
  projectLabel: string;
}

/**
 * Overview-page tree for one project. Shares localStorage open-state
 * with ProjectDetail (same key prefix) so collapse decisions follow the
 * user across both views. Bounded height so a 50-row tree doesn't push
 * the rest of Overview off-screen — the user can scroll within it or
 * click into ProjectDetail for the full view.
 */
export default function ProjectTreeSection({
  worktreeRoot,
  projectLabel,
}: ProjectTreeSectionProps) {
  const navigate = useNavigate();
  const { tree, loading } = useTree(worktreeRoot);
  const treeRef = useRef<TreeApi<TreeRowData> | null>(null);

  const initialOpenState = useMemo(() => loadOpenIds(worktreeRoot), [worktreeRoot]);

  const persistOpenState = useCallback(() => {
    if (!treeRef.current) return;
    const map = treeRef.current.openState;
    const ids: Record<string, boolean> = {};
    for (const [id, open] of Object.entries(map)) ids[id] = !!open;
    saveOpenIds(worktreeRoot, ids);
  }, [worktreeRoot]);

  const rows = useMemo<TreeRowData[]>(() => {
    if (!tree) return [];
    // useTree synthesizes a `__project__:<root>` parent when a worktree
    // has multiple top-level sessions; collapse past it so the tree shows
    // sessions at the top level.
    if (tree.session.session_id.startsWith("__project__")) {
      return tree.children.map(toRowData);
    }
    return [toRowData(tree)];
  }, [tree]);

  const totalRows = useMemo(() => countNodes(rows), [rows]);
  // Cap per-project tree height so 5 projects with 10 rows each don't
  // each demand 600px. User scrolls within the section, or clicks "View
  // full" for the dedicated page.
  const treeHeight = Math.min(360, TREE_ROW_HEIGHT * totalRows + 8);

  return (
    <section aria-label={`${projectLabel} tree`} className="space-y-2">
      <Link
        to={`/projects/${encodeURIComponent(worktreeRoot)}`}
        className="flex items-center justify-between min-h-11 -mx-1 px-1 rounded-md text-sm text-zinc-200 hover:text-zinc-100 hover:bg-zinc-900/40"
      >
        <span className="font-medium truncate">{projectLabel}</span>
        <span className="text-zinc-500 text-xs shrink-0 ml-2">
          {loading ? "loading…" : `${totalRows} node${totalRows === 1 ? "" : "s"} →`}
        </span>
      </Link>
      <div className="rounded-md border border-zinc-800 overflow-hidden">
        {loading ? (
          <div className="p-2">
            <TreeSkeleton rows={2} />
          </div>
        ) : rows.length === 0 ? (
          <p className="text-xs text-zinc-500 px-3 py-3">No live sessions.</p>
        ) : (
          <Tree<TreeRowData>
            data={rows}
            ref={treeRef}
            openByDefault
            initialOpenState={initialOpenState}
            rowHeight={TREE_ROW_HEIGHT}
            indent={16}
            width="100%"
            height={treeHeight}
            disableDrag
            disableDrop
            disableEdit
            onToggle={persistOpenState}
            onActivate={(node) => {
              const id = node.data.id;
              if (id.startsWith("__project__") || id.startsWith("__empty__")) return;
              if (node.data.node.is_virtual) {
                navigate(`/subagents/${encodeURIComponent(id)}`);
                return;
              }
              navigate(`/sessions/${id}`);
            }}
          >
            {TreeRow}
          </Tree>
        )}
      </div>
    </section>
  );
}
