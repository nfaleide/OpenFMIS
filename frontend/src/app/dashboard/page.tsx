"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { FieldMap } from "@/components/map/field-map";
import { StatCard } from "@/components/ui/stat-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { fields as fieldsApi, analysis, indices, collections as collectionsApi } from "@/lib/api";
import { formatDate, formatNumber } from "@/lib/utils";
import { Map, BarChart3, Satellite, Layers } from "lucide-react";
import Link from "next/link";
import type { Field, AnalysisJob, SpectralIndex, CollectionInfo } from "@/types/api";

export default function DashboardPage() {
  const [fieldList, setFieldList] = useState<Field[]>([]);
  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [indexList, setIndexList] = useState<SpectralIndex[]>([]);
  const [colls, setColls] = useState<CollectionInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fieldsApi.list().catch(() => ({ items: [], total: 0 })),
      analysis.list().catch(() => ({ items: [], total: 0 })),
      indices.list().catch(() => []),
      collectionsApi.list().catch(() => []),
    ]).then(([f, j, idx, c]) => {
      setFieldList(f.items);
      setJobs(j.items);
      setIndexList(idx);
      setColls(c);
      setLoading(false);
    });
  }, []);

  const recentJobs = jobs.slice(0, 5);

  return (
    <AppShell>
      <div className="p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">
            OpenFMIS overview with Satshot imagery plugin
          </p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Total Fields"
            value={loading ? "..." : fieldList.length}
            icon={<Map className="w-5 h-5" />}
          />
          <StatCard
            label="Analysis Jobs"
            value={loading ? "..." : jobs.length}
            icon={<BarChart3 className="w-5 h-5" />}
          />
          <StatCard
            label="Spectral Indices"
            value={loading ? "..." : indexList.length}
            icon={<Layers className="w-5 h-5" />}
          />
          <StatCard
            label="Data Sources"
            value={loading ? "..." : colls.length}
            icon={<Satellite className="w-5 h-5" />}
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Map */}
          <div className="lg:col-span-2">
            <div className="card overflow-hidden">
              <div className="px-5 py-3 border-b border-gray-200 flex items-center justify-between">
                <h2 className="font-semibold text-gray-900">Field Map</h2>
                <Link href="/fields" className="text-sm text-brand-600 hover:text-brand-700">
                  View all
                </Link>
              </div>
              <FieldMap fields={fieldList} className="h-[400px]" />
            </div>
          </div>

          {/* Recent Analysis */}
          <div className="card">
            <div className="px-5 py-3 border-b border-gray-200 flex items-center justify-between">
              <h2 className="font-semibold text-gray-900">Recent Analysis</h2>
              <Link href="/analysis" className="text-sm text-brand-600 hover:text-brand-700">
                View all
              </Link>
            </div>
            <div className="divide-y divide-gray-100">
              {loading ? (
                <div className="p-8 text-center text-gray-400">Loading...</div>
              ) : recentJobs.length === 0 ? (
                <div className="p-8 text-center text-gray-400">
                  No analysis jobs yet.
                  <br />
                  <Link href="/scenes" className="text-brand-600 text-sm">
                    Search for scenes to get started
                  </Link>
                </div>
              ) : (
                recentJobs.map((job) => (
                  <Link
                    key={job.id}
                    href={`/analysis/${job.id}`}
                    className="flex items-center justify-between px-5 py-3 hover:bg-gray-50 transition-colors"
                  >
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-gray-900 truncate">
                        {job.index_type.toUpperCase()}
                      </div>
                      <div className="text-xs text-gray-500 truncate">
                        {job.scene_id}
                      </div>
                    </div>
                    <div className="flex items-center gap-3 flex-shrink-0">
                      {job.result && (
                        <span className="text-sm font-mono text-gray-700">
                          {formatNumber(job.result.mean)}
                        </span>
                      )}
                      <StatusBadge status={job.status} />
                    </div>
                  </Link>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Data Sources */}
        <div className="card">
          <div className="px-5 py-3 border-b border-gray-200">
            <div className="flex items-center gap-2">
              <Satellite className="w-4 h-4 text-satshot-500" />
              <h2 className="font-semibold text-gray-900">
                Satshot Data Sources
              </h2>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-gray-200">
            {colls.map((c) => (
              <div key={c.collection_id} className="p-5">
                <div className="flex items-center gap-2">
                  <span className={`badge ${c.sensor_type === "sar" ? "bg-purple-100 text-purple-700" : "bg-satshot-100 text-satshot-700"}`}>
                    {c.sensor_type}
                  </span>
                  <h3 className="font-medium text-gray-900">
                    {c.display_name}
                  </h3>
                </div>
                <p className="text-xs text-gray-500 mt-2">{c.description}</p>
                <div className="flex flex-wrap gap-1 mt-3">
                  {c.available_bands.slice(0, 6).map((b) => (
                    <span
                      key={b}
                      className="badge bg-gray-100 text-gray-600"
                    >
                      {b}
                    </span>
                  ))}
                  {c.available_bands.length > 6 && (
                    <span className="badge bg-gray-100 text-gray-600">
                      +{c.available_bands.length - 6}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
