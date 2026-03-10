"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  fields as fieldsApi,
  scenes,
  batch,
  collections as collectionsApi,
} from "@/lib/api";
import { formatDate, formatNumber } from "@/lib/utils";
import { Layers, Play, CheckSquare, Square } from "lucide-react";
import type { Field, BatchAnalysis, CollectionInfo, SceneResult } from "@/types/api";

export default function BatchAnalysisPage() {
  const [fieldList, setFieldList] = useState<Field[]>([]);
  const [colls, setColls] = useState<CollectionInfo[]>([]);
  const [batches, setBatches] = useState<BatchAnalysis[]>([]);
  const [loading, setLoading] = useState(true);

  // Form state
  const [selectedFields, setSelectedFields] = useState<Set<string>>(new Set());
  const [sceneId, setSceneId] = useState("");
  const [indexType, setIndexType] = useState("ndvi");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    Promise.all([
      fieldsApi.list().catch(() => ({ items: [], total: 0 })),
      collectionsApi.list().catch(() => []),
      batch.list().catch(() => []),
    ]).then(([f, c, b]) => {
      setFieldList(f.items);
      setColls(c);
      setBatches(b);
      setLoading(false);
    });
  }, []);

  function toggleField(id: string) {
    setSelectedFields((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll() {
    if (selectedFields.size === fieldList.length) {
      setSelectedFields(new Set());
    } else {
      setSelectedFields(new Set(fieldList.map((f) => f.id)));
    }
  }

  async function handleSubmit() {
    if (selectedFields.size === 0 || !sceneId.trim()) return;
    setSubmitting(true);
    try {
      const result = await batch.create({
        field_ids: Array.from(selectedFields),
        scene_id: sceneId.trim(),
        index_type: indexType,
      });
      setBatches((prev) => [result, ...prev]);
      setSelectedFields(new Set());
      setSceneId("");
    } catch (e: unknown) {
      alert(`Failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell>
      <div className="p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Batch Analysis
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Run analysis across multiple fields simultaneously
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Field Selection */}
          <div className="lg:col-span-2 card overflow-hidden">
            <div className="px-5 py-3 border-b border-gray-200 flex items-center justify-between">
              <h2 className="font-semibold text-gray-900">
                Select Fields ({selectedFields.size} of {fieldList.length})
              </h2>
              <button
                onClick={selectAll}
                className="text-sm text-brand-600 hover:text-brand-700"
              >
                {selectedFields.size === fieldList.length
                  ? "Deselect All"
                  : "Select All"}
              </button>
            </div>
            <div className="max-h-[400px] overflow-y-auto">
              {loading ? (
                <div className="p-8 text-center text-gray-400">
                  Loading fields...
                </div>
              ) : fieldList.length === 0 ? (
                <div className="p-8 text-center text-gray-400">
                  No fields available.
                </div>
              ) : (
                fieldList.map((field) => (
                  <button
                    key={field.id}
                    onClick={() => toggleField(field.id)}
                    className="w-full flex items-center gap-3 px-5 py-3 hover:bg-gray-50 transition-colors text-left border-b border-gray-50"
                  >
                    {selectedFields.has(field.id) ? (
                      <CheckSquare className="w-4 h-4 text-brand-600 flex-shrink-0" />
                    ) : (
                      <Square className="w-4 h-4 text-gray-300 flex-shrink-0" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-gray-900 truncate">
                        {field.name}
                      </div>
                      <div className="text-xs text-gray-500">
                        {field.area_acres
                          ? `${formatNumber(field.area_acres, 1)} ac`
                          : "No area"}
                      </div>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* Submit Panel */}
          <div className="space-y-4">
            <div className="card p-5 space-y-4">
              <h3 className="font-semibold text-gray-900">
                Analysis Parameters
              </h3>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Scene ID
                </label>
                <input
                  type="text"
                  placeholder="e.g. S2A_MSIL2A_20240301..."
                  value={sceneId}
                  onChange={(e) => setSceneId(e.target.value)}
                  className="input text-sm font-mono"
                />
                <p className="text-xs text-gray-400 mt-1">
                  Paste a scene ID from the Scene Search page
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Spectral Index
                </label>
                <select
                  value={indexType}
                  onChange={(e) => setIndexType(e.target.value)}
                  className="input"
                >
                  <option value="ndvi">NDVI</option>
                  <option value="ndwi">NDWI</option>
                  <option value="evi">EVI</option>
                  <option value="savi">SAVI</option>
                  <option value="ndre">NDRE</option>
                </select>
              </div>

              <button
                onClick={handleSubmit}
                disabled={
                  selectedFields.size === 0 || !sceneId.trim() || submitting
                }
                className="btn-satshot w-full flex items-center justify-center gap-2"
              >
                <Layers className="w-4 h-4" />
                {submitting
                  ? "Submitting..."
                  : `Analyze ${selectedFields.size} Field${selectedFields.size !== 1 ? "s" : ""}`}
              </button>
            </div>

            <div className="card p-5">
              <h3 className="font-semibold text-gray-900 mb-2">How it works</h3>
              <ol className="text-sm text-gray-600 space-y-2 list-decimal list-inside">
                <li>Select one or more fields</li>
                <li>Enter a scene ID from a satellite search</li>
                <li>Choose a spectral index</li>
                <li>Each field gets its own analysis job</li>
              </ol>
            </div>
          </div>
        </div>

        {/* Batch History */}
        {batches.length > 0 && (
          <div className="card overflow-hidden">
            <div className="px-5 py-3 border-b border-gray-200">
              <h2 className="font-semibold text-gray-900">Batch History</h2>
            </div>
            <table className="w-full">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left text-xs font-medium text-gray-500 uppercase px-5 py-2">
                    Index
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase px-5 py-2">
                    Fields
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase px-5 py-2">
                    Scene
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase px-5 py-2">
                    Status
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase px-5 py-2">
                    Date
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {batches.map((b) => (
                  <tr key={b.id} className="hover:bg-gray-50">
                    <td className="px-5 py-3 font-medium text-gray-900">
                      {b.index_type.toUpperCase()}
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-600">
                      {b.field_ids.length} fields
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-600 font-mono truncate max-w-[200px]">
                      {b.scene_id}
                    </td>
                    <td className="px-5 py-3">
                      <StatusBadge status={b.status} />
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-500">
                      {formatDate(b.created_at)}
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
