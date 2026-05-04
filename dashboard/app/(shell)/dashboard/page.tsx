"use client";

import useSWR from "swr";
import dynamic from "next/dynamic";
import Link from "next/link";
import { format } from "date-fns";
import { Activity, Cpu, ShieldAlert, Zap } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { motion } from "framer-motion";
import { apiGet } from "@/lib/api";
import { LiveClock } from "@/components/LiveClock";
import { StatCounter } from "@/components/StatCounter";
import { Skeleton } from "@/components/Skeleton";
import { ErrorCard } from "@/components/ErrorCard";
import type { Zone } from "@/components/ZoneMap";

const ZoneMap = dynamic(() => import("@/components/ZoneMap").then((m) => ({ default: m.ZoneMap })), { ssr: false });

type Summary = {
  total_meters: number;
  flagged_count: number;
  critical_zones: { locality: string; max_risk_level: string }[];
  high_risk_feeders: string[];
  detection_accuracy: { precision?: number; recall?: number; f1?: number; false_positive_rate?: number };
  last_updated: string;
};

type AnomalySummary = {
  top_flagged_meters: Record<string, unknown>[];
};

type Overview = {
  hours: number[];
  forecast_kwh: number[];
  baseline_kwh: number[];
  capacity_reference_kwh: number[];
};

export default function DashboardPage() {
  const { data: summary, error: e1, mutate: m1, isLoading: l1 } = useSWR<Summary>(
    "/api/dashboard-summary",
    (u: string) => apiGet<Summary>(u),
    { refreshInterval: 30_000 },
  );
  const { data: zones, error: e2, mutate: m2, isLoading: l2 } = useSWR<Zone[]>(
    "/api/forecast/zones",
    (u: string) => apiGet<Zone[]>(u),
    { refreshInterval: 30_000 },
  );
  const { data: anom, error: e3, mutate: m3, isLoading: l3 } = useSWR<AnomalySummary>(
    "/api/anomaly-summary",
    (u: string) => apiGet<AnomalySummary>(u),
    { refreshInterval: 30_000 },
  );
  const { data: overview, error: e4, mutate: m4, isLoading: l4 } = useSWR<Overview>(
    "/api/forecast/overview-24h",
    (u: string) => apiGet<Overview>(u),
    { refreshInterval: 30_000 },
  );

  const err = e1 || e2 || e3 || e4;
  const retry = () => {
    void m1();
    void m2();
    void m3();
    void m4();
  };

  const chartData =
    overview?.hours?.map((h, i) => ({
      hour: `${h}:00`,
      forecast: overview.forecast_kwh[i],
      baseline: overview.baseline_kwh[i],
      cap: overview.capacity_reference_kwh[i],
    })) ?? [];

  const f1pct = summary?.detection_accuracy?.f1 != null ? Math.round(Number(summary.detection_accuracy.f1) * 100) : 0;

  return (
    <div className="space-y-6 p-6 lg:p-10">
      <header className="flex flex-col gap-4 border-b border-slate-800 pb-6 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-300 ring-1 ring-cyan-500/30">
              <Zap className="h-6 w-6" />
            </div>
            <div>
              <h1 className="font-display text-2xl font-semibold tracking-tight text-white">SENTINEL</h1>
              <p className="text-sm text-slate-400">BESCOM Smart Grid Intelligence</p>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm text-slate-400">
          <div className="flex items-center gap-2 rounded-full border border-slate-800 bg-white/5 px-3 py-1">
            <LiveClock />
          </div>
          <div className="flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-emerald-200">
            <span className="pulse-dot inline-block h-2 w-2 rounded-full bg-emerald-400" />
            SYSTEM ACTIVE
          </div>
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-cyan-400" />
            </span>
            <span className="text-cyan-200">LIVE</span>
          </div>
          <div className="text-xs text-slate-500">
            Last sync:{" "}
            {summary?.last_updated ? format(new Date(summary.last_updated), "yyyy-MM-dd HH:mm:ss") : "—"}
          </div>
        </div>
      </header>

      {err ? (
        <ErrorCard message={(err as Error).message} onRetry={retry} />
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {l1 ? (
              <>
                <Skeleton className="h-28" />
                <Skeleton className="h-28" />
                <Skeleton className="h-28" />
                <Skeleton className="h-28" />
              </>
            ) : (
              <>
                <StatCounter label="Total meters monitored" value={summary?.total_meters ?? 0} icon={Cpu} accent="ok" />
                <StatCounter
                  label="Flagged for inspection"
                  value={summary?.flagged_count ?? 0}
                  icon={ShieldAlert}
                  accent="crit"
                />
                <StatCounter
                  label="Critical risk zones"
                  value={summary?.critical_zones?.length ?? 0}
                  icon={Activity}
                  accent="warn"
                />
                <StatCounter label="Model F1 (detection)" value={f1pct} icon={Zap} accent="cyan" />
              </>
            )}
          </div>

          <div className="grid gap-6 lg:grid-cols-5">
            <section className="glass rounded-2xl p-4 lg:col-span-3">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-display text-lg text-white">Zone risk map</h2>
                <span className="text-xs text-slate-500">Bangalore operational view</span>
              </div>
              {l2 ? <Skeleton className="h-[420px]" /> : <ZoneMap zones={zones ?? []} />}
            </section>
            <section className="glass rounded-2xl p-4 lg:col-span-2">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-display text-lg text-white">Top flagged meters</h2>
                <Link href="/anomalies" className="text-xs text-cyan-300 hover:underline">
                  View all
                </Link>
              </div>
              <div className="space-y-3">
                {l3 ? (
                  <Skeleton className="h-64" />
                ) : (
                  (anom?.top_flagged_meters ?? []).map((m, idx) => (
                    <motion.div
                      key={String(m.meter_id)}
                      initial={{ opacity: 0, x: 12 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: idx * 0.04 }}
                      className="flex items-center gap-3 rounded-lg border border-slate-800 bg-white/5 p-3"
                    >
                      <div className="font-mono text-xs text-cyan-200">{String(m.meter_id)}</div>
                      <div className="flex-1 text-xs text-slate-300">{String(m.locality)}</div>
                      <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-[10px] text-orange-200">
                        {String(m.anomaly_type)}
                      </span>
                      <div className="w-24">
                        <div className="h-1.5 rounded-full bg-slate-800">
                          <div
                            className="h-1.5 rounded-full bg-gradient-to-r from-orange-500 to-red-500"
                            style={{ width: `${Number(m.confidence_score)}%` }}
                          />
                        </div>
                      </div>
                      <Link
                        href={`/reports?meter=${encodeURIComponent(String(m.meter_id))}`}
                        className="rounded-md border border-cyan-500/40 px-2 py-1 text-[11px] text-cyan-200 hover:bg-cyan-500/10"
                      >
                        Report
                      </Link>
                    </motion.div>
                  ))
                )}
              </div>
            </section>
          </div>

          <section className="glass rounded-2xl p-4">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="font-display text-lg text-white">24-hour demand forecast</h2>
              <span className="text-xs text-slate-500">SENTINEL forecast vs historical average</span>
            </div>
            {l4 ? (
              <Skeleton className="h-72" />
            ) : (
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="fc" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#00D4FF" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#00D4FF" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e2a45" />
                    <XAxis dataKey="hour" stroke="#6b7a9f" tick={{ fill: "#6b7a9f", fontSize: 11 }} />
                    <YAxis stroke="#6b7a9f" tick={{ fill: "#6b7a9f", fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{ background: "#0f1629", border: "1px solid #1e2a45", borderRadius: 8 }}
                      labelStyle={{ color: "#e8edf5" }}
                    />
                    <Area type="monotone" dataKey="forecast" stroke="#00D4FF" fill="url(#fc)" strokeWidth={2} name="Forecast" />
                    <Line type="monotone" dataKey="baseline" stroke="#6b7a9f" dot={false} strokeWidth={2} name="Baseline" />
                    <Line
                      type="monotone"
                      dataKey="cap"
                      stroke="#ff2d55"
                      strokeDasharray="5 5"
                      dot={false}
                      name="Capacity ref."
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
