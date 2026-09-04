import React from "react";

export function num(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(digits);
}

/** Renders `unknown` as the literal word — distinct from 0 and from — (missing). */
export function Val({ v, digits = 1 }: { v: number | null | undefined | "unknown"; digits?: number }) {
  if (v === "unknown") return <span className="unknown">unknown</span>;
  if (v === null || v === undefined) return <span className="faint">—</span>;
  return <span className="mono">{v.toFixed(digits)}</span>;
}

export function Delta({ v, digits = 1 }: { v: number | null | undefined; digits?: number }) {
  if (v === null || v === undefined) return <span className="faint">—</span>;
  const s = v >= 0 ? "+" : "";
  return (
    <span className={v > 0.05 ? "pos mono" : v < -0.05 ? "neg mono" : "dim mono"}>
      {s}
      {v.toFixed(digits)}
    </span>
  );
}

export function Bar({ v, max = 100 }: { v: number | null | undefined; max?: number }) {
  if (v === null || v === undefined) return <span className="faint">—</span>;
  const pct = Math.max(0, Math.min(100, (v / max) * 100));
  return (
    <span className="bar" title={String(v)}>
      <span style={{ width: `${pct}%` }} />
    </span>
  );
}

export function Pill({ children, act }: { children: React.ReactNode; act?: boolean }) {
  return <span className={act ? "pill act" : "pill"}>{children}</span>;
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const days = Math.round((Date.now() - d.getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "1d ago";
  if (days < 60) return `${days}d ago`;
  return `${Math.round(days / 30)}mo ago`;
}

export function MiniHistogram({ values, width = 5 }: { values: number[]; width?: number }) {
  if (!values.length) return <span className="faint">no data</span>;
  const max = Math.max(...values, 1);
  return (
    <div className="hist">
      {values.map((v, i) => (
        <i key={i} style={{ height: `${(v / max) * 100}%`, width }} />
      ))}
    </div>
  );
}
