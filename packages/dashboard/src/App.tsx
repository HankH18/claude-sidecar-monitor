import { Link, NavLink, Route, Routes } from "react-router";
import Overview from "./pages/Overview";
import ProjectDetail from "./pages/ProjectDetail";
import SessionDetail from "./pages/SessionDetail";
import Settings from "./pages/Settings";
import Tokens from "./pages/Tokens";

function NavTab({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        `flex-1 text-center py-3 text-sm font-medium transition-colors ${
          isActive
            ? "text-emerald-400 border-b-2 border-emerald-400"
            : "text-zinc-400 hover:text-zinc-200"
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
      <header className="sticky top-0 z-10 bg-zinc-950/95 backdrop-blur border-b border-zinc-800">
        <div className="px-4 py-3 flex items-center justify-between">
          <Link to="/" className="font-semibold text-zinc-100">
            <span className="text-emerald-400">●</span> Sidecar
          </Link>
        </div>
        <nav className="flex border-t border-zinc-900" aria-label="primary">
          <NavTab to="/" label="Live" />
          <NavTab to="/tokens" label="Tokens" />
          <NavTab to="/settings" label="Settings" />
        </nav>
      </header>
      <main className="flex-1 px-4 py-4 pb-safe">
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
    <div className="text-zinc-500 text-sm py-8 text-center">
      Page not found.{" "}
      <Link to="/" className="text-emerald-400 underline">
        Back to Live
      </Link>
    </div>
  );
}
