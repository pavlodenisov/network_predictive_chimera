import { actionLabel, actionTone } from "@/lib/format";

export default function ActionBadge({ action }: { action?: string | null }) {
  return <span className={`badge ${actionTone(action)}`}>{actionLabel(action)}</span>;
}
