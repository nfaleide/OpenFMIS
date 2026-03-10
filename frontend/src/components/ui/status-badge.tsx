import { statusColor, cn } from "@/lib/utils";

export function StatusBadge({ status }: { status: string }) {
  const colors = statusColor(status);
  return (
    <span
      className={cn(
        "badge gap-1.5",
        colors.bg,
        colors.text,
      )}
    >
      <span className={cn("w-1.5 h-1.5 rounded-full", colors.dot)} />
      {status}
    </span>
  );
}
