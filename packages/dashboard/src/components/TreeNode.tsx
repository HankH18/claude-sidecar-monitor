import type { NodeRendererProps } from "react-arborist";
import type { TreeNode as ApiTreeNode } from "../api/types";
import ElapsedClock from "./ElapsedClock";
import StatePill from "./StatePill";
import { formatTokens } from "./TokenBadge";

export interface TreeRowData {
  id: string;
  /** Display name (project label / agent_type fallback). */
  name: string;
  node: ApiTreeNode;
  children?: TreeRowData[];
}

/** Build react-arborist row data from an API TreeNode recursively. */
export function toRowData(n: ApiTreeNode): TreeRowData {
  return {
    id: n.session.session_id,
    name: n.session.agent_type ?? n.session.session_id,
    node: n,
    children: n.children.length ? n.children.map(toRowData) : undefined,
  };
}

/**
 * Tree row renderer. Targeted at 380px viewport:
 *
 * - Whole row is the tap target (≥44px tall via the rowHeight prop on Tree).
 * - Caret is a separate ≥32px-wide button so expand/collapse doesn't fight
 *   navigation.
 * - Tokens compress to a single self/subtree line; cache numbers stay on the
 *   detail page so they don't crowd the tree label.
 */
export default function TreeRow({ node, style }: NodeRendererProps<TreeRowData>) {
  const data = node.data;
  const session = data.node.session;
  const hasChildren = !!data.children?.length;
  const liveStates = new Set(["running", "tool", "waiting_user", "hung"]);
  const live = liveStates.has(session.state);

  const ownTotal = session.input_tokens + session.output_tokens;
  const subTotal = data.node.subtree_tokens.input + data.node.subtree_tokens.output;

  return (
    <div
      role="treeitem"
      aria-selected={node.isSelected}
      aria-expanded={hasChildren ? node.isOpen : undefined}
      style={style}
      className="flex items-center gap-1.5 pr-2 hover:bg-zinc-900/60 cursor-pointer text-xs rounded-sm"
      onClick={() => {
        if (hasChildren) node.toggle();
        node.select();
        node.activate();
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          if (hasChildren) node.toggle();
          node.activate();
        }
      }}
    >
      <button
        type="button"
        aria-label={node.isOpen ? "collapse" : "expand"}
        className={`shrink-0 inline-flex items-center justify-center w-8 h-full text-zinc-500 hover:text-zinc-200 ${
          hasChildren ? "" : "opacity-0 pointer-events-none"
        }`}
        tabIndex={hasChildren ? 0 : -1}
        onClick={(e) => {
          e.stopPropagation();
          node.toggle();
        }}
      >
        {hasChildren ? (node.isOpen ? "▾" : "▸") : "·"}
      </button>
      <StatePill state={session.state} className="shrink-0" />
      <span className="flex-1 min-w-0 truncate text-zinc-200">
        {data.name}
        {session.last_tool_name ? (
          <span className="text-zinc-500 ml-1">· {session.last_tool_name}</span>
        ) : null}
      </span>
      <span className="text-zinc-500 hidden sm:inline shrink-0">
        <ElapsedClock since={session.started_at} live={live} />
      </span>
      <span className="text-right tabular-nums font-mono ml-1 leading-tight shrink-0">
        <span className="text-zinc-300">self {formatTokens(ownTotal)}</span>
        {hasChildren ? (
          <span className="block text-[10px] text-zinc-500">subtree {formatTokens(subTotal)}</span>
        ) : null}
      </span>
    </div>
  );
}
