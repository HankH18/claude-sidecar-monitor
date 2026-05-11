import { useState } from "react";
import { usePermissionRequests } from "../hooks/usePermissionRequests";
import PermissionSheet from "./PermissionSheet";

/**
 * V2.D4 — banner shown at the top of the app when one or more permission
 * requests are pending. Clicking it opens the PermissionSheet for the
 * oldest pending request (FIFO so the user can chew through a backlog
 * without re-tapping the banner each time).
 *
 * Renders nothing when there are no pending requests, so the banner has
 * zero visual weight in the steady state.
 */
export default function PendingApprovalsBanner() {
  const { requests, refresh } = usePermissionRequests();
  const [open, setOpen] = useState(false);

  if (requests.length === 0) return null;

  // requested_at DESC from backend → oldest is last in the array.
  const oldest = requests[requests.length - 1];

  return (
    <>
      <div
        role="alert"
        aria-live="polite"
        className="mx-3 my-2 rounded-md border border-amber-500/40 bg-amber-500/10 text-amber-100 text-xs flex items-center justify-between gap-2"
        data-testid="pending-approvals-banner"
      >
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex-1 inline-flex items-center gap-2 min-h-11 px-3 text-left hover:bg-amber-500/15 rounded-md"
        >
          <span aria-hidden="true">🛂</span>
          <span className="truncate">
            {requests.length} permission request{requests.length === 1 ? "" : "s"} waiting —{" "}
            <span className="text-amber-300 underline">review</span>
          </span>
        </button>
      </div>
      {open ? (
        <PermissionSheet
          request={oldest}
          onClose={() => setOpen(false)}
          onDecided={() => {
            refresh();
            setOpen(false);
          }}
        />
      ) : null}
    </>
  );
}
