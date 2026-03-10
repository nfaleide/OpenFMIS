export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  group_id: string | null;
  created_at: string;
}

export interface Group {
  id: string;
  name: string;
  description: string | null;
  parent_id: string | null;
  created_at: string;
}

export interface Field {
  id: string;
  name: string;
  description: string | null;
  area_acres: number | null;
  group_id: string;
  created_by: string;
  version: number;
  is_current: boolean;
  geometry?: GeoJSON.MultiPolygon | null;
  created_at: string;
  updated_at: string;
}

export interface FieldListResponse {
  items: Field[];
  total: number;
}

export interface SceneSearchParams {
  geometry: GeoJSON.Geometry;
  date_from: string;
  date_to: string;
  cloud_cover_max: number;
  collection?: string;
  collections?: string[];
}

export interface SceneResult {
  scene_id: string;
  collection: string;
  acquired_at: string;
  cloud_cover: number;
  bbox: number[];
  assets: Record<string, string>;
}

export interface AnalysisJob {
  id: string;
  field_id: string;
  scene_id: string;
  index_type: string;
  status: "pending" | "running" | "complete" | "failed";
  result: AnalysisResult | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface AnalysisResult {
  mean: number | null;
  min: number | null;
  max: number | null;
  std: number | null;
  median?: number | null;
  p10?: number | null;
  p90?: number | null;
  pixel_count: number;
  valid_pixel_count: number;
  nodata_fraction: number;
}

export interface JobListResponse {
  items: AnalysisJob[];
  total: number;
}

export interface SpectralIndex {
  slug: string;
  display_name: string;
  formula: string;
  required_bands: string[];
  category: string;
  is_builtin: boolean;
}

export interface CollectionInfo {
  collection_id: string;
  display_name: string;
  sensor_type: string;
  available_bands: string[];
  description: string;
}

export interface BatchAnalysis {
  id: string;
  field_ids: string[];
  scene_id: string;
  index_type: string;
  status: string;
  job_ids: string[];
  summary: Record<string, unknown> | null;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}
