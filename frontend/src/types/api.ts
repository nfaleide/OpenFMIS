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

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}
