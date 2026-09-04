"use client";
import { useQuery } from "@tanstack/react-query";
import { api, qs } from "@/lib/api";
import RankTable from "@/components/RankTable";

export default function RankingScreen({
  title,
  endpoint,
  blurb,
}: {
  title: string;
  endpoint: string;
  blurb: string;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["rankings", endpoint],
    queryFn: () => api<any>(`/rankings/${endpoint}${qs({ page_size: 200 })}`),
  });
  return (
    <>
      <div className="pagehead">
        <h2>{title}</h2>
        <span className="sub">
          {blurb}
          {data ? ` · ${data.universe.label} · ${data.universe.member_count} in universe` : ""}
        </span>
      </div>
      {error ? <div className="err">{String((error as Error).message)}</div> : null}
      {isLoading ? <div className="dim">loading…</div> : <RankTable rows={data?.items || []} />}
    </>
  );
}
