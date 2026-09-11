import Link from "next/link";
import ActionBadge from "./ActionBadge";
import { ago, classLabel, eventPhrase, normalizeRow, num } from "@/lib/format";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] || "") + (parts[parts.length - 1]?.[0] || "")).toUpperCase();
}

export default function PersonCard({ row }: { row: any }) {
  const p = normalizeRow(row);
  const cls = p.classes[0];
  const reason = p.latestEvent
    ? `${eventPhrase(p.latestEvent.type)} · ${ago(p.latestEvent.occurred_at || p.latestEvent.detected_at)}`
    : "No recent activity detected";

  return (
    <Link href={`/person/${p.id}`} className="card person-card">
      <div className="avatar">{initials(p.name || "?")}</div>
      <div className="body">
        <div className="name">{p.name}</div>
        <div className="role">{cls ? classLabel(cls) : "Unclassified"}</div>
        <div className="reason">{reason}</div>
      </div>
      <div className="side">
        <ActionBadge action={p.action} />
        <div className="priority">{p.priority === null ? "—" : num(p.priority, 0)}</div>
      </div>
    </Link>
  );
}
