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
 * Compact ~38px row. Mobile-first: avoids horizontal overflow at 380px by
 * truncating the label and stacking subtree-rollup on a second line.
 *
 * Navigation is handled by the Tree's onActivate prop in the parent — this
 * renderer is a pure visual component with no extra props.
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
      style={style}
      className="flex items-center gap-1 px-1 py-1 hover:bg-zinc-900/60 cursor-pointer text-xs"
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
        className={`w-4 text-zinc-500 ${hasChildren ? "" : "opacity-0"}`}
        tabIndex={-1}
        onClick={(e) => {
          e.stopPropagation();
          node.toggle();
        }}
      >
        {hasChildren ? (node.isOpen ? "▾" : "▸") : "·"}
      </button>
      <StatePill state={session.state} />
      <span className="flex-1 min-w-0 truncate text-zinc-200">
        {data.name}
        {session.last_tool_name ? (
          <span className="text-zinc-500 ml-1">· {session.last_tool_name}</span>
        ) : null}
      </span>
      <span className="text-zinc-500 hidden sm:inline">
        <ElapsedClock since={session.started_at} live={live} />
      </span>
      <span className="text-right tabular-nums font-mono ml-1 leading-tight">
        <span className="text-zinc-300">self {formatTokens(ownTotal)}</span>
        {hasChildren ? (
          <span className="block text-[10px] text-zinc-500">subtree {formatTokens(subTotal)}</span>
        ) : null}
      </span>
    </div>
  );
}
