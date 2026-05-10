import { Link, NavLink, Route, Routes } from "react-router";
import ConnectionStatus from "./components/ConnectionStatus";
import Overview from "./pages/Overview";
import ProjectDetail from "./pages/ProjectDetail";
import SessionDetail from "./pages/SessionDetail";
import Settings from "./pages/Settings";
import Tokens from "./pages/Tokens";

/**
 * Bottom-navigation tab. py-3.5 + min-h-12 keeps the tap target ≥44pt per
 * Apple HIG; the focus-visible ring is provided globally in `theme.css`.
 */
function NavTab({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        `flex-1 inline-flex items-center justify-center min-h-12 py-3.5 text-sm font-medium transition-colors ${
          isActive
            ? "text-emerald-300 border-b-2 border-emerald-400"
            : "text-zinc-400 hover:text-zinc-200 border-b-2 border-transparent"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="min-h-dvh flex flex-col">
      <header className="sticky top-0 z-10 bg-zinc-950/95 backdrop-blur border-b border-zinc-800 pt-safe">
        <div className="px-4 py-3 flex items-center justify-between gap-3">
          <Link
            to="/"
            className="font-semibold text-zinc-100 inline-flex items-center gap-2 min-h-11 -my-1.5"
          >
            <span aria-hidden="true" className="text-emerald-400 text-base leading-none">
              ●
            </span>
            <span>Sidecar</span>
          </Link>
          <ConnectionStatus />
        </div>
        <nav className="flex border-t border-zinc-800" aria-label="primary">
          <NavTab to="/" label="Live" />
          <NavTab to="/tokens" label="Tokens" />
          <NavTab to="/settings" label="Settings" />
        </nav>
      </header>
      <main className="flex-1 px-4 py-5 pb-safe">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/projects/:encoded" element={<ProjectDetail />} />
          <Route path="/sessions/:id" element={<SessionDetail />} />
          <Route path="/tokens" element={<Tokens />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  );
}

function NotFound() {
  return (
    <div className="text-zinc-500 text-sm py-12 text-center space-y-3">
      <p>Page not found.</p>
      <Link
        to="/"
        className="inline-flex items-center justify-center min-h-11 px-4 rounded-md bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/40 hover:bg-emerald-500/25"
      >
        Back to Live
      </Link>
    </div>
  );
}
