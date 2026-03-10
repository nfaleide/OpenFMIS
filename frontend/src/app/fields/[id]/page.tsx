"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { FieldMap } from "@/components/map/field-map";
import { StatusBadge } from "@/components/ui/status-badge";
import { fields as fieldsApi, analysis } from "@/lib/api";
import { formatAcres, formatDate, formatNumber } from "@/lib/utils";
import { ArrowLeft, Satellite, BarChart3 } from "lucide-react";
import type { Field, AnalysisJob } from "@/types/api";

export default function FieldDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [field, setField] = useState<Field | null>(null);
  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    Promise.all([
      fieldsApi.get(id),
      analysis.list(id).catch(() => ({ items: [], total: 0 })),
    ]).then(([f, j]) => {
      setField(f);
      setJobs(j.items);
      setLoading(false);
    });
  }, [id]);

  if (loading) {
    return (
      <AppShell>
        <div className="p-6 text-gray-400">Loading field...</div>
      </AppShell>
    );
  }

  if (!field) {
    return (
      <AppShell>
        <div className="p-6 text-red-600">Field not found.</div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center gap-4">
          <Link
            href="/fields"
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-gray-600" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{field.name}</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              {formatAcres(field.area_acres)} &middot; Version {field.version}{" "}
              &middot; Created {formatDate(field.created_at)}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Map */}
          <div className="lg:col-span-2 card overflow-hidden">
            <FieldMap
              fields={[field]}
              selectedFieldId={field.id}
              className="h-[500px]"
            />
          </div>

          {/* Actions Panel */}
          <div className="space-y-4">
            <div className="card p-5 space-y-3">
              <h3 className="font-semibold text-gray-900">Quick Actions</h3>
              <Link
                href={`/scenes?field=${field.id}`}
                className="btn-satshot flex items-center gap-2 w-full justify-center"
              >
                <Satellite className="w-4 h-4" />
                Search Scenes
              </Link>
              <Link
                href={`/analysis?field=${field.id}`}
                className="btn-secondary flex items-center gap-2 w-full justify-center"
              >
                <BarChart3 className="w-4 h-4" />
                View Analysis
              </Link>
            </div>

            {/* Field Info */}
            <div className="card p-5">
              <h3 className="font-semibold text-gray-900 mb-3">Details</h3>
              <dl className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-gray-500">Area</dt>
                  <dd className="font-medium">{formatAcres(field.area_acres)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-gray-500">Version</dt>
                  <dd className="font-medium">{field.version}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-gray-500">Has Geometry</dt>
                  <dd className="font-medium">{field.geometry ? "Yes" : "No"}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-gray-500">Analysis Jobs</dt>
                  <dd className="font-medium">{jobs.length}</dd>
                </div>
              </dl>
            </div>
          </div>
        </div>

        {/* Analysis History */}
        {jobs.length > 0 && (
          <div className="card overflow-hidden">
            <div className="px-5 py-3 border-b border-gray-200">
              <h2 className="font-semibold text-gray-900">Analysis History</h2>
            </div>
            <table className="w-full">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left text-xs font-medium text-gray-500 uppercase px-5 py-2">
                    Index
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase px-5 py-2">
                    Scene
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase px-5 py-2">
                    Status
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase px-5 py-2">
                    Mean
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase px-5 py-2">
                    Date
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {jobs.map((job) => (
                  <tr key={job.id} className="hover:bg-gray-50">
                    <td className="px-5 py-3">
                      <Link
                        href={`/analysis/${job.id}`}
                        className="font-medium text-brand-600 hover:text-brand-700"
                      >
                        {job.index_type.toUpperCase()}
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
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
}
