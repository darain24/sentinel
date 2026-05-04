"use client";

import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { useEffect } from "react";
import { LucideIcon } from "lucide-react";

export function StatCounter({
  label,
  value,
  icon: Icon,
  accent = "cyan",
}: {
  label: string;
  value: number;
  icon: LucideIcon;
  accent?: "cyan" | "warn" | "crit" | "ok";
}) {
  const mv = useMotionValue(0);
  const spring = useSpring(mv, { stiffness: 120, damping: 18 });
  const rounded = useTransform(spring, (v) => Math.round(v).toLocaleString());

  useEffect(() => {
    mv.set(0);
    const t = setTimeout(() => mv.set(value), 80);
    return () => clearTimeout(t);
  }, [mv, value]);

  const ring =
    accent === "crit"
      ? "ring-red-400/30"
      : accent === "warn"
        ? "ring-orange-400/30"
        : accent === "ok"
          ? "ring-emerald-400/30"
          : "ring-cyan-400/30";

  const text =
    accent === "crit"
      ? "text-red-300"
      : accent === "warn"
        ? "text-orange-200"
        : accent === "ok"
          ? "text-emerald-200"
          : "text-cyan-200";

  return (
    <motion.div layout className={`glass rounded-xl p-4 ${ring} ring-1`}>
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
          <motion.div className={`font-display text-3xl font-semibold ${text}`}>{rounded}</motion.div>
        </div>
        <div className="rounded-lg bg-white/5 p-2 text-cyan-200">
          <Icon className="h-5 w-5" />
        </div>
      </div>
      <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-slate-800">
        <motion.div
          className="h-full bg-gradient-to-r from-cyan-500 to-blue-500"
          initial={{ width: "0%" }}
          animate={{ width: "100%" }}
          transition={{ duration: 1.2, ease: "easeOut" }}
        />
      </div>
    </motion.div>
  );
}
