"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Bar, Delta, Pill, Val, ago } from "@/lib/fmt";

type Row = any;

const COLS: { key: string; label: string; num?: boolean; get: (r: Row) => any; render?: (r: Row) => React.ReactNode }[] = [
  { key: "rank", label: "#", num: true, get: (r) => r.rank ?? 9e9, render: (r) => <span className="mono">{r.rank ?? "—"}</span> },
  { key: "name", label: "Person", get: (r) => r.name, render: (r) => <Link href={`/person/${r.id}`}>{r.name}</Link> },
  { key: "class", label: "Class", get: (r) => (r.classes || [])[0] || "", render: (r) => (r.classes || []).slice(0, 2).map((c: string) => <Pill key={c}>{c.replace("POTENTIAL_", "P·")}</Pill>) },
  { key: "priority", label: "Priority", num: true, get: (r) => r.priority ?? -1, render: (r) => <Val v={r.priority} /> },
  { key: "delta", label: "Δ 7d", num: true, get: (r) => r.delta ?? -9e9, render: (r) => <Delta v={r.delta} /> },
  { key: "quality", label: "Qual", num: true, get: (r) => sc(r, "quality"), render: (r) => <Val v={sc(r, "quality")} /> },
  { key: "fit", label: "Fit", num: true, get: (r) => sc(r, "fit"), render: (r) => <Val v={sc(r, "fit")} /> },
  { key: "timing", label: "Timing", num: true, get: (r) => sc(r, "timing"), render: (r) => <Val v={sc(r, "timing")} /> },
  { key: "access", label: "Access", num: true, get: (r) => sc(r, "access"), render: (r) => <Val v={sc(r, "access") ?? "unknown"} /> },
  { key: "confidence", label: "Conf", num: true, get: (r) => r.confidence ?? -1, render: (r) => <Val v={r.confidence} digits={2} /> },
  { key: "conf_bar", label: "", get: (r) => r.confidence ?? 0, render: (r) => <Bar v={(r.confidence ?? 0) * 100} /> },
  { key: "event", label: "Latest event", get: (r) => r.latest_event?.type || "", render: (r) => r.latest_event ? <span className="dim">{r.latest_event.type}</span> : <span className="faint">—</span> },
  { key: "event_age", label: "Event age", get: (r) => r.latest_event?.occurred_at || "", render: (r) => <span className="faint">{ago(r.latest_event?.occurred_at || r.latest_event?.detected_at)}</span> },
  { key: "action", label: "Action", get: (r) => r.action || "", render: (r) => r.action ? <Pill act>{r.action}</Pill> : null },
];

function sc(r: Row, k: string): number | null {
  const model = r.scores?.founder || r.scores?.lp || r.scores?.talent || r.scores?.connector;
  return (model?.[k] ?? null) as number | null;
}

export default function RankTable({ rows }: { rows: Row[] }) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 }>({ key: "rank", dir: 1 });
  const sorted = useMemo(() => {
    const col = COLS.find((c) => c.key === sort.key);
    if (!col) return rows;
    return [...rows].sort((a, b) => {
      const av = col.get(a);
      const bv = col.get(b);
      if (av === bv) return 0;
      return (av > bv ? 1 : -1) * sort.dir;
    });
  }, [rows, sort]);

  return (
    <div className="scroll-x">
      <table className="grid">
        <thead>
          <tr>
            {COLS.map((c) => (
              <th
                key={c.key}
                className={c.num ? "num" : "l"}
                onClick={() => setSort((s) => ({ key: c.key, dir: s.key === c.key ? (-s.dir as 1 | -1) : 1 }))}
                title="click to sort"
              >
                {c.label}
                {sort.key === c.key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.id}>
              {COLS.map((c) => (
                <td key={c.key} className={c.num ? "num" : "l"}>
                  {c.render ? c.render(r) : String(c.get(r))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
