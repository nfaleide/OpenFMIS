# API Reference

Base URL: `/api/v1`

All endpoints require `Authorization: Bearer <token>` unless marked **Public**.

## Health

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/health` | Health check | Public |
| GET | `/health/ready` | Readiness probe | Public |

## Authentication

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| POST | `/login` | Login (username + password → tokens) | Public |
| POST | `/refresh` | Refresh token pair | Public |
| POST | `/logout` | Revoke access token | Required |
| GET | `/me` | Current user profile | Required |
| GET | `/auth/sessions` | List active sessions | Required |
| POST | `/auth/api-keys` | Create API key | Required |
| GET | `/auth/api-keys` | List API keys | Required |
| DELETE | `/auth/api-keys/{key_id}` | Revoke API key | Required |

## Users

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/users` | List users | Required |
| GET | `/users/{user_id}` | Get user | Required |
| POST | `/users` | Create user | Required |
| PATCH | `/users/{user_id}` | Update user | Required |
| POST | `/users/{user_id}/change-password` | Change password | Required |
| DELETE | `/users/{user_id}` | Delete user | Required |

## Groups

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/groups` | List groups | Required |
| GET | `/groups/tree` | Get group tree | Required |
| GET | `/groups/{group_id}` | Get group detail | Required |
| GET | `/groups/{group_id}/ancestors` | Get group ancestors | Required |
| GET | `/groups/{group_id}/descendants` | Get group descendants | Required |
| POST | `/groups` | Create group | change_group_settings |
| PATCH | `/groups/{group_id}` | Update group | change_group_settings |
| DELETE | `/groups/{group_id}` | Delete group | change_group_settings |

## ACL (Access Control)

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/acl/check` | Check single permission | Required |
| GET | `/acl/effective` | Get effective permissions on resource | Required |
| GET | `/acl/users/{user_id}/privileges` | List user privileges | Required |
| POST | `/acl/users/{user_id}/privileges` | Grant user privilege | change_object_acls |
| DELETE | `/acl/users/{user_id}/privileges` | Revoke user privilege | change_object_acls |
| GET | `/acl/groups/{group_id}/privileges` | List group privileges | Required |
| POST | `/acl/groups/{group_id}/privileges` | Grant group privilege | change_object_acls |
| DELETE | `/acl/groups/{group_id}/privileges` | Revoke group privilege | change_object_acls |

## Fields

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/fields` | List fields | fields.read |
| GET | `/fields/{field_id}` | Get field detail | fields.read |
| GET | `/fields/{field_id}/versions` | Get version history | fields.read |
| POST | `/fields` | Create field | fields.create |
| PATCH | `/fields/{field_id}` | Update field attributes | fields.modify |
| PUT | `/fields/{field_id}/geometry` | Update geometry (creates new version) | fields.modify |
| POST | `/fields/batch-rename` | Batch rename fields | fields.modify |
| DELETE | `/fields/{field_id}` | Soft delete field | fields.delete |

## Boundary Versions

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/boundary-versions` | List boundary versions | Required |
| GET | `/boundary-versions/{version_id}` | Get boundary version | Required |
| POST | `/boundary-versions` | Create boundary version | Required |

## Crop Years

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/crop-years` | List crop years (by field) | Required |
| GET | `/crop-years/{crop_year_id}` | Get crop year | Required |
| POST | `/crop-years` | Create crop year | Required |
| PATCH | `/crop-years/{crop_year_id}` | Update crop year | Required |
| DELETE | `/crop-years/{crop_year_id}` | Delete crop year | Required |

## Field Events

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/field-events` | List events | fielddata.read |
| GET | `/field-events/{event_id}` | Get event | fielddata.read |
| GET | `/field-events/{event_id}/versions` | Get event version history | fielddata.read |
| GET | `/field-events/{event_id}/history` | Get event audit history | fielddata.read |
| POST | `/field-events` | Create event | fielddata.append |
| PATCH | `/field-events/{event_id}` | Update event | fielddata.modify |
| POST | `/field-events/{event_id}/versions` | Create new version | fielddata.modify |
| DELETE | `/field-events/{event_id}` | Delete event | fielddata.modify |
| POST | `/field-events/{event_id}/entries` | Add entry | fielddata.modify |
| DELETE | `/field-events/entries/{entry_id}` | Remove entry | fielddata.modify |

**Event Types**: `crop_protection`, `fertilizing`, `harvest`, `irrigation`, `insurance`, `planting`, `scouting`, `soil_testing`, `tillage`

## Geometry Operations

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| POST | `/geometry/validate` | Validate GeoJSON geometry | Required |
| POST | `/geometry/area` | Calculate area (acres + sq meters) | Required |
| POST | `/geometry/bbox` | Calculate bounding box | Required |
| POST | `/geometry/type` | Get geometry type | Required |
| POST | `/geometry/centroid` | Get centroid | Required |
| POST | `/geometry/union` | Union multiple geometries | Required |
| POST | `/geometry/clip` | Clip geometry | Required |
| POST | `/geometry/hole` | Cut hole in geometry | Required |
| POST | `/geometry/buffer` | Buffer geometry | Required |
| POST | `/geometry/intersections` | Find field intersections | Required |

## Regions

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/regions` | List regions | regions.read |
| GET | `/regions/accessible` | Get accessible set | Required |
| GET | `/regions/mine` | List my regions | Required |
| GET | `/regions/visible` | List visible regions | Required |
| GET | `/regions/{region_id}` | Get region detail | regions.read |
| POST | `/regions` | Create region | regions.create |
| PATCH | `/regions/{region_id}` | Update region | regions.modify |
| DELETE | `/regions/{region_id}` | Delete region | regions.delete |
| POST | `/regions/{region_id}/members` | Add field members | regions.modify |
| DELETE | `/regions/{region_id}/members` | Remove field members | regions.modify |
| GET | `/regions/{region_id}/fields` | List region fields | regions.read |

## Equipment

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/equipment` | List equipment | Required |
| GET | `/equipment/{equip_id}` | Get equipment | Required |
| POST | `/equipment` | Create equipment | change_group_settings |
| PATCH | `/equipment/{equip_id}` | Update equipment | change_group_settings |
| DELETE | `/equipment/{equip_id}` | Delete equipment | change_group_settings |

## Photos

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/photos` | List photos | fields.read |
| GET | `/photos/{photo_id}` | Get photo | fields.read |
| POST | `/photos` | Create photo | fields.modify |
| PATCH | `/photos/{photo_id}` | Update photo | fields.modify |
| DELETE | `/photos/{photo_id}` | Delete photo | fields.modify |

## Preferences

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/preferences` | List all preferences | Required |
| GET | `/preferences/{namespace}` | Get preference by namespace | Required |
| PUT | `/preferences` | Upsert preference | Required |
| DELETE | `/preferences/{namespace}` | Delete preference | Required |

## Logos

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/logos/{group_id}` | Get group logo | Required |
| PUT | `/logos` | Upsert logo | Required |
| DELETE | `/logos/{group_id}` | Delete logo | Required |

## Import

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| POST | `/import/vector` | Import vector file (Shapefile, GeoJSON, KML) | Required |
| POST | `/import/modus` | Import MODUS XML | Required |
| POST | `/import/sst-package` | Import SST package | Required |
| POST | `/import/isoxml` | Import ISOXML | Required |

## Export

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/export/geojson` | Export as GeoJSON | Required |
| GET | `/export/shapefile` | Export as Shapefile (ZIP) | Required |
| GET | `/export/kml` | Export as KML | Required |
| GET | `/export/csv` | Export as CSV | Required |
| POST | `/export/links` | Create shareable download link | Required |
| GET | `/export/links/{link_hash}` | Download via link | Public (hash auth) |

## PLSS

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/plss/states` | List PLSS states | Required |
| GET | `/plss/fips` | Get FIPS for state | Required |
| GET | `/plss/townships` | Search townships | Required |
| GET | `/plss/townships/{township_id}` | Get township | Required |
| GET | `/plss/townships/{township_id}/sections` | Get sections | Required |
| GET | `/plss/sections` | Search sections | Required |
| GET | `/plss/sections/{section_id}` | Get section | Required |
| GET | `/plss/at-point` | PLSS at lat/lon | Required |

## CLU

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/clu/states` | List CLU states | Required |
| GET | `/clu/county/{state}/{county_fips}` | Get CLUs by county | Required |
| GET | `/clu/at-point` | Get CLUs at lat/lon | Required |
| POST | `/clu/intersecting` | Get CLUs intersecting geometry | Required |
| GET | `/clu/fields/{field_id}` | Get CLUs for field | Required |

## Boundaries (Geodata Proxy)

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/boundaries/clus/bbox` | CLUs in bounding box | Public |
| GET | `/boundaries/plss/states` | PLSS state list | Public |
| GET | `/boundaries/plss/counties` | PLSS county list | Public |
| GET | `/boundaries/plss/townships/bbox` | Townships in bbox | Public |
| GET | `/boundaries/plss/townships/search` | Search townships | Public |
| GET | `/boundaries/plss/townships/{township_id}` | Township detail | Public |
| GET | `/boundaries/plss/townships/{township_id}/sections` | Township sections | Public |
| GET | `/boundaries/plss/sections/bbox` | Sections in bbox | Public |
| GET | `/boundaries/plss/sections/{section_id}` | Section detail | Public |

## Plugins

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/plugins` | List plugins | Required |
| GET | `/plugins/{slug}` | Get plugin | Required |
| POST | `/plugins` | Register plugin | Superuser |
| PATCH | `/plugins/{slug}` | Update plugin | Superuser |
| POST | `/plugins/{slug}/activate` | Activate plugin | Superuser |
| POST | `/plugins/{slug}/deactivate` | Deactivate plugin | Superuser |
| DELETE | `/plugins/{slug}` | Unregister plugin | Superuser |

## Datasets (Plugin)

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| POST | `/datasets` | Create dataset | fielddata.append |
| GET | `/datasets` | List datasets (by field) | fielddata.read |
| GET | `/datasets/{dataset_id}` | Get dataset | fielddata.read |
| DELETE | `/datasets/{dataset_id}` | Delete dataset | fielddata.modify |

## Point Datasets

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/point-datasets` | List point datasets | Required |
| GET | `/point-datasets/{dataset_id}` | Get point dataset | Required |
| POST | `/point-datasets` | Create point dataset | Required |
| PATCH | `/point-datasets/{dataset_id}` | Update point dataset | Required |
| DELETE | `/point-datasets/{dataset_id}` | Delete point dataset | Required |
| GET | `/point-datasets/{dataset_id}/cleaning-log` | Get cleaning log | Required |
| POST | `/point-datasets/{dataset_id}/cleaning-log` | Add cleaning step | Required |

## Point Ingestion

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| POST | `/point-ingestion/preview` | Preview uploaded file | Required |
| POST | `/point-ingestion/upload` | Upload point data file | Required |
| POST | `/point-ingestion/structured` | Structured intake (GeoJSON features) | Required |
| POST | `/point-ingestion/validate` | Validate data values | Required |

## Prescriptions

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/prescriptions/surfaces` | List interpolation surfaces | Required |
| GET | `/prescriptions/surfaces/{surface_id}` | Get surface | Required |
| POST | `/prescriptions/surfaces` | Create surface | Required |
| GET | `/prescriptions` | List prescriptions | Required |
| GET | `/prescriptions/{prescription_id}` | Get prescription | Required |
| POST | `/prescriptions` | Create prescription | Required |
| PATCH | `/prescriptions/{prescription_id}` | Update prescription | Required |
| DELETE | `/prescriptions/{prescription_id}` | Delete prescription | Required |

## Sampling

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| POST | `/sampling/plans` | Create sampling plan | Required |
| GET | `/sampling/plans` | List plans | Required |
| GET | `/sampling/plans/{plan_id}` | Get plan | Required |
| PATCH | `/sampling/plans/{plan_id}` | Update plan | Required |
| DELETE | `/sampling/plans/{plan_id}` | Delete plan | Required |
| POST | `/sampling/plans/{plan_id}/regenerate` | Regenerate sample points | Required |
| POST | `/sampling/plans/{plan_id}/points/{point_index}/complete` | Mark point completed | Required |
| GET | `/sampling/plans/{plan_id}/export` | Export plan (GeoJSON) | Required |
| GET | `/sampling/plans/{plan_id}/modus-submit` | Export as MODUS submit | Required |

## ADAPT Map

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/adapt-map` | List mappings | Required |
| GET | `/adapt-map/{map_id}` | Get mapping | Required |
| GET | `/adapt-map/lookup/{internal_type}/{internal_id}` | Lookup mapping | Required |
| POST | `/adapt-map` | Create mapping | Required |
| PUT | `/adapt-map` | Upsert mapping | Required |
| DELETE | `/adapt-map/{map_id}` | Delete mapping | Required |
| GET | `/adapt-map/export/{group_id}` | Export ADAPT mappings | Required |
| POST | `/adapt-map/import` | Import ADAPT mappings | Required |

## Sync

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| POST | `/sync/register` | Register sync client | Required |
| GET | `/sync/status` | Get sync status | Required |
| POST | `/sync/push` | Push changes to server | Required |
| POST | `/sync/pull` | Pull changes from server | Required |
| GET | `/sync/conflicts` | List conflicts | Required |
| POST | `/sync/conflicts/{conflict_id}/resolve` | Resolve conflict | Required |

## Billing

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/billing/accounts/{owner_type}/{owner_id}` | Get account | view_financials |
| GET | `/billing/accounts/{owner_type}/{owner_id}/ledger` | Get ledger | view_financials |
| POST | `/billing/accounts/{owner_type}/{owner_id}/credits` | Add credits | Superuser |
| POST | `/billing/accounts/{owner_type}/{owner_id}/consume` | Consume credits | make_payments |
| POST | `/billing/accounts/{owner_type}/{owner_id}/refund` | Refund credits | Superuser |
| POST | `/billing/accounts/{owner_type}/{owner_id}/reconcile` | Reconcile account | Superuser |
| GET | `/billing/transactions` | List all transactions | Superuser |
| POST | `/billing/balances` | Batch balance lookup | Superuser |
| GET | `/billing/prices` | List price catalog | view_financials |
| GET | `/billing/prices/{operation}` | Get price | view_financials |
| PUT | `/billing/prices/{operation}` | Set price | Superuser |
| DELETE | `/billing/prices/{operation}` | Deactivate price | Superuser |
| GET | `/billing/charge-types` | List charge types | Required |

## Tiles

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/tiles/layers` | List available layers | Required |
| GET | `/tiles/{layer}/{z}/{x}/{y}.mvt` | Get vector tile | Required |

**Core layers**: `fields`, `clu`, `plss_townships`, `plss_sections`
**Plugin layers**: Any registered via `register_tile_layer()`

## Email Config

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/satshot/email-config/` | Get email config | Required |
| PUT | `/satshot/email-config/` | Update email config | Required |
| POST | `/satshot/email-config/test` | Send test email | Required |

## Highlights

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/highlights` | Get highlights | Required |
| POST | `/highlights` | Add highlights | Required |
| DELETE | `/highlights` | Remove highlights | Required |
| DELETE | `/highlights/all` | Clear all highlights | Required |
| POST | `/highlights/merge` | Merge highlights | Required |
| POST | `/highlights/clip` | Clip highlights | Required |
| POST | `/highlights/hole` | Cut hole in highlights | Required |

## Reference Data

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/reference/crop-types` | List crop types | Required |
| GET | `/reference/fcic-crops` | List FCIC crop codes | Required |
| GET | `/reference/tillage-types` | List tillage types | Required |
| GET | `/reference/units` | List measurement units | Required |

## Subscriptions

| Method | Path | Summary | Auth |
|--------|------|---------|------|
| POST | `/subscriptions` | Start subscription | Required |
| GET | `/subscriptions/{subscription_id}` | Get subscription | Required |
| GET | `/subscriptions` | List subscriptions | Required |
| POST | `/subscriptions/{subscription_id}/renew` | Renew subscription | Required |
| POST | `/subscriptions/{subscription_id}/cancel` | Cancel subscription | Required |
| POST | `/subscriptions/expire-due` | Expire due subscriptions | Superuser |

---

**Total: 206 endpoints across 34 domains**
