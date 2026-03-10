"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { StatusBadge } from "@/components/ui/status-badge";
import { analysis, fields as fieldsApi } from "@/lib/api";
import { formatDate, formatDateTime, formatNumber } from "@/lib/utils";
import { ArrowLeft, RefreshCw } from "lucide-react";
import type { AnalysisJob, Field } from "@/types/api";

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-2">
      <dt className="text-gray-500">{label}</dt>
      <dd className="font-mono font-medium text-gray-900">{value}</dd>
    </div>
  );
}

function Bar({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
}) {
  const pct = max > 0 ? Math.min((Math.abs(value) / max) * 100, 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-gray-500">{label}</span>
        <span className="font-mono text-gray-700">{formatNumber(value, 4)}</span>
      </div>
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function AnalysisDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [field, setField] = useState<Field | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadJob() {
    if (!id) return;
    try {
      const j = await analysis.get(id);
      setJob(j);
      try {
        const f = await fieldsApi.get(j.field_id);
        setField(f);
      } catch {}
    } catch {}
    setLoading(false);
  }

  useEffect(() => {
    loadJob();
  }, [id]);

  // Auto-refresh if job is still running
  useEffect(() => {
    if (!job || (job.status !== "pending" && job.status !== "running")) return;
    const interval = setInterval(loadJob, 5000);
    return () => clearInterval(interval);
  }, [job?.status]);

  if (loading) {
    return (
      <AppShell>
        <div className="p-6 text-gray-400">Loading analysis...</div>
      </AppShell>
    );
  }

  if (!job) {
    return (
      <AppShell>
        <div className="p-6 text-red-600">Analysis job not found.</div>
      </AppShell>
    );
  }

  const r = job.result;
  const absMax = r
    ? Math.max(Math.abs(r.min ?? 0), Math.abs(r.max ?? 0), Math.abs(r.mean ?? 0))
    : 1;

  return (
    <AppShell>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center gap-4">
          <Link
            href="/analysis"
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-gray-600" />
          </Link>
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900">
                {job.index_type.toUpperCase()} Analysis
              </h1>
              <StatusBadge status={job.status} />
            </div>
            <p className="text-sm text-gray-500 mt-0.5">
              {field ? field.name : job.field_id.slice(0, 8)} &middot;{" "}
              {formatDateTime(job.created_at)}
            </p>
          </div>
          {(job.status === "pending" || job.status === "running") && (
            <button
              onClick={loadJob}
              className="btn-secondary flex items-center gap-2 text-sm"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Results Panel */}
          <div className="lg:col-span-2 space-y-6">
            {r ? (
              <>
                {/* Stat Bars */}
                <div className="card p-5 space-y-4">
                  <h3 className="font-semibold text-gray-900">
                    Index Statistics
                  </h3>
                  <Bar
                    label="Mean"
                    value={r.mean ?? 0}
                    max={absMax}
                    color="bg-brand-500"
                  />
                  <Bar
                    label="Median"
                    value={r.median ?? r.mean ?? 0}
                    max={absMax}
                    color="bg-brand-400"
                  />
                  <Bar
                    label="Min"
                    value={r.min ?? 0}
                    max={absMax}
                    color="bg-blue-400"
                  />
                  <Bar
                    label="Max"
                    value={r.max ?? 0}
                    max={absMax}
                    color="bg-blue-600"
                  />
                  <Bar
                    label="Std Dev"
                    value={r.std ?? 0}
                    max={absMax}
                    color="bg-gray-400"
                  />
                  {r.p10 != null && (
                    <Bar
                      label="P10"
                      value={r.p10}
                      max={absMax}
                      color="bg-purple-400"
                    />
                  )}
                  {r.p90 != null && (
                    <Bar
                      label="P90"
                      value={r.p90}
                      max={absMax}
                      color="bg-purple-600"
                    />
                  )}
                </div>

                {/* Pixel Stats */}
                <div className="card p-5">
                  <h3 className="font-semibold text-gray-900 mb-3">
                    Coverage
                  </h3>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="text-center p-3 bg-gray-50 rounded-lg">
                      <div className="text-2xl font-bold text-gray-900">
                        {r.pixel_count.toLocaleString()}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        Total Pixels
                      </div>
                    </div>
                    <div className="text-center p-3 bg-green-50 rounded-lg">
                      <div className="text-2xl font-bold text-green-700">
                        {r.valid_pixel_count.toLocaleString()}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        Valid Pixels
                      </div>
                    </div>
                    <div className="text-center p-3 bg-amber-50 rounded-lg">
                      <div className="text-2xl font-bold text-amber-700">
                        {formatNumber(r.nodata_fraction * 100, 1)}%
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        NoData
                      </div>
                    </div>
                  </div>
                </div>
              </>
            ) : job.status === "failed" ? (
              <div className="card p-5">
                <h3 className="font-semibold text-red-700 mb-2">
                  Analysis Failed
                </h3>
                <p className="text-sm text-gray-600">
                  {job.error_message || "An unknown error occurred."}
                </p>
              </div>
            ) : (
              <div className="card p-8 text-center">
                <div className="animate-pulse">
                  <div className="w-12 h-12 bg-brand-100 rounded-full mx-auto mb-4 flex items-center justify-center">
                    <RefreshCw className="w-6 h-6 text-brand-500 animate-spin" />
                  </div>
                  <p className="text-gray-500">
                    Analysis is {job.status}. Results will appear automatically.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Info Sidebar */}
          <div className="space-y-4">
            <div className="card p-5">
              <h3 className="font-semibold text-gray-900 mb-3">Job Details</h3>
              <dl className="space-y-0 text-sm divide-y divide-gray-100">
                <StatRow label="Job ID" value={job.id.slice(0, 8)} />
                <StatRow label="Index" value={job.index_type.toUpperCase()} />
                <StatRow label="Status" value={job.status} />
                <StatRow label="Created" value={formatDateTime(job.created_at)} />
                {job.completed_at && (
                  <StatRow
                    label="Completed"
                    value={formatDateTime(job.completed_at)}
                  />
                )}
              </dl>
            </div>

            <div className="card p-5">
              <h3 className="font-semibold text-gray-900 mb-3">Scene</h3>
              <p className="text-sm font-mono text-gray-600 break-all">
                {job.scene_id}
              </p>
            </div>

            {field && (
              <div className="card p-5">
                <h3 className="font-semibold text-gray-900 mb-3">Field</h3>
                <Link
                  href={`/fields/${field.id}`}
                  className="text-sm text-brand-600 hover:text-brand-700"
                >
                  {field.name}
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
