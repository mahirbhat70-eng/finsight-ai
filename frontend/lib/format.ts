/** INR formatting (Playbook P5.1): 1234.5 -> "Rs 1,234.5 Cr"; 0.113 -> "11.3%"; 4.2x; +180bps. */

export function formatInr(value: number | null | undefined, dp = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `Rs ${value.toLocaleString("en-IN", { maximumFractionDigits: dp })} Cr`;
}

export function formatPercent(value: number | null | undefined, dp = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(dp)}%`;
}

export function formatX(value: number | null | undefined, dp = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(dp)}x`;
}

export function formatBps(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const bps = value * 10_000;
  return `${bps >= 0 ? "+" : ""}${bps.toFixed(0)}bps`;
}

export function formatDays(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(0)} days`;
}

export function formatSharePrice(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `Rs ${value.toFixed(2)}`;
}
