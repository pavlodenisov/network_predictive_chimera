"use client";
import { Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { api, qs } from "@/lib/api";
import RankTable from "@/components/RankTable";

const CLASSES = ["", "FOUNDER", "POTENTIAL_FOUNDER", "LP", "POTENTIAL_LP", "TALENT", "CONNECTOR"];

export default function Page() {
  return (
    <Suspense fallback={<div className="dim">loading…</div>}>
      <Intelligence />
    </Suspense>
  );
}

function Intelligence() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const min_priority = sp.get("min_priority") || "";
  const warm_path = sp.get("warm_path") === "1";
  const min_confidence = sp.get("min_confidence") || "";
  const cls = sp.get("class") || "";

  function setParam(k: string, v: string) {
    const next = new URLSearchParams(sp.toString());
    if (v) next.set(k, v);
    else next.delete(k);
    router.replace(`${pathname}?${next.toString()}`);
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ["rankings", "founders", min_priority, warm_path, min_confidence],
    queryFn: () =>
      api<any>(`/rankings/founders${qs({ min_priority, warm_path: warm_path ? 1 : "", min_confidence, page_size: 200 })}`),
  });

  let rows: any[] = data?.items || [];
  if (cls) rows = rows.filter((r) => (r.classes || []).includes(cls));

  return (
    <>
      <div className="pagehead">
        <h2>Intelligence</h2>
        <span className="sub">
          {data ? `${data.universe.label} · ${data.universe.member_count} in universe · founder_v0.1` : ""}
        </span>
      </div>

      <div className="toolbar">
        <select value={cls} onChange={(e) => setParam("class", e.target.value)}>
          {CLASSES.map((c) => (
            <option key={c} value={c}>
              {c || "all classes"}
            </option>
          ))}
        </select>
        <input
          placeholder="min priority"
          defaultValue={min_priority}
          onBlur={(e) => setParam("min_priority", e.target.value)}
          style={{ width: 90 }}
        />
        <input
          placeholder="min confidence"
          defaultValue={min_confidence}
          onBlur={(e) => setParam("min_confidence", e.target.value)}
          style={{ width: 100 }}
        />
        <span className={warm_path ? "chip on" : "chip"} onClick={() => setParam("warm_path", warm_path ? "" : "1")}>
          warm path available
        </span>
        <span className="faint" style={{ marginLeft: "auto" }}>
          {rows.length} shown · click a column to sort · filters are in the URL
        </span>
      </div>

      {error ? <div className="err">API error: {String((error as Error).message)}</div> : null}
      {isLoading ? <div className="dim">loading…</div> : <RankTable rows={rows} />}
    </>
  );
}
