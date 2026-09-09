/**
 * SG-MAP-04A — renderer input types for `RealMapCanvas`.
 *
 * These types describe ONLY what the isolated map renderer accepts as props.
 * They are provider-neutral and deliberately know nothing about SirenGrid
 * backend schemas (`IncidentRead`, `ResponsePlanRead`, `ResourceRead`,
 * `HospitalRead`), `OperationsContext`, or React state. That isolation is what
 * lets Phase 04A ship in parallel with the Phase 03 data layer.
 *
 * Coordinates follow the canonical backend GeoJSON contract (RFC 7946):
 * `[longitude, latitude]`, WGS84 / EPSG:4326.
 */

/** A single position: `[longitude, latitude]`. */
export type LngLatTuple = readonly [longitude: number, latitude: number];

/** GeoJSON `Point` / `LineString` / `MultiLineString` / `Polygon` / `MultiPolygon`. */
export type MapGeoJsonGeometry =
  | {
      type: 'Point';
      coordinates: readonly [number, number];
    }
  | {
      type: 'LineString';
      coordinates: readonly (readonly [number, number])[];
    }
  | {
      type: 'MultiLineString';
      coordinates: readonly (readonly (readonly [number, number])[])[];
    }
  | {
      type: 'Polygon';
      coordinates: readonly (readonly (readonly [number, number])[])[];
    }
  | {
      type: 'MultiPolygon';
      coordinates: readonly (readonly (readonly (readonly [number, number])[])[])[];
    };

export interface MapGeoJsonFeature {
  type: 'Feature';
  geometry: MapGeoJsonGeometry | null;
  properties?: Record<string, unknown> | null;
}

export interface MapGeoJsonFeatureCollection {
  type: 'FeatureCollection';
  features: readonly MapGeoJsonFeature[];
}

/** Renderer marker categories. The caller decides which one a datum earns. */
export type MapMarkerKind = 'incident' | 'resource' | 'hospital' | 'facility';

/** Pictogram drawn inside the marker. The caller picks it from backend truth. */
export type MapMarkerIcon =
  | 'incident'
  | 'ambulance'
  | 'fire'
  | 'police'
  | 'hospital'
  | 'unit';

/** Renderer colour intent. The caller supplies tone; the renderer never infers it. */
export type MapMarkerTone = 'critical' | 'primary' | 'neutral' | 'simulated';

export interface RealMapMarker {
  id: string;
  coordinate: LngLatTuple;
  kind: MapMarkerKind;
  label: string;
  sublabel?: string;
  tone?: MapMarkerTone;
  /** Optional pictogram; defaults are derived from `kind` when absent. */
  icon?: MapMarkerIcon;
  /** Selected markers get a highlight ring / pulse. */
  selected?: boolean;
}

/** Role of a supplied route line. Geometry is never computed by the renderer. */
export type RealMapRouteRole = 'primary' | 'alternative' | 'previous';

export interface RealMapRoute {
  id: string;
  geometry: MapGeoJsonFeatureCollection;
  role: RealMapRouteRole;
  label?: string;
}

/** Optional per-layer visibility toggles. Absent keys default to visible. */
export interface RealMapOverlayState {
  roads?: boolean;
  zones?: boolean;
  boundary?: boolean;
}
