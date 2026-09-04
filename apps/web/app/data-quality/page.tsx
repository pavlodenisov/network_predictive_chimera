"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function DataQualityPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["dq"], queryFn: () => api<any>("/data-quality") });
  if (error) return <div className="err">{String((error as Error).message)}</div>;
  if (isLoading || !data) return <div className="dim">loading…</div>;
  const rows: [string, any][] = [
    ["Source failures / partial", data.source_failures],
    ["Extraction failures", data.extraction_failures],
    ["Unresolved / needs-review entities", data.unresolved_or_review_entities],
    ["Ambiguous entity resolutions", data.ambiguous_resolutions],
    ["Conflicting current employment", data.conflicting_employment],
    ["Suspicious duplicate names", data.suspicious_duplicate_names],
  ];
  return (
    <>
      <div className="pagehead">
        <h2>Data Quality</h2>
        <span className="sub">this screen is important — nothing is silently skipped</span>
      </div>
      {rows.map(([label, v]) => (
        <div className="panel" key={label}>
          <h3>
            {label} · {Array.isArray(v) ? v.length : v}
          </h3>
          {Array.isArray(v) && v.length ? (
            <pre className="mono faint" style={{ whiteSpace: "pre-wrap", fontSize: 11.5, margin: 0 }}>
              {JSON.stringify(v, null, 1)}
            </pre>
          ) : Array.isArray(v) ? (
            <div className="faint">none</div>
          ) : null}
        </div>
      ))}
    </>
  );
}
