"use client";
import { useQueries } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { actionTone } from "@/lib/format";
import PersonCard from "@/components/PersonCard";

const MODELS: { key: string; label: string; href: string }[] = [
  { key: "founders", label: "Founders", href: "/people?class=FOUNDER" },
  { key: "lps", label: "LPs", href: "/people?class=LP" },
  { key: "talent", label: "Talent", href: "/people?class=TALENT" },
  { key: "connectors", label: "Connectors", href: "/people?class=CONNECTOR" },
];

function useAllRankings() {
  const queries = useQueries({
    queries: MODELS.map((m) => ({
      queryKey: ["rankings", m.key],
      queryFn: () => api<any>(`/rankings/${m.key}?page_size=100`),
    })),
  });
  const loading = queries.some((q) => q.isLoading);
  const error = queries.find((q) => q.error)?.error as Error | undefined;
  const byModel: Record<string, any[]> = {};
  MODELS.forEach((m, i) => {
    byModel[m.key] = queries[i].data?.items || [];
  });
  return { byModel, loading, error };
}

export default function Home() {
  const { byModel, loading, error } = useAllRankings();
  const all = MODELS.flatMap((m) => byModel[m.key] || []);

  const goRows = all.filter((r) => actionTone(r.action) === "go").sort((a, b) => b.priority - a.priority).slice(0, 6);
  const considerRows = all
    .filter((r) => actionTone(r.action) === "consider")
    .sort((a, b) => b.priority - a.priority)
    .slice(0, 6);

  return (
    <>
      <div className="pagehead">
        <h1>This week</h1>
        <span className="sub">
          Who to spend time with, why, and how to reach them — updated by the weekly batch cycle.
        </span>
      </div>

      {error ? <div className="dim">Couldn&rsquo;t load rankings: {error.message}</div> : null}

      <div className="section">
        <h2>Reach out this week</h2>
        {loading ? (
          <div className="dim">Loading…</div>
        ) : goRows.length ? (
          <div className="card-list">
            {goRows.map((r) => (
              <PersonCard key={`${r.id}`} row={r} />
            ))}
          </div>
        ) : (
          <div className="card empty">Nothing rises to the top this week — check back after the next update.</div>
        )}
      </div>

      <div className="section">
        <h2>Worth a conversation</h2>
        {loading ? (
          <div className="dim">Loading…</div>
        ) : considerRows.length ? (
          <div className="card-list">
            {considerRows.map((r) => (
              <PersonCard key={`${r.id}`} row={r} />
            ))}
          </div>
        ) : (
          <div className="card empty">Nothing in this tier right now.</div>
        )}
      </div>

      {MODELS.map((m) => {
        const rows = (byModel[m.key] || []).slice(0, 3);
        if (loading || rows.length === 0) return null;
        return (
          <div className="section" key={m.key}>
            <h2>
              {m.label} &nbsp;
              <Link href={m.href} style={{ textTransform: "none", letterSpacing: 0, fontWeight: 600 }}>
                see all →
              </Link>
            </h2>
            <div className="card-list">
              {rows.map((r) => (
                <PersonCard key={`${m.key}-${r.id}`} row={r} />
              ))}
            </div>
          </div>
        );
      })}
    </>
  );
}
