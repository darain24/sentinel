"use client";

export function ErrorCard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="glass rounded-xl border border-red-500/30 bg-red-500/5 p-6 text-center">
      <div className="font-display text-lg text-red-300">System fault</div>
      <p className="mt-2 text-sm text-slate-400">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 rounded-lg bg-cyan-500/20 px-4 py-2 text-sm font-semibold text-cyan-200 ring-1 ring-cyan-500/40 hover:bg-cyan-500/30"
      >
        Retry
      </button>
    </div>
  );
}
