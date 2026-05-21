import type { FileRow } from "../lib/useFiles";
import { cn } from "../lib/format";

const LABELS: Record<FileRow["status"], { text: string; symbol: string; cls: string; aria?: string }> = {
  queued: { text: "Queued", symbol: "⏳", cls: "sb sb--queued" },
  profiling: {
    text: "Profiling…",
    symbol: "⚙",
    cls: "sb sb--profiling",
    aria: "polite",
  },
  profiled: { text: "Profiled", symbol: "✓", cls: "sb sb--profiled" },
  failed: { text: "Failed", symbol: "!", cls: "sb sb--failed" },
};

export function StatusBadge({ status }: { status: FileRow["status"] }): JSX.Element {
  const info = LABELS[status];
  return (
    <span
      className={cn(info.cls)}
      aria-live={info.aria as "polite" | undefined}
      role={status === "failed" ? "status" : undefined}
    >
      <span className="sb__symbol" aria-hidden="true">
        {info.symbol}
      </span>
      <span className="sb__text">{info.text}</span>
    </span>
  );
}
