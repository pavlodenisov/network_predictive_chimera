"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";

export default function ModelsPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["models"], queryFn: () => api<any>("/models") });
  const [open, setOpen] = useState<string | null>("founder");
  const models = data?.items || [];
  return (
    <>
      <div className="pagehead">
        <h2>Models</h2>
        <span className="sub">versioned config · weights live in YAML · no silent production changes</span>
      </div>
      {error ? <div className="err">{String((error as Error).message)}</div> : null}
      {isLoading ? <div className="dim">loading…</div> : null}

      {models.map((m: any) => (
        <div className="panel" key={m.full_version}>
          <h3 onClick={() => setOpen(open === m.name ? null : m.name)} style={{ cursor: "pointer" }}>
            {m.full_version} · {m.status} · config {m.config_hash} {open === m.name ? "▲" : "▼"}
          </h3>
          <div className="kv" style={{ marginBottom: 8 }}>
            <span className="k">dimension weights</span>
            <span className="v">
              {Object.entries<number>(m.dimension_weights)
                .map(([k, v]) => `${k} ${v}`)
                .join(" · ")}{" "}
              (Σ {Object.values<number>(m.dimension_weights).reduce((a, b) => a + b, 0).toFixed(2)})
            </span>
            <span className="k">confidence weights</span>
            <span className="v">
              {Object.entries<number>(m.confidence_weights)
                .map(([k, v]) => `${k} ${v}`)
                .join(" · ")}
            </span>
          </div>
          {open === m.name ? (
            <div className="tree">
              {Object.entries<any>(m.dimensions).map(([dn, d]) => (
                <details key={dn} open>
                  <summary>
                    <span className="lbl">
                      {dn} · {d.kind} · weight {d.weight}
                    </span>
                  </summary>
                  {Object.entries<any>(d.features || {}).map(([fn, f]) => (
                    <div className="row" key={fn}>
                      <span className="lbl">{fn}</span>
                      <span className="mono">
                        w {f.weight} · {f.normalization}
                        {Object.keys(f.params || {}).length ? ` ${JSON.stringify(f.params)}` : ""} · missing:{" "}
                        {f.missing_behavior}
                      </span>
                      <span className="faint" style={{ flex: 2 }}>
                        {f.rationale}
                      </span>
                    </div>
                  ))}
                  {Object.entries<any>(d.signals || {}).map(([sn, s]) => (
                    <div className="row" key={sn}>
                      <span className="lbl">{sn}</span>
                      <span className="mono">{JSON.stringify(s)}</span>
                    </div>
                  ))}
                  {d.access_model ? (
                    <div className="row">
                      <span className="lbl">access model</span>
                      <span className="mono">{d.access_model}</span>
                    </div>
                  ) : null}
                </details>
              ))}
            </div>
          ) : null}
        </div>
      ))}
    </>
  );
}
