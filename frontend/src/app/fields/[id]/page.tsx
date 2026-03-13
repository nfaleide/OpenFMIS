"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { FieldMap } from "@/components/map/field-map";
import { fields as fieldsApi } from "@/lib/api";
import { formatAcres, formatDate } from "@/lib/utils";
import { ArrowLeft } from "lucide-react";
import type { Field } from "@/types/api";

export default function FieldDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [field, setField] = useState<Field | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    fieldsApi
      .get(id)
      .then(setField)
      .catch(() => {})
      .finally(() => setLoading(false));
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
                <dt className="text-gray-500">Created</dt>
                <dd className="font-medium">{formatDate(field.created_at)}</dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
