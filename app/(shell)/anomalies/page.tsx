"use client";

import useSWR from "swr";
import { useMemo, useState } from "react";
import { apiGet } from "@/lib/api";
import { ErrorCard } from "@/components/ErrorCard";
import { Skeleton } from "@/components/Skeleton";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { motion, AnimatePresence } from "framer-motion";
import { Download, X } from "lucide-react";

type Row = Record<string, string | number>;
type MeterDetail = {
  readings_last_7d?: { timestamp: string; consumption_kwh: number }[];
};

const anomalyFetcher = (path: string) => apiGet<Row[]>(path);
const detailFetcher = (path: string) => apiGet<MeterDetail>(path);

const LOCALITIES = [
  "All",
  "Jayanagar",
  "Indiranagar",
  "Whitefield",
  "Koramangala",
  "Hebbal",
  "Electronic City",
  "Yelahanka",
  "Marathahalli",
  "Rajajinagar",
  "BTM Layout",
];

const TYPES = ["ALL", "THEFT", "TAMPERING", "PEER_DEVIATION", "FEEDER_LOSS"];

function chipColor(t: string) {
  switch (t) {
    case "THEFT":
      return "bg-red-500/20 text-red-200 ring-red-500/40";
    case "TAMPERING":
      return "bg-orange-500/20 text-orange-200 ring-orange-500/40";
    case "PEER_DEVIATION":
      return "bg-yellow-500/15 text-yellow-100 ring-yellow-500/30";
    case "FEEDER_LOSS":
      return "bg-purple-500/20 text-purple-100 ring-purple-500/40";
    default:
      return "bg-slate-500/15 text-slate-200 ring-slate-500/30";
  }
}

export default function AnomaliesPage() {
  const [locality, setLocality] = useState("All");
  const [atype, setAtype] = useState("ALL");
  const [minConf, setMinConf] = useState(0);
  const [feeder, setFeeder] = useState("All");
  const [selected, setSelected] = useState<Row | null>(null);

  const qs = useMemo(() => {
    const p = new URLSearchParams();
    if (locality !== "All") p.set("locality", locality);
    if (atype !== "ALL") p.set("type", atype);
    if (minConf > 0) p.set("min_confidence", String(minConf));
    if (feeder !== "All") p.set("feeder_id", feeder);
    const s = p.toString();
    return s ? `?${s}` : "";
  }, [locality, atype, minConf, feeder]);

  const { data, error, mutate, isLoading } = useSWR<Row[]>(`/api/anomalies${qs}`, anomalyFetcher, {
    refreshInterval: 30_000,
  });

  const { data: detail } = useSWR<MeterDetail>(
    selected ? `/api/meters/${encodeURIComponent(String(selected.meter_id))}` : null,
    detailFetcher,
  );

  const exportCsv = () => {
    if (!data?.length) return;
    const cols = Object.keys(data[0]);
    const lines = [cols.join(","), ...data.map((r) => cols.map((c) => JSON.stringify(r[c] ?? "")).join(","))];
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "sentinel_anomalies.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6 p-6 lg:p-10">
      <header className="flex flex-col gap-4 border-b border-slate-800 pb-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="font-display text-2xl text-white">Anomaly detection</h1>
          <p className="text-sm text-slate-400">Meter-level fusion scoring (IF + peer + feeder)</p>
        </div>
        <button
          type="button"
          onClick={exportCsv}
          className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/20"
        >
          <Download className="h-4 w-4" />
          Export CSV
        </button>
      </header>

      {error ? (
        <ErrorCard message={(error as Error).message} onRetry={() => mutate()} />
      ) : (
        <>
          <div className="glass flex flex-col gap-4 rounded-xl p-4 lg:flex-row lg:items-end">
            <label className="flex flex-col gap-1 text-xs text-slate-400">
              Locality
              <select
                value={locality}
                onChange={(e) => setLocality(e.target.value)}
                className="rounded-lg border border-slate-800 bg-[#0A0E1A] px-3 py-2 text-sm text-white"
              >
                {LOCALITIES.map((l) => (
                  <option key={l} value={l === "All" ? "All" : l}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex flex-col gap-2">
              <div className="text-xs text-slate-400">Anomaly type</div>
              <div className="flex flex-wrap gap-2">
                {TYPES.map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setAtype(t)}
                    className={`rounded-full px-3 py-1 text-xs ring-1 ${
                      atype === t ? "bg-cyan-500/20 text-cyan-100 ring-cyan-400/50" : "bg-white/5 text-slate-300 ring-slate-700"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
            <label className="flex flex-col gap-1 text-xs text-slate-400">
              Min confidence ({minConf}%)
              <input
                type="range"
                min={0}
                max={100}
                value={minConf}
                onChange={(e) => setMinConf(Number(e.target.value))}
                className="w-48 accent-cyan-400"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-400">
              Feeder
              <select
                value={feeder}
                onChange={(e) => setFeeder(e.target.value)}
                className="rounded-lg border border-slate-800 bg-[#0A0E1A] px-3 py-2 text-sm text-white"
              >
                <option>All</option>
                {Array.from({ length: 10 }, (_, i) => (
                  <option key={i} value={`F${String(i + 1).padStart(2, "0")}`}>
                    F{String(i + 1).padStart(2, "0")}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="glass overflow-hidden rounded-xl border border-slate-800">
            {isLoading ? (
              <Skeleton className="h-96 w-full" />
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-white/5 text-xs uppercase tracking-wide text-slate-400">
                    <tr>
                      <th className="px-4 py-3">Meter</th>
                      <th className="px-4 py-3">Locality</th>
                      <th className="px-4 py-3">Category</th>
                      <th className="px-4 py-3">Type</th>
                      <th className="px-4 py-3">Confidence</th>
                      <th className="px-4 py-3">Days</th>
                      <th className="px-4 py-3">Deviation %</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data ?? []).map((r) => (
                      <tr key={String(r.meter_id)} className="border-t border-slate-800/80 hover:bg-white/5">
                        <td className="px-4 py-3 font-mono text-cyan-200">{String(r.meter_id)}</td>
                        <td className="px-4 py-3 text-slate-300">{String(r.locality)}</td>
                        <td className="px-4 py-3 text-slate-400">{String(r.category)}</td>
                        <td className="px-4 py-3">
                          <span className={`rounded-full px-2 py-0.5 text-[11px] ring-1 ${chipColor(String(r.anomaly_type))}`}>
                            {String(r.anomaly_type)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-24 rounded-full bg-slate-800">
                              <div
                                className="h-1.5 rounded-full bg-gradient-to-r from-cyan-400 to-blue-500"
                                style={{ width: `${Number(r.confidence_score)}%` }}
                              />
                            </div>
                            <span className="text-xs text-slate-400">{Number(r.confidence_score)}%</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-slate-300">{String(r.days_anomalous)}</td>
                        <td className="px-4 py-3 text-slate-300">{Number(r.deviation_pct).toFixed(1)}</td>
                        <td className="px-4 py-3">
                          <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-[11px] text-red-200 ring-1 ring-red-500/40">
                            {String(r.flag_status)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <button
                            type="button"
                            onClick={() => setSelected(r)}
                            className="rounded-md border border-slate-700 px-2 py-1 text-xs text-cyan-200 hover:border-cyan-500/50"
                          >
                            View detail
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      <AnimatePresence>
        {selected && (
          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 260, damping: 30 }}
            className="fixed inset-y-0 right-0 z-40 w-full max-w-md border-l border-slate-800 bg-[#0B1020]/98 p-5 shadow-2xl backdrop-blur"
          >
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="font-display text-lg text-white">{String(selected.meter_id)}</div>
                <div className="text-xs text-slate-400">
                  {String(selected.locality)} · {String(selected.category)}
                </div>
              </div>
              <button type="button" onClick={() => setSelected(null)} className="rounded-full p-2 hover:bg-white/5">
                <X className="h-5 w-5 text-slate-300" />
              </button>
            </div>

            <div className="mb-4 h-40">
              {detail && Array.isArray(detail.readings_last_7d) ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={detail.readings_last_7d.map((x) => ({
                      t: new Date(x.timestamp).getTime(),
                      kwh: x.consumption_kwh,
                    }))}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e2a45" />
                    <XAxis dataKey="t" hide />
                    <YAxis hide />
                    <Tooltip
                      labelFormatter={(v) => new Date(v as number).toLocaleString()}
                      contentStyle={{ background: "#0f1629", border: "1px solid #1e2a45" }}
                    />
                    <Area type="monotone" dataKey="kwh" stroke="#00D4FF" fill="#00D4FF33" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <Skeleton className="h-full" />
              )}
            </div>

            <div className="mb-3 rounded-lg border border-emerald-500/20 bg-black/40 p-3 font-mono text-xs text-emerald-100">
              <div className="mb-1 text-[10px] uppercase tracking-widest text-emerald-300/80">SHAP drivers</div>
              <div>1) {String(selected.shap_top_feature_1)}</div>
              <div>2) {String(selected.shap_top_feature_2)}</div>
              <div>3) {String(selected.shap_top_feature_3)}</div>
            </div>

            <p className="mb-4 text-sm leading-relaxed text-slate-300">{String(selected.explanation_text)}</p>

            <div className="flex flex-col gap-2">
              <a
                href={`/reports?meter=${encodeURIComponent(String(selected.meter_id))}`}
                className="rounded-lg bg-cyan-500/20 py-2 text-center text-sm font-semibold text-cyan-100 ring-1 ring-cyan-500/40 hover:bg-cyan-500/30"
              >
                Generate inspection report
              </a>
              <button
                type="button"
                title="False positive tracking is reserved for supervised retraining workflows."
                className="cursor-not-allowed rounded-lg border border-slate-800 py-2 text-sm text-slate-600"
                disabled
              >
                Mark as false positive
              </button>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  );
}
