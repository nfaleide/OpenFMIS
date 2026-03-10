"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppShell } from "@/components/layout/app-shell";
import { fields as fieldsApi, scenes, collections as collectionsApi, analysis } from "@/lib/api";
import { formatDate, formatNumber, cn } from "@/lib/utils";
import { Search, Satellite, Cloud, Calendar, ChevronDown, Play } from "lucide-react";
import type { Field, SceneResult, CollectionInfo } from "@/types/api";

export default function ScenesPage() {
  return (
    <Suspense>
      <ScenesContent />
    </Suspense>
  );
}

function ScenesContent() {
  const searchParams = useSearchParams();
  const preselectedFieldId = searchParams.get("field");

  const [fieldList, setFieldList] = useState<Field[]>([]);
  const [colls, setColls] = useState<CollectionInfo[]>([]);
  const [selectedFieldId, setSelectedFieldId] = useState(preselectedFieldId || "");
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date();
    d.setMonth(d.getMonth() - 3);
    return d.toISOString().slice(0, 10);
  });
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [cloudMax, setCloudMax] = useState(30);
  const [collection, setCollection] = useState("");
  const [results, setResults] = useState<SceneResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [submittingScene, setSubmittingScene] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState("ndvi");

  useEffect(() => {
    Promise.all([
      fieldsApi.list().catch(() => ({ items: [], total: 0 })),
      collectionsApi.list().catch(() => []),
    ]).then(([f, c]) => {
      setFieldList(f.items);
      setColls(c);
    });
  }, []);

  const selectedField = fieldList.find((f) => f.id === selectedFieldId);

  async function handleSearch() {
    if (!selectedField?.geometry) return;
    setSearching(true);
    setSearched(true);
    try {
      const res = await scenes.search({
        geometry: selectedField.geometry,
        date_from: dateFrom,
        date_to: dateTo,
        cloud_cover_max: cloudMax,
        collection: collection || undefined,
      });
      setResults(res);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  async function handleAnalyze(sceneId: string) {
    if (!selectedFieldId) return;
    setSubmittingScene(sceneId);
    try {
      await analysis.submit({
        field_id: selectedFieldId,
        scene_id: sceneId,
        index_type: selectedIndex,
      });
      alert("Analysis job submitted!");
    } catch (e: unknown) {
      alert(`Failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    } finally {
      setSubmittingScene(null);
    }
  }

  return (
    <AppShell>
      <div className="p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Scene Search</h1>
          <p className="text-sm text-gray-500 mt-1">
            Search satellite imagery for your fields
          </p>
        </div>

        {/* Search Form */}
        <div className="card p-5 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Field Selector */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Field
              </label>
              <select
                value={selectedFieldId}
                onChange={(e) => setSelectedFieldId(e.target.value)}
                className="input"
              >
                <option value="">Select a field...</option>
                {fieldList.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Date From */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                <Calendar className="w-3.5 h-3.5 inline mr-1" />
                From
              </label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="input"
              />
            </div>

            {/* Date To */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                <Calendar className="w-3.5 h-3.5 inline mr-1" />
                To
              </label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="input"
              />
            </div>

            {/* Cloud Cover */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                <Cloud className="w-3.5 h-3.5 inline mr-1" />
                Max Cloud Cover
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={cloudMax}
                  onChange={(e) => setCloudMax(Number(e.target.value))}
                  className="flex-1"
                />
                <span className="text-sm font-medium text-gray-700 w-10">
                  {cloudMax}%
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-end gap-4">
            {/* Collection */}
            <div className="flex-1 max-w-xs">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                <Satellite className="w-3.5 h-3.5 inline mr-1" />
                Collection
              </label>
              <select
                value={collection}
                onChange={(e) => setCollection(e.target.value)}
                className="input"
              >
                <option value="">All Collections</option>
                {colls.map((c) => (
                  <option key={c.collection_id} value={c.collection_id}>
                    {c.display_name}
                  </option>
                ))}
              </select>
            </div>

            <button
              onClick={handleSearch}
              disabled={!selectedField?.geometry || searching}
              className="btn-satshot flex items-center gap-2"
            >
              <Search className="w-4 h-4" />
              {searching ? "Searching..." : "Search Scenes"}
            </button>
          </div>

          {!selectedField?.geometry && selectedFieldId && (
            <p className="text-sm text-amber-600">
              Selected field has no geometry. Please draw a boundary first.
            </p>
          )}
        </div>

        {/* Results */}
        {searched && (
          <div className="card overflow-hidden">
            <div className="px-5 py-3 border-b border-gray-200 flex items-center justify-between">
              <h2 className="font-semibold text-gray-900">
                {searching
                  ? "Searching..."
                  : `${results.length} Scene${results.length !== 1 ? "s" : ""} Found`}
              </h2>
              {results.length > 0 && (
                <div className="flex items-center gap-2">
                  <label className="text-sm text-gray-500">Index:</label>
                  <select
                    value={selectedIndex}
                    onChange={(e) => setSelectedIndex(e.target.value)}
                    className="input text-sm py-1 px-2"
                  >
                    <option value="ndvi">NDVI</option>
                    <option value="ndwi">NDWI</option>
                    <option value="evi">EVI</option>
                    <option value="savi">SAVI</option>
                    <option value="ndre">NDRE</option>
                  </select>
                </div>
              )}
            </div>

            {results.length === 0 && !searching ? (
              <div className="p-8 text-center text-gray-400">
                No scenes found for the given criteria. Try expanding the date range or increasing cloud cover tolerance.
              </div>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="text-left text-xs font-medium text-gray-500 uppercase px-5 py-2">
                      Scene ID
                    </th>
                    <th className="text-left text-xs font-medium text-gray-500 uppercase px-5 py-2">
                      Collection
                    </th>
                    <th className="text-left text-xs font-medium text-gray-500 uppercase px-5 py-2">
                      Date
                    </th>
                    <th className="text-left text-xs font-medium text-gray-500 uppercase px-5 py-2">
                      Cloud %
                    </th>
                    <th className="text-right text-xs font-medium text-gray-500 uppercase px-5 py-2">
                      Action
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {results.map((scene) => (
                    <tr key={scene.scene_id} className="hover:bg-gray-50">
                      <td className="px-5 py-3 text-sm font-mono text-gray-900 truncate max-w-[250px]">
                        {scene.scene_id}
                      </td>
                      <td className="px-5 py-3">
                        <span
                          className={cn(
                            "badge",
                            scene.collection.includes("sentinel-1")
                              ? "bg-purple-100 text-purple-700"
                              : scene.collection.includes("sentinel-2")
                                ? "bg-satshot-100 text-satshot-700"
                                : "bg-amber-100 text-amber-700",
                          )}
                        >
                          {scene.collection}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-sm text-gray-600">
                        {formatDate(scene.acquired_at)}
                      </td>
                      <td className="px-5 py-3 text-sm">
                        <span
                          className={cn(
                            "font-medium",
                            scene.cloud_cover < 10
                              ? "text-green-600"
                              : scene.cloud_cover < 30
                                ? "text-yellow-600"
                                : "text-red-600",
                          )}
                        >
                          {formatNumber(scene.cloud_cover, 1)}%
                        </span>
                      </td>
                      <td className="px-5 py-3 text-right">
                        <button
                          onClick={() => handleAnalyze(scene.scene_id)}
                          disabled={submittingScene === scene.scene_id}
                          className="btn-satshot text-xs py-1 px-3 inline-flex items-center gap-1"
                        >
                          <Play className="w-3 h-3" />
                          {submittingScene === scene.scene_id
                            ? "Submitting..."
                            : "Analyze"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
