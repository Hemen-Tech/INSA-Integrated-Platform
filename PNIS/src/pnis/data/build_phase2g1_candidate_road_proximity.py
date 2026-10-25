from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import sys
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[3]
P = ROOT / 'data' / 'processed'
CANDIDATES = P / 'phase2f5_verification_evidence_register.csv'
SPATIAL = P / 'phase2f2_osm_facility_candidates_spatially_classified_v1.csv'
ROADS = P / 'phase2c_v2_sidama_buffered_roads.gpkg'
ROAD_LAYER = 'sidama_buffered_roads_v2'
OUT = P / 'phase2g1_candidate_road_proximity_register.csv'
AUDIT = P / 'phase2g1_candidate_road_proximity_audit.txt'
CRS = 'EPSG:32637'


def col(df, options, label):
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for x in options:
        if x.lower() in lookup:
            return lookup[x.lower()]
    for x in options:
        for c in df.columns:
            if x.lower() in str(c).strip().lower():
                return c
    raise ValueError(f'Cannot identify {label}. Available columns: {list(df.columns)}')


def main():
    for f in (CANDIDATES, SPATIAL, ROADS):
        if not f.exists():
            raise FileNotFoundError(f'Required input missing: {f}')
    c = pd.read_csv(CANDIDATES, low_memory=False)
    s = pd.read_csv(SPATIAL, low_memory=False)
    cid = col(c, ['candidate_id', 'candidate_record_id', 'record_id', 'candidate_uid', 'review_id'], 'candidate ID')
    sid = col(s, ['candidate_id', 'candidate_record_id', 'record_id', 'candidate_uid', 'review_id'], 'spatial candidate ID')
    sc = col(s, ['spatial_classification', 'spatial_status', 'sidama_classification', 'boundary_classification', 'location_classification'], 'spatial classification')
    lon = col(c, ['longitude', 'lon', 'long', 'x_lon', 'longitude_wgs84', 'lon_wgs84', 'decimal_longitude', 'candidate_longitude'], 'longitude')
    lat = col(c, ['latitude', 'lat', 'y_lat', 'latitude_wgs84', 'lat_wgs84', 'decimal_latitude', 'candidate_latitude'], 'latitude')
    c[cid] = c[cid].astype(str).str.strip()
    s[sid] = s[sid].astype(str).str.strip()
    s[sc] = s[sc].astype(str).str.strip().str.upper()
    inside = s[s[sc].str.contains('INSIDE', na=False)]
    ids, inside_ids = set(c[cid]), set(inside[sid])
    if ids != inside_ids:
        raise ValueError(f'Safety stop: evidence IDs do not match INSIDE_SIDAMA IDs; evidence={len(ids)}, inside={len(inside_ids)}, evidence-only={len(ids-inside_ids)}, inside-only={len(inside_ids-ids)}')
    c[lon] = pd.to_numeric(c[lon], errors='coerce')
    c[lat] = pd.to_numeric(c[lat], errors='coerce')
    valid = c[lon].between(-180, 180) & c[lat].between(-90, 90) & c[lon].notna() & c[lat].notna()
    if not valid.all():
        raise ValueError(f'Safety stop: {int((~valid).sum())} rows have invalid/missing coordinates')
    pts = gpd.GeoDataFrame(c.copy(), geometry=gpd.points_from_xy(c[lon], c[lat]), crs='EPSG:4326').to_crs(CRS)
    roads = gpd.read_file(ROADS, layer=ROAD_LAYER)
    if roads.empty or roads.crs is None:
        raise ValueError('Road layer is empty or has no CRS; cannot calculate distances')
    roads = roads[roads.geometry.notna() & ~roads.geometry.is_empty].to_crs(CRS)
    roads = roads[roads.geometry.geom_type.isin(['LineString', 'MultiLineString'])]
    if roads.empty:
        raise ValueError('No usable line geometries in road layer')
    union = roads.geometry.union_all()
    pts['nearest_mapped_road_distance_m'] = pts.geometry.distance(union).round(3)
    pts['nearest_mapped_road_distance_km'] = (pts['nearest_mapped_road_distance_m'] / 1000).round(6)
    d = pts['nearest_mapped_road_distance_m']
    bins = [-1, 25, 50, 100, 250, 500, float('inf')]
    labels = ['0_25_M', '25_50_M', '50_100_M', '100_250_M', '250_500_M', 'OVER_500_M']
    pts['road_proximity_band'] = pd.cut(d, bins=bins, labels=labels, include_lowest=True).astype(str)
    for t in (25, 50, 100, 250, 500):
        pts[f'within_{t}m_mapped_road'] = d <= t
    pts['phase2g1_access_assessment_status'] = 'PROXIMITY_ONLY_REVIEW_REQUIRED'
    pts['physical_vehicle_access_confirmed'] = 'NO'
    pts['operational_facility_verified'] = 'NO'
    pts['routing_eligible'] = 'NO'
    pts['routing_exclusion_reason'] = 'Facility identity/operation and physical vehicle access are not verified; mapped-road proximity alone is insufficient.'
    pts['road_network_source'] = ROADS.name
    pts['road_network_layer'] = ROAD_LAYER
    pts['distance_crs'] = CRS
    pts['assessment_timestamp_utc'] = datetime.now(timezone.utc).isoformat()
    out = pd.DataFrame(pts.drop(columns='geometry'))
    out.to_csv(OUT, index=False, encoding='utf-8-sig')
    checks = []
    def ck(name, ok, detail): checks.append((name, bool(ok), detail))
    ck('candidate_count_255', len(out) == 255, f'rows={len(out)}')
    ck('candidate_ids_unique', out[cid].nunique() == len(out), f'unique_ids={out[cid].nunique()}')
    ck('all_distances_finite', d.notna().all(), f'non_null={int(d.notna().sum())}')
    ck('distances_nonnegative', (d >= 0).all(), f'minimum_m={d.min():.3f}')
    ck('all_candidates_unverified', (out['operational_facility_verified'] == 'NO').all(), 'verified candidates=0')
    ck('all_candidates_routing_ineligible', (out['routing_eligible'] == 'NO').all(), 'routing-approved candidates=0')
    ck('physical_access_not_confirmed', (out['physical_vehicle_access_confirmed'] == 'NO').all(), 'physical access confirmations=0')
    ck('evidence_ids_match_inside_spatial_ids', set(out[cid]) == inside_ids, f'evidence={len(ids)}, inside={len(inside_ids)}')
    ck('road_layer_has_line_geometry', len(roads) > 0, f'usable road features={len(roads)}; CRS={roads.crs}')
    ck('outputs_do_not_overwrite_inputs', OUT not in (CANDIDATES, SPATIAL, ROADS), 'separate Phase 2G.1 output paths')
    counts = out['road_proximity_band'].value_counts().to_dict()
    failed = [x for x in checks if not x[1]]
    lines = [
        'PNIS PHASE 2G.1 — CANDIDATE-TO-ROAD PROXIMITY ASSESSMENT', '=' * 72,
        f'Generated UTC: {datetime.now(timezone.utc).isoformat()}', f'Project root: {ROOT}', '',
        'METHOD AND SAFETY LIMITS', '-' * 72,
        'Candidate points are measured against Phase 2C v2 Sidama-buffered road geometries.',
        f'Candidate coordinate columns: longitude={lon}; latitude={lat}', f'Road source: {ROADS}',
        f'Road layer: {ROAD_LAYER}', f'Usable road features: {len(roads)}', f'Projected distance CRS: {CRS}',
        'Distance is geometric proximity to a mapped road feature only. It does NOT establish a physical entrance,',
        'road connectivity, legal access, surface quality, seasonal passability, or vehicle suitability.',
        'All candidates remain unverified and routing-ineligible.', '', 'SUMMARY', '-' * 72,
        f'Evidence-register candidates assessed: {len(out)}', f'Unique candidate IDs: {out[cid].nunique()}',
        f'Minimum distance (m): {d.min():.3f}', f'Median distance (m): {d.median():.3f}', f'Maximum distance (m): {d.max():.3f}',
        'Proximity bands:'
    ]
    for label in labels: lines.append(f'  {label}: {counts.get(label, 0)}')
    lines += ['', 'VALIDATION CHECKS', '-' * 72]
    for name, ok, detail in checks: lines.append(f'{"PASS" if ok else "FAIL"} - {name}: {detail}')
    lines += ['', f'Checks passed: {sum(x[1] for x in checks)}', f'Checks failed: {len(failed)}', f'Overall status: {"PASS" if not failed else "FAIL"}', '', 'OUTPUTS', '-' * 72, f'Register CSV: {OUT}', f'Audit TXT: {AUDIT}']
    AUDIT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    return 1 if failed else 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f'PHASE 2G.1 STOPPED: {type(e).__name__}: {e}', file=sys.stderr)
        print('No existing Phase 2C/2E outputs are modified.', file=sys.stderr)
        raise SystemExit(2)
