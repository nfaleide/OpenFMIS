"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { FieldMap } from "@/components/map/field-map";
import { fields as fieldsApi, groups as groupsApi } from "@/lib/api";
import { formatAcres, formatDate } from "@/lib/utils";
import { Plus, MapPin, Search } from "lucide-react";
import type { Field, Group } from "@/types/api";

export default function FieldsPage() {
  const [fieldList, setFieldList] = useState<Field[]>([]);
  const [groupList, setGroupList] = useState<Group[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<string>("");
  const [selectedField, setSelectedField] = useState<Field | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    groupsApi.list().then(setGroupList).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    fieldsApi
      .list(selectedGroup || undefined)
      .then((r) => setFieldList(r.items))
      .catch(() => setFieldList([]))
      .finally(() => setLoading(false));
  }, [selectedGroup]);

  const filtered = fieldList.filter((f) =>
    f.name.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <AppShell>
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Fields</h1>
            <p className="text-sm text-gray-500 mt-1">
              {fieldList.length} fields across {groupList.length} groups
            </p>
          </div>
          <button className="btn-primary flex items-center gap-2">
            <Plus className="w-4 h-4" />
            Add Field
          </button>
        </div>

        {/* Map */}
        <div className="card overflow-hidden">
          <FieldMap
            fields={filtered}
            selectedFieldId={selectedField?.id}
            onFieldClick={setSelectedField}
            className="h-[400px]"
          />
        </div>

        {/* Filters */}
        <div className="flex gap-3">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search fields..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="input pl-9"
            />
          </div>
          <select
            value={selectedGroup}
            onChange={(e) => setSelectedGroup(e.target.value)}
            className="input max-w-xs"
          >
            <option value="">All Groups</option>
            {groupList.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </div>

        {/* Field List */}
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-5 py-3">
                  Name
                </th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-5 py-3">
                  Area
                </th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-5 py-3">
                  Version
                </th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-5 py-3">
                  Created
                </th>
                <th className="text-right text-xs font-medium text-gray-500 uppercase tracking-wider px-5 py-3">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-gray-400">
                    Loading fields...
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-gray-400">
                    No fields found.
                  </td>
                </tr>
              ) : (
                filtered.map((field) => (
                  <tr
                    key={field.id}
                    className={`hover:bg-gray-50 transition-colors cursor-pointer ${
                      field.id === selectedField?.id ? "bg-brand-50" : ""
                    }`}
                    onClick={() => setSelectedField(field)}
                  >
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <MapPin className="w-4 h-4 text-gray-400" />
                        <Link
                          href={`/fields/${field.id}`}
                          className="font-medium text-gray-900 hover:text-brand-600"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {field.name}
                        </Link>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-600">
                      {formatAcres(field.area_acres)}
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-600">
                      v{field.version}
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-500">
                      {formatDate(field.created_at)}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <Link
                        href={`/fields/${field.id}`}
                        className="text-sm text-brand-600 hover:text-brand-700"
                        onClick={(e) => e.stopPropagation()}
                      >
                        View
                      </Link>
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
