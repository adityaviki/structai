/**
 * Pure formatting helpers. No React, no DOM.
 */

export function humanBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = n / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[i]}`;
}

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 60 * 60],
  ["month", 30 * 24 * 60 * 60],
  ["day", 24 * 60 * 60],
  ["hour", 60 * 60],
  ["minute", 60],
  ["second", 1],
];

export function relativeTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const delta = Math.round((t - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (const [unit, seconds] of RELATIVE_UNITS) {
    if (Math.abs(delta) >= seconds || unit === "second") {
      return formatter.format(Math.round(delta / seconds), unit);
    }
  }
  return formatter.format(delta, "second");
}

export function pct(rate: number): string {
  if (!Number.isFinite(rate)) return "—";
  return `${(rate * 100).toFixed(rate < 0.01 && rate > 0 ? 2 : 1)}%`;
}

export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function stringifyError(error: unknown): string {
  if (!error) return "unknown error";
  if (typeof error === "string") return error;
  if (typeof error === "object") {
    const detail = (error as { detail?: string }).detail;
    if (typeof detail === "string") return detail;
    return JSON.stringify(error);
  }
  return String(error);
}
