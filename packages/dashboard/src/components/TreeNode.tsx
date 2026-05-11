import type { NodeRendererProps } from "react-arborist";
import type { TreeNode as ApiTreeNode } from "../api/types";
import ActivityLine from "./ActivityLine";
import AgentKindIcon from "./AgentKindIcon";
import ElapsedClock from "./ElapsedClock";
import SessionLabel from "./SessionLabel";
import StatePill from "./StatePill";
import { formatTokens } from "./TokenBadge";

/** Per-row height; bumped from 44 → 60 in V2.B to fit ActivityLine. */
export const TREE_ROW_HEIGHT = 60;

export interface TreeRowData {
  /** react-arborist row id. For virtual rows this is the `virtual_id`
   *  (encoded `<parent_session_id>:<tool_use_id>`); for real sessions it's
   *  the session_id. */
  id: string;
  /** Display name (project label / agent_type fallback). */
  name: string;
  node: ApiTreeNode;
  children?: TreeRowData[];
}

/** Build react-arborist row data from an API TreeNode recursively. */
export function toRowData(n: ApiTreeNode): TreeRowData {
  const isVirtual = !!n.is_virtual;
  const id = isVirtual ? (n.virtual_id ?? n.session.session_id) : n.session.session_id;
  return {
    id,
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
 * - V2.C3: virtual subagent rows get a subtle dashed left border + a 🜲
 *   glyph so they read as "synthesised from a tool_use" rather than a real
 *   session row.
 */
export default function TreeRow({ node, style }: NodeRendererProps<TreeRowData>) {
  const data = node.data;
  const apiNode = data.node;
  const session = apiNode.session;
  const isVirtual = !!apiNode.is_virtual;
  const hasChildren = !!data.children?.length;
  const liveStates = new Set(["running", "tool", "waiting_user", "hung"]);
  const live = liveStates.has(session.state);

  const ownTotal = session.input_tokens + session.output_tokens;
  const subTotal = apiNode.subtree_tokens.input + apiNode.subtree_tokens.output;

  return (
    <div
      role="treeitem"
      aria-selected={node.isSelected}
      aria-expanded={hasChildren ? node.isOpen : undefined}
      data-virtual={isVirtual ? "true" : "false"}
      style={style}
      className={`flex flex-col justify-center gap-0.5 pr-2 hover:bg-zinc-900/60 cursor-pointer text-xs rounded-sm ${
        isVirtual ? "border-l border-dashed border-zinc-700/80 pl-0.5" : ""
      }`}
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
      <div className="flex items-center gap-1.5 min-w-0">
        <button
          type="button"
          aria-label={node.isOpen ? "collapse" : "expand"}
          className={`shrink-0 inline-flex items-center justify-center w-8 text-zinc-500 hover:text-zinc-200 ${
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
        {isVirtual ? (
          <span
            aria-hidden="true"
            className="shrink-0 text-zinc-500 font-mono text-[11px]"
            title="virtual subagent"
          >
            🜲
          </span>
        ) : (
          <StatePill state={session.state} className="shrink-0" />
        )}
        <AgentKindIcon
          kind={session.agent_kind ?? null}
          confidence={session.agent_kind_confidence ?? null}
          className="shrink-0 text-xs"
        />
        <SessionLabel
          session={session}
          fallback={isVirtual ? (apiNode.description ?? data.name) : data.name}
          className="flex-1 min-w-0 truncate text-zinc-200"
        />
        {!isVirtual && session.last_tool_name ? (
          <span className="text-zinc-500 shrink-0">· {session.last_tool_name}</span>
        ) : null}
        {!isVirtual ? (
          <span className="text-zinc-500 hidden sm:inline shrink-0">
            <ElapsedClock since={session.started_at} live={live} />
          </span>
        ) : null}
        {!isVirtual ? (
          <span className="text-right tabular-nums font-mono ml-1 leading-tight shrink-0">
            <span className="text-zinc-300">self {formatTokens(ownTotal)}</span>
            {hasChildren ? (
              <span className="block text-[10px] text-zinc-500">
                subtree {formatTokens(subTotal)}
              </span>
            ) : null}
          </span>
        ) : null}
      </div>
      {/* V2.B — activity digest beneath the label. Padded to align past the
          caret + status pill column on the first line. */}
      {!isVirtual ? (
        <ActivityLine
          summary={session.activity_summary ?? null}
          updatedAt={session.activity_updated_at ?? null}
          className="pl-9"
        />
      ) : apiNode.description ? (
        <p className="pl-9 text-[11px] text-zinc-500 truncate">{apiNode.description}</p>
      ) : null}
    </div>
  );
}
