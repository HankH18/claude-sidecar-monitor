import { useParams } from "react-router";

export default function ProjectDetail() {
  const { encoded } = useParams();
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold text-zinc-100">Project</h1>
      <p className="text-xs text-zinc-500 break-all">worktree: {encoded}</p>
      <p className="text-xs text-zinc-600">Tree view fills in at T17.</p>
    </div>
  );
}
