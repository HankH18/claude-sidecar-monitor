import { Link, NavLink, Route, Routes } from "react-router";
import ConnectionBanner from "./components/ConnectionBanner";
import ConnectionStatus from "./components/ConnectionStatus";
import PendingApprovalsBanner from "./components/PendingApprovalsBanner";
import { ToastProvider } from "./components/Toast";
import Overview from "./pages/Overview";
import PermissionDeepLink from "./pages/PermissionDeepLink";
import ProjectDetail from "./pages/ProjectDetail";
import SessionDetail from "./pages/SessionDetail";
import Settings from "./pages/Settings";
import SubagentDetail from "./pages/SubagentDetail";
import Tokens from "./pages/Tokens";

/**
 * Bottom-navigation tab. py-3.5 + min-h-12 keeps the tap target ≥44pt per
 * Apple HIG; the focus-visible ring is provided globally in `theme.css`.
 *
 * Active tab gets a teal underline + ink text; inactive sits in muted ink.
 */
function NavTab({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        `flex-1 inline-flex items-center justify-center min-h-12 py-3.5 text-sm font-medium transition-colors ${
          isActive
            ? "text-ink border-b-2 border-teal"
            : "text-ink-muted hover:text-ink border-b-2 border-transparent"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

/**
 * Tiny stylized "S" logomark — three stacked rectangles in the CTA orange.
 * Inline SVG keeps it asset-free and matches the wordmark color.
 */
function Logomark() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className="shrink-0">
      <rect x="2" y="2.5" width="12" height="3" rx="0.8" fill="var(--csm-orange)" />
      <rect x="4" y="6.5" width="8" height="3" rx="0.8" fill="var(--csm-orange)" opacity="0.85" />
      <rect x="2" y="10.5" width="12" height="3" rx="0.8" fill="var(--csm-orange)" opacity="0.7" />
    </svg>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <div className="min-h-dvh flex flex-col">
        <header className="sticky top-0 z-10 bg-titlebar/95 backdrop-blur border-b border-line pt-safe">
          <div className="px-4 py-3 flex items-center justify-between gap-3">
            <Link
              to="/"
              className="font-semibold text-ink inline-flex items-center gap-2 min-h-11 -my-1.5 text-base"
            >
              <Logomark />
              <span>Sidecar</span>
            </Link>
            <ConnectionStatus />
          </div>
          <nav className="flex border-t border-line" aria-label="primary">
            <NavTab to="/" label="Live" />
            <NavTab to="/tokens" label="Tokens" />
            <NavTab to="/settings" label="Settings" />
          </nav>
        </header>
        <ConnectionBanner />
        <PendingApprovalsBanner />
        <main className="flex-1 px-4 py-5 pb-safe">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/projects/:encoded" element={<ProjectDetail />} />
            <Route path="/sessions/:id" element={<SessionDetail />} />
            <Route path="/subagents/:virtualId" element={<SubagentDetail />} />
            <Route path="/permissions/:id" element={<PermissionDeepLink />} />
            <Route path="/tokens" element={<Tokens />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
      </div>
    </ToastProvider>
  );
}

function NotFound() {
  return (
    <div className="text-ink-muted text-sm py-12 text-center space-y-3">
      <p>Page not found.</p>
      <Link
        to="/"
        className="inline-flex items-center justify-center min-h-11 px-4 rounded-md bg-cta text-white font-medium shadow-[0_1px_0_rgba(0,0,0,0.15),inset_0_1px_0_rgba(255,255,255,0.25)] hover:bg-cta-hover active:translate-y-px"
      >
        Back to Live
      </Link>
    </div>
  );
}
