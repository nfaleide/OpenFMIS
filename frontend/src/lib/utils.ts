import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatNumber(n: number | null | undefined, decimals = 2): string {
  if (n == null) return "N/A";
  return n.toFixed(decimals);
}

export function formatAcres(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${n.toLocaleString("en-US", { maximumFractionDigits: 1 })} ac`;
}

export function statusColor(
  status: string,
): { bg: string; text: string; dot: string } {
  switch (status) {
    case "complete":
      return { bg: "bg-green-50", text: "text-green-700", dot: "bg-green-500" };
    case "running":
      return { bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-500" };
    case "pending":
      return { bg: "bg-yellow-50", text: "text-yellow-700", dot: "bg-yellow-500" };
    case "failed":
      return { bg: "bg-red-50", text: "text-red-700", dot: "bg-red-500" };
    default:
      return { bg: "bg-gray-50", text: "text-gray-700", dot: "bg-gray-500" };
  }
}

export const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || "";
