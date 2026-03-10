"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { StatusBadge } from "@/components/ui/status-badge";
import { analysis, fields as fieldsApi } from "@/lib/api";
import { formatDate, formatNumber } from "@/lib/utils";
import { BarChart3, Filter } from "lucide-react";
import type { AnalysisJob, Field } from "@/types/api";

export default function AnalysisListPage() {
  return (
    <Suspense>
      <AnalysisListContent />
    </Suspense>
  );
}

function AnalysisListContent() {
  const searchParams = useSearchParams();
  const preselectedFieldId = searchParams.get("field");

  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [fieldList, setFieldList] = useState<Field[]>([]);
  const [filterField, setFilterField] = useState(preselectedFieldId || "");
  const [filterStatus, setFilterStatus] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fieldsApi.list().then((r) => setFieldList(r.items)).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    analysis
      .list(filterField || undefined)
      .then((r) => setJobs(r.items))
      .catch(() => setJobs([]))
      .finally(() => setLoading(false));
  }, [filterField]);

  const filtered = filterStatus
    ? jobs.filter((j) => j.status === filterStatus)
    : jobs;

  const fieldName = (id: string) =>
    fieldList.find((f) => f.id === id)?.name || id.slice(0, 8);

  const statusCounts = jobs.reduce(
    (acc, j) => {
      acc[j.status] = (acc[j.status] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  return (
    <AppShell>
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Analysis Jobs</h1>
            <p className="text-sm text-gray-500 mt-1">
              {jobs.length} total jobs
            </p>
          </div>
          <Link
            href="/scenes"
            className="btn-satshot flex items-center gap-2"
          >
            <BarChart3 className="w-4 h-4" />
            New Analysis
          </Link>
        </div>

        {/* Status Summary */}
        <div className="flex gap-2">
          <button
            onClick={() => setFilterStatus("")}
            className={`badge cursor-pointer ${!filterStatus ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
          >
            All ({jobs.length})
          </button>
          {Object.entries(statusCounts).map(([status, count]) => (
            <button
              key={status}
              onClick={() => setFilterStatus(filterStatus === status ? "" : status)}
              className={`badge cursor-pointer ${filterStatus === status ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
            >
              {status} ({count})
            </button>
          ))}
        </div>

        {/* Filters */}
        <div className="flex gap-3">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-400" />
            <select
              value={filterField}
              onChange={(e) => setFilterField(e.target.value)}
              className="input max-w-xs"
            >
              <option value="">All Fields</option>
              {fieldList.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Jobs Table */}
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-5 py-3">
                  Index
                </th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-5 py-3">
                  Field
                </th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-5 py-3">
                  Scene
                </th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-5 py-3">
                  Status
                </th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-5 py-3">
                  Mean
                </th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-5 py-3">
                  Date
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-gray-400">
                    Loading jobs...
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-gray-400">
                    No analysis jobs found.
                    <br />
                    <Link href="/scenes" className="text-brand-600 text-sm">
                      Search scenes to start an analysis
                    </Link>
                  </td>
                </tr>
              ) : (
                filtered.map((job) => (
                  <tr key={job.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-5 py-3">
                      <Link
                        href={`/analysis/${job.id}`}
                        className="font-medium text-brand-600 hover:text-brand-700"
                      >
                        {job.index_type.toUpperCase()}
                      </Link>
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-600">
                      <Link
                        href={`/fields/${job.field_id}`}
                        className="hover:text-brand-600"
                      >
                        {fieldName(job.field_id)}
                      </Link>
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-600 font-mono truncate max-w-[200px]">
                      {job.scene_id}
                    </td>
                    <td className="px-5 py-3">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="px-5 py-3 text-sm font-mono">
                      {job.result ? formatNumber(job.result.mean) : "—"}
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-500">
                      {formatDate(job.created_at)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </AppShell>
  );
}
