"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { FieldMap } from "@/components/map/field-map";
import { StatCard } from "@/components/ui/stat-card";
import { fields as fieldsApi, groups as groupsApi } from "@/lib/api";
import { formatAcres } from "@/lib/utils";
import { Map, Users } from "lucide-react";
import Link from "next/link";
import type { Field, Group } from "@/types/api";

export default function DashboardPage() {
  const [fieldList, setFieldList] = useState<Field[]>([]);
  const [groupList, setGroupList] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fieldsApi.list().catch(() => ({ items: [], total: 0 })),
      groupsApi.list().catch(() => []),
    ]).then(([f, g]) => {
      setFieldList(f.items);
      setGroupList(g);
      setLoading(false);
    });
  }, []);

  const totalAcres = fieldList.reduce(
    (sum, f) => sum + (f.area_acres || 0),
    0,
  );

  return (
    <AppShell>
      <div className="p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">
            OpenFMIS overview
          </p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <StatCard
            label="Total Fields"
            value={loading ? "..." : fieldList.length}
            icon={<Map className="w-5 h-5" />}
          />
          <StatCard
            label="Total Area"
            value={loading ? "..." : formatAcres(totalAcres)}
            icon={<Map className="w-5 h-5" />}
          />
          <StatCard
            label="Groups"
            value={loading ? "..." : groupList.length}
            icon={<Users className="w-5 h-5" />}
          />
        </div>

        {/* Map */}
        <div className="card overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-200 flex items-center justify-between">
            <h2 className="font-semibold text-gray-900">Field Map</h2>
            <Link href="/fields" className="text-sm text-brand-600 hover:text-brand-700">
              View all
            </Link>
          </div>
          <FieldMap fields={fieldList} className="h-[500px]" />
        </div>
      </div>
    </AppShell>
  );
}
