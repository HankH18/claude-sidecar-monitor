import { useParams } from "react-router";

export default function SessionDetail() {
  const { id } = useParams();
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold text-zinc-100">Session</h1>
      <p className="text-xs text-zinc-500 break-all">id: {id}</p>
      <p className="text-xs text-zinc-600">Transcript reader fills in at T18.</p>
    </div>
  );
}
