"use client";

import { useEffect, useState } from "react";
import { format } from "date-fns";

export function LiveClock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  if (!now) return <span className="font-mono text-sm text-slate-500">--:--:--</span>;
  return <span className="font-mono text-sm text-cyan-200">{format(now, "HH:mm:ss")}</span>;
}
