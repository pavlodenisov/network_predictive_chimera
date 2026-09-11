"use client";
import { Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { api, qs } from "@/lib/api";
import { classLabel } from "@/lib/format";
import PersonCard from "@/components/PersonCard";

const TABS = ["", "FOUNDER", "POTENTIAL_FOUNDER", "LP", "POTENTIAL_LP", "TALENT", "CONNECTOR"];

export default function PeoplePage() {
  return (
    <Suspense fallback={<div className="dim">Loading…</div>}>
      <People />
    </Suspense>
  );
}

function People() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const cls = sp.get("class") || "";
  const [q, setQ] = useState(sp.get("q") || "");

  function setClass(next: string) {
    const params = new URLSearchParams(sp.toString());
    if (next) params.set("class", next);
    else params.delete("class");
    router.push(`${pathname}?${params.toString()}`);
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ["people", q, cls],
    queryFn: () =>
      api<any>(`/people${qs({ q, person_class: cls, page_size: 100, sort: "name" })}`),
  });

  const rows = data?.items || [];

  return (
    <>
      <div className="pagehead">
        <h1>{cls ? classLabel(cls) : "Everyone we track"}</h1>
        <span className="sub">{data ? `${data.total} people` : "Search by name, or filter by who they are."}</span>
      </div>

      <div className="toolbar">
        {TABS.map((t) => (
          <span key={t || "all"} className={`tab ${cls === t ? "on" : ""}`} onClick={() => setClass(t)}>
            {t ? classLabel(t) : "Everyone"}
          </span>
        ))}
        <input
          placeholder="Search by name…"
          defaultValue={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ marginLeft: "auto", minWidth: 220 }}
        />
      </div>

      {error ? <div className="dim">Couldn&rsquo;t load people: {(error as Error).message}</div> : null}
      {isLoading ? (
        <div className="dim">Loading…</div>
      ) : rows.length ? (
        <div className="card-list">
          {rows.map((r: any) => (
            <PersonCard key={r.id} row={r} />
          ))}
        </div>
      ) : (
        <div className="card empty">No one matches yet.</div>
      )}
    </>
  );
}
