"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { Pill } from "@/lib/fmt";

export default function DiscoveryPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["discoveries"], queryFn: () => api<any>("/discoveries") });
  const cands = data?.candidates || [];
  return (
    <>
      <div className="pagehead">
        <h2>Discovery</h2>
        <span className="sub">
          {cands.length} candidates · staged, not auto-trusted until identity resolution completes
        </span>
      </div>
      {error ? <div className="err">{String((error as Error).message)}</div> : null}
      {isLoading ? <div className="dim">loading…</div> : null}

      <div className="panel">
        <h3>New candidates</h3>
        <div className="scroll-x">
          <table className="grid">
            <thead>
              <tr>
                <th className="l">person</th>
                <th className="l">rule</th>
                <th className="l">class</th>
                <th className="num">identity conf</th>
                <th className="l">discovered</th>
                <th className="l">state</th>
              </tr>
            </thead>
            <tbody>
              {cands.map((c: any) => (
                <tr key={c.id}>
                  <td className="l">
                    {c.person_id ? <Link href={`/person/${c.person_id}`}>{c.person}</Link> : c.person}
                  </td>
                  <td className="l">{c.rule}</td>
                  <td className="l">
                    <Pill>{c.candidate_classification}</Pill>
                  </td>
                  <td className="num">{c.identity_confidence?.toFixed(2)}</td>
                  <td className="l faint">{c.first_discovered_at?.slice(0, 10)}</td>
                  <td className="l">
                    {c.promoted ? "promoted" : c.dismissed ? "dismissed" : c.false_positive ? "false positive" : "review"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h3>Discovery rules</h3>
        <div className="scroll-x">
          <table className="grid">
            <thead>
              <tr>
                <th className="l">name</th>
                <th className="l">target</th>
                <th className="l">active</th>
                <th className="num">lookback</th>
                <th className="l">keywords</th>
              </tr>
            </thead>
            <tbody>
              {(data?.rules || []).map((r: any) => (
                <tr key={r.id}>
                  <td className="l">{r.name}</td>
                  <td className="l">{r.target_class}</td>
                  <td className="l">{r.active ? "yes" : "no"}</td>
                  <td className="num">{r.lookback_days}d</td>
                  <td className="l faint">{(r.keywords || []).slice(0, 6).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
