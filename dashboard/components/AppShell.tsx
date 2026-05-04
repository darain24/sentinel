"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, AlertTriangle, BarChart3, FileText, Zap } from "lucide-react";
import { ReactNode, useState } from "react";
import { motion } from "framer-motion";

const links = [
  { href: "/dashboard", label: "Dashboard", icon: Activity },
  { href: "/anomalies", label: "Anomalies", icon: AlertTriangle },
  { href: "/forecasting", label: "Forecasting", icon: BarChart3 },
  { href: "/reports", label: "Reports", icon: FileText },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex min-h-screen">
      <aside
        className={`sticky top-0 flex h-screen flex-col border-r border-slate-800/80 bg-[#0B1020]/95 px-3 py-6 backdrop-blur transition-all ${
          collapsed ? "w-[72px]" : "w-60"
        }`}
      >
        <div className="mb-8 flex items-center gap-2 px-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-300 ring-1 ring-cyan-500/30">
            <Zap className="h-5 w-5" />
          </div>
          {!collapsed && (
            <div>
              <div className="font-display text-lg font-semibold tracking-tight text-white">SENTINEL</div>
              <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">BESCOM</div>
            </div>
          )}
        </div>
        <nav className="flex flex-1 flex-col gap-1">
          {links.map((l) => {
            const active = pathname === l.href;
            const Icon = l.icon;
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                  active
                    ? "border border-cyan-500/30 bg-cyan-500/10 text-cyan-200 shadow-[inset_3px_0_0_#00D4FF]"
                    : "text-slate-400 hover:bg-white/5 hover:text-white"
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {!collapsed && <span>{l.label}</span>}
              </Link>
            );
          })}
        </nav>
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="mt-4 rounded-lg border border-slate-800 px-2 py-2 text-xs text-slate-500 hover:border-slate-600 hover:text-slate-300"
        >
          {collapsed ? "»" : "« Collapse"}
        </button>
        <div className="mt-auto space-y-1 px-2 pt-6 text-[11px] text-slate-600">
          {!collapsed && (
            <>
              <div>BESCOM © 2026</div>
              <div className="text-slate-500">Powered by SENTINEL</div>
            </>
          )}
        </div>
      </aside>
      <motion.main layout className="flex-1 overflow-x-hidden">
        {children}
      </motion.main>
    </div>
  );
}
