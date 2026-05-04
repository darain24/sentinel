"use client";

import useSWR from "swr";
import { useEffect, useMemo, useState } from "react";
import { apiGet } from "@/lib/api";
import { ErrorCard } from "@/components/ErrorCard";
import { Printer } from "lucide-react";

type Report = {
  report_id: string;
  generated_at: string;
  meter: Record<string, unknown>;
  anomaly_details: Record<string, unknown>;
  shap_explanation: string;
  recommendation: string;
  priority: string;
  evidence: string[];
};

const fetcher = (u: string) => apiGet<Report>(u);

const STORAGE_KEY = "sentinel_reports_v1";

export default function ReportsPage() {
  const [meterFromQuery, setMeterFromQuery] = useState<string | null>(null);
  const [items, setItems] = useState<Report[]>([]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setItems(JSON.parse(raw) as Report[]);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const qp = new URLSearchParams(window.location.search);
    setMeterFromQuery(qp.get("meter"));
  }, []);

  const persist = (next: Report[]) => {
    setItems(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  };

  const { data: seeded } = useSWR("/api/anomalies", (u) => apiGet<Record<string, unknown>[]>(u), { refreshInterval: 0 });

  useEffect(() => {
    if (!seeded?.length || items.length) return;
    const top = seeded.slice(0, 5);
    Promise.all(
      top.map((m) => apiGet<Report>(`/api/inspection-report/${encodeURIComponent(String(m.meter_id))}`)),
    ).then((reports) => persist(reports)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seeded]);

  const { data: active, error, mutate } = useSWR<Report>(
    meterFromQuery ? `/api/inspection-report/${encodeURIComponent(meterFromQuery)}` : null,
    fetcher,
  );

  useEffect(() => {
    if (!active) return;
    setItems((prev) => {
      if (prev.find((p) => p.report_id === active.report_id)) return prev;
      return [active, ...prev];
    });
  }, [active]);

  const merged = useMemo(() => {
    const map = new Map<string, Report>();
    [...items, ...(active ? [active] : [])].forEach((r) => map.set(r.report_id, r));
    return Array.from(map.values()).sort((a, b) => (a.generated_at < b.generated_at ? 1 : -1));
  }, [items, active]);

  const [open, setOpen] = useState<Report | null>(null);

  return (
    <div className="space-y-6 p-6 lg:p-10">
      <header className="flex flex-col gap-3 border-b border-slate-800 pb-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="font-display text-2xl text-white">Inspection reports</h1>
          <p className="text-sm text-slate-400">Structured field packages generated from live anomaly context</p>
        </div>
        <button
          type="button"
          onClick={() => window.print()}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:border-cyan-500/40"
        >
          <Printer className="h-4 w-4" />
          Print / PDF
        </button>
      </header>

      {error && <ErrorCard message={(error as Error).message} onRetry={() => mutate()} />}

      <div className="glass overflow-hidden rounded-xl border border-slate-800">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-white/5 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-4 py-3">Report ID</th>
              <th className="px-4 py-3">Meter</th>
              <th className="px-4 py-3">Generated</th>
              <th className="px-4 py-3">Priority</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {merged.map((r) => (
              <tr key={r.report_id} className="cursor-pointer border-t border-slate-800 hover:bg-white/5" onClick={() => setOpen(r)}>
                <td className="px-4 py-3 font-mono text-xs text-cyan-200">{r.report_id}</td>
                <td className="px-4 py-3 text-slate-200">{String((r.meter as { meter_id?: string }).meter_id ?? "")}</td>
                <td className="px-4 py-3 text-slate-400">{new Date(r.generated_at).toLocaleString()}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-[11px] text-orange-100 ring-1 ring-orange-500/30">
                    {r.priority}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-400">Pending</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {open && (
        <article className="glass space-y-4 rounded-2xl p-6 print:border-0 print:shadow-none">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="font-display text-xl text-white">{open.report_id}</div>
              <div className="text-xs text-slate-500">{new Date(open.generated_at).toLocaleString()}</div>
            </div>
            <button type="button" className="text-sm text-cyan-300 hover:underline" onClick={() => setOpen(null)}>
              Close
            </button>
          </div>
          <section>
            <h3 className="mb-2 text-sm font-semibold text-slate-300">Meter</h3>
            <pre className="overflow-x-auto rounded-lg border border-slate-800 bg-black/40 p-3 text-xs text-slate-200">
              {JSON.stringify(open.meter, null, 2)}
            </pre>
          </section>
          <section>
            <h3 className="mb-2 text-sm font-semibold text-slate-300">Evidence</h3>
            <ul className="list-disc space-y-1 pl-5 text-sm text-slate-300">
              {open.evidence.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          </section>
          <section>
            <h3 className="mb-2 text-sm font-semibold text-slate-300">SHAP narrative</h3>
            <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-4 text-sm leading-relaxed text-cyan-50">
              {open.shap_explanation}
            </div>
          </section>
          <section>
            <h3 className="mb-2 text-sm font-semibold text-slate-300">Recommendation</h3>
            <p className="text-base font-semibold text-white">{open.recommendation}</p>
          </section>
        </article>
      )}
    </div>
  );
}
