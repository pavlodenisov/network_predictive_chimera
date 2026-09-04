"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api, qs } from "@/lib/api";

export default function NetworkPage() {
  const { data } = useQuery({
    queryKey: ["rankings", "connectors", "net"],
    queryFn: () => api<any>(`/rankings/connectors${qs({ page_size: 100 })}`),
  });
  const founders = useQuery({
    queryKey: ["rankings", "founders", "net"],
    queryFn: () => api<any>(`/rankings/founders${qs({ warm_path: 1, page_size: 50 })}`),
  });
  return (
    <>
      <div className="pagehead">
        <h2>Network</h2>
        <span className="sub">strongest warm paths + connectors — no decorative graph (spec §28)</span>
      </div>

      <div className="panel">
        <h3>People with a warm path to Chimera</h3>
        <div className="scroll-x">
          <table className="grid">
            <thead>
              <tr>
                <th className="l">person</th>
                <th className="num">priority</th>
                <th className="num">access</th>
                <th className="l">action</th>
              </tr>
            </thead>
            <tbody>
              {(founders.data?.items || []).map((r: any) => (
                <tr key={r.id}>
                  <td className="l">
                    <Link href={`/person/${r.id}`}>{r.name}</Link>
                  </td>
                  <td className="num">{r.priority?.toFixed(1)}</td>
                  <td className="num">{(r.scores?.founder?.access ?? "—") + ""}</td>
                  <td className="l">{r.action || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h3>Connectors — network-position value</h3>
        <div className="scroll-x">
          <table className="grid">
            <thead>
              <tr>
                <th className="num">#</th>
                <th className="l">person</th>
                <th className="num">priority</th>
                <th className="num">confidence</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((r: any) => (
                <tr key={r.id}>
                  <td className="num">{r.rank ?? "—"}</td>
                  <td className="l">
                    <Link href={`/person/${r.id}`}>{r.name}</Link>
                  </td>
                  <td className="num">{r.priority?.toFixed(1)}</td>
                  <td className="num">{r.confidence?.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
