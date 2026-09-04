"use client";
import { Delta, Val } from "@/lib/fmt";

/** Renders ScoreSnapshot.contribution_breakdown as the §70 explanation chain:
 *  priority -> dimension (score x weight) -> feature (raw -> normalized -> contribution)
 *  -> normalization rule -> source fact ids. */
export function ScoreDecomposition({ breakdown, delta }: { breakdown: any; delta?: any }) {
  if (!breakdown?.dimensions) return <div className="faint">no scored snapshot</div>;
  const dims = breakdown.dimensions;
  const movers: Record<string, number> = {};
  for (const m of delta?.top_movers || []) movers[`${m.dimension}.${m.feature}`] = m.delta;

  return (
    <div className="tree">
      <div className="row">
        <span className="lbl">priority</span>
        <b className="mono">{num(breakdown.priority)}</b>
        {delta ? <Delta v={delta.priority_delta} /> : null}
      </div>
      {Object.entries<any>(dims).map(([dname, d]) => (
        <details key={dname} open={dname === "timing" || dname === "quality"}>
          <summary>
            <span className="lbl">{dname}</span>{" "}
            {d.status === "unknown" ? (
              <span className="unknown">unknown</span>
            ) : (
              <>
                <span className="mono">{num(d.score)}</span>
                <span className="faint mono"> × {num(d.effective_weight, 2)} = </span>
                <b className="mono">{num(d.weighted)}</b>
              </>
            )}
            {d.access ? (
              <span className="faint">
                {" "}
                · {d.access.hops}-hop {d.access.strength} · {(d.access.node_names || []).join(" → ")}
              </span>
            ) : null}
          </summary>
          {Object.entries<any>(d.features || {}).map(([fname, f]) => (
            <details key={fname}>
              <summary>
                <span className="lbl">{fname}</span>{" "}
                {f.status === "unknown" || f.included === false ? (
                  <span className="unknown">{f.status === "unknown" ? "unknown — excluded" : "excluded"}</span>
                ) : (
                  <>
                    raw <span className="mono">{fmtRaw(f.raw)}</span>
                    <span className="faint"> → norm </span>
                    <span className="mono">{num(f.normalized, 2)}</span>
                    <span className="faint"> × w </span>
                    <span className="mono">{num(f.effective_weight ?? f.weight, 3)}</span>
                    <span className="faint"> = </span>
                    <b className="mono">{num(f.contribution, 3)}</b>
                  </>
                )}
                {movers[`${dname}.${fname}`] !== undefined ? (
                  <>
                    {" "}
                    <Delta v={movers[`${dname}.${fname}`]} />
                  </>
                ) : null}
              </summary>
              <div className="row">
                <span className="lbl">normalization</span>
                <span className="mono">
                  {f.normalization} — {f.normalization_detail?.formula}
                </span>
              </div>
              {f.normalization_detail?.params && Object.keys(f.normalization_detail.params).length ? (
                <div className="row">
                  <span className="lbl">params</span>
                  <span className="mono">{JSON.stringify(f.normalization_detail.params)}</span>
                </div>
              ) : null}
              {f.missing_behavior ? (
                <div className="row">
                  <span className="lbl">missing behavior</span>
                  <span className="mono">{f.missing_behavior}</span>
                </div>
              ) : null}
              {f.fit_evidence?.length ? (
                <div className="row">
                  <span className="lbl">matched keywords</span>
                  <span className="mono">{f.fit_evidence.join(", ")}</span>
                </div>
              ) : null}
              {f.source_fact_ids?.length ? (
                <div className="row">
                  <span className="lbl">source facts</span>
                  <span className="mono faint">{f.source_fact_ids.join(", ")}</span>
                </div>
              ) : null}
              {f.signals
                ? f.signals.map((s: any, i: number) => (
                    <div className="row" key={i}>
                      <span className="lbl">
                        signal {i + 1} · age {s.days_since}d · half-life {s.half_life_days}d
                      </span>
                      <span className="mono">
                        {num(s.initial, 2)} × e^(−λ·t) = {num(s.value, 3)}
                        {s.probability != null ? ` · inference p=${s.probability}` : ""}
                      </span>
                    </div>
                  ))
                : null}
            </details>
          ))}
        </details>
      ))}
      <div className="row" style={{ marginTop: 6 }}>
        <span className="lbl">confidence (separate from priority)</span>
        <span className="mono">{num(breakdown.confidence?.score, 3)}</span>
        <span className="faint mono">
          {" "}
          {Object.entries<number>(breakdown.confidence?.components || {})
            .map(([k, v]) => `${k} ${v}`)
            .join(" · ")}
        </span>
      </div>
    </div>
  );
}

function num(v: any, d = 1) {
  return typeof v === "number" ? v.toFixed(d) : "—";
}
function fmtRaw(v: any) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v).slice(0, 60);
  return String(v);
}
