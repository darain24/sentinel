"use client";

import useSWR from "swr";
import { Fragment, useMemo, useState } from "react";
import { apiGet } from "@/lib/api";
import { ErrorCard } from "@/components/ErrorCard";
import { Skeleton } from "@/components/Skeleton";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Acc = {
  feeder_id: string;
  locality: string;
  rmse: number;
  mae: number;
  mape: number;
  improvement_pct_vs_baseline: number;
};

type FeederResp = {
  feeder_id: string;
  hourly: { hour: number; predicted_kwh: number; risk_level: string }[];
  accuracy: Acc;
};

type Heat = { feeder_id: string; locality: string; hour: number; predicted_kwh: number; risk_level: string };

const riskRank: Record<string, number> = { LOW: 0, MEDIUM: 1, HIGH: 2, CRITICAL: 3 };

function riskBadge(level: string) {
  const map: Record<string, string> = {
    CRITICAL: "bg-red-500/20 text-red-200 ring-red-500/40",
    HIGH: "bg-orange-500/20 text-orange-200 ring-orange-500/40",
    MEDIUM: "bg-yellow-500/15 text-yellow-100 ring-yellow-500/30",
    LOW: "bg-emerald-500/15 text-emerald-100 ring-emerald-500/30",
  };
  return map[level] ?? map.LOW;
}

export default function ForecastingPage() {
  const { data: acc, error: e1, mutate: m1 } = useSWR<Acc[]>(
    "/api/forecast/accuracy",
    (u: string) => apiGet<Acc[]>(u),
    { refreshInterval: 30_000 },
  );
  const { data: heat, error: e2, mutate: m2 } = useSWR<Heat[]>(
    "/api/forecast/heatmap",
    (u: string) => apiGet<Heat[]>(u),
    { refreshInterval: 30_000 },
  );

  const feeders = useMemo(() => acc?.map((a) => a.feeder_id) ?? Array.from({ length: 10 }, (_, i) => `F${String(i + 1).padStart(2, "0")}`), [acc]);
  const [fid, setFid] = useState("F01");

  const { data: fd, error: e3, isLoading } = useSWR<FeederResp>(
    `/api/forecast/feeder/${fid}`,
    (u: string) => apiGet<FeederResp>(u),
    { refreshInterval: 30_000 },
  );

  const err = e1 || e2 || e3;

  const chartRows =
    fd?.hourly?.map((h) => ({
      hour: `${h.hour}:00`,
      pred: h.predicted_kwh,
      risk: h.risk_level,
    })) ?? [];

  const peak = fd?.hourly?.reduce(
    (best, cur) => (cur.predicted_kwh > (best?.predicted_kwh ?? 0) ? cur : best),
    fd?.hourly?.[0],
  );

  const localities = Array.from(new Set((heat ?? []).map((h) => h.locality)));
  const hours = Array.from({ length: 24 }, (_, i) => i + 1);

  const cell = (loc: string, hour: number) => {
    const rows = (heat ?? []).filter((h) => h.locality === loc && h.hour === hour);
    if (!rows.length) return { risk: "LOW", kwh: 0 };
    const top = rows.reduce((a, b) => (riskRank[b.risk_level] > riskRank[a.risk_level] ? b : a));
    return { risk: top.risk_level, kwh: top.predicted_kwh };
  };

  return (
    <div className="space-y-6 p-6 lg:p-10">
      <header className="border-b border-slate-800 pb-4">
        <h1 className="font-display text-2xl text-white">Demand forecasting</h1>
        <p className="text-sm text-slate-400">Per-feeder XGBoost models with zone risk envelopes</p>
      </header>

      {err ? (
        <ErrorCard message={(err as Error).message} onRetry={() => { void m1(); void m2(); }} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-4">
          <aside className="glass space-y-2 rounded-xl p-3 lg:col-span-1">
            <div className="text-xs uppercase tracking-wide text-slate-500">Feeders</div>
            {feeders.map((f) => {
              const row = acc?.find((a) => a.feeder_id === f);
              const badge = row ? riskBadge("HIGH") : riskBadge("LOW");
              return (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFid(f)}
                  className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-sm ${
                    fid === f ? "border-cyan-500/60 bg-cyan-500/10 text-cyan-50" : "border-slate-800 bg-white/5 text-slate-200"
                  }`}
                >
                  <span className="font-mono">{f}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] ring-1 ${badge}`}>
                    {row ? `${row.improvement_pct_vs_baseline.toFixed(0)}%` : "—"}
                  </span>
                </button>
              );
            })}
          </aside>

          <section className="space-y-4 lg:col-span-3">
            <div className="glass rounded-xl p-4">
              {isLoading ? (
                <Skeleton className="h-72" />
              ) : (
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartRows}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e2a45" />
                      <XAxis dataKey="hour" stroke="#6b7a9f" tick={{ fill: "#6b7a9f", fontSize: 11 }} />
                      <YAxis stroke="#6b7a9f" tick={{ fill: "#6b7a9f", fontSize: 11 }} />
                      <Tooltip contentStyle={{ background: "#0f1629", border: "1px solid #1e2a45" }} />
                      <Legend />
                      <Line type="monotone" dataKey="pred" name="Predicted kWh" stroke="#00D4FF" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
              {peak && (
                <div className="mt-3 rounded-lg border border-orange-500/30 bg-orange-500/5 p-3 text-sm text-orange-100">
                  Expected peak at hour {peak.hour} — {peak.predicted_kwh.toFixed(1)} kWh — {peak.risk_level} risk
                </div>
              )}
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="glass rounded-xl p-4">
                <div className="mb-2 font-display text-sm text-white">Hourly risk timeline</div>
                <div className="flex h-10 gap-0.5">
                  {fd?.hourly
                    ?.slice()
                    .sort((a, b) => a.hour - b.hour)
                    .map((h) => (
                      <div
                        key={h.hour}
                        title={`${h.hour}:00 — ${h.risk_level}`}
                        className="flex-1 rounded-sm"
                        style={{
                          background:
                            h.risk_level === "CRITICAL"
                              ? "#FF2D55"
                              : h.risk_level === "HIGH"
                                ? "#FF6B35"
                                : h.risk_level === "MEDIUM"
                                  ? "#FFC857"
                                  : "#00E676",
                        }}
                      />
                    ))}
                </div>
              </div>
              <div className="glass rounded-xl p-4">
                <div className="mb-2 font-display text-sm text-white">Model accuracy</div>
                {fd?.accuracy ? (
                  <dl className="grid grid-cols-2 gap-2 text-sm text-slate-300">
                    <div>RMSE</div>
                    <div className="text-right text-white">{fd.accuracy.rmse?.toFixed(2)}</div>
                    <div>MAE</div>
                    <div className="text-right text-white">{fd.accuracy.mae?.toFixed(2)}</div>
                    <div>MAPE</div>
                    <div className="text-right text-white">{fd.accuracy.mape?.toFixed(2)}%</div>
                    <div>Δ vs baseline</div>
                    <div className="text-right text-cyan-200">{fd.accuracy.improvement_pct_vs_baseline?.toFixed(1)}%</div>
                  </dl>
                ) : (
                  <Skeleton className="h-24" />
                )}
              </div>
            </div>

            <div className="glass rounded-xl p-4">
              <div className="mb-3 font-display text-sm text-white">Zone risk heatmap (locality × hour)</div>
              <div className="overflow-x-auto">
                <div className="inline-grid gap-px" style={{ gridTemplateColumns: `96px repeat(${hours.length}, minmax(28px,1fr))` }}>
                  <div />
                  {hours.map((h) => (
                    <div key={h} className="text-center text-[10px] text-slate-500">
                      {h}
                    </div>
                  ))}
                  {localities.map((loc) => (
                    <Fragment key={loc}>
                      <div key={`${loc}-label`} className="pr-2 text-xs text-slate-300">
                        {loc}
                      </div>
                      {hours.map((h) => {
                        const c = cell(loc, h);
                        const bg =
                          c.risk === "CRITICAL"
                            ? "#FF2D55"
                            : c.risk === "HIGH"
                              ? "#FF6B35"
                              : c.risk === "MEDIUM"
                                ? "#FFC857"
                                : "#00E676";
                        return (
                          <div
                            key={`${loc}-${h}`}
                            title={`${loc} @ ${h}:00 — ${c.risk} — ${c.kwh.toFixed(2)} kWh`}
                            className="h-7 w-7 rounded-sm"
                            style={{ background: bg, opacity: 0.85 }}
                          />
                        );
                      })}
                    </Fragment>
                  ))}
                </div>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
