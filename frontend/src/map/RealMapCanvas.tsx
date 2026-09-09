/**
 * SG-MAP-04A — isolated real-map foundation.
 *
 * `RealMapCanvas` is a pure MapLibre GL renderer. It owns the map instance
 * lifecycle, an OpenStreetMap raster basemap, a Nasr City default viewport,
 * and a small fixed set of sources/layers for boundary / roads / zones /
 * routes plus DOM markers.
 *
 * It performs NO SirenGrid network I/O, imports no API client, and reads no
 * shared operational state. Every piece of geometry it draws is supplied by
 * its parent as props. Backend binding is deferred to Phase 04B.
 */

import { useEffect, useRef, useState } from 'react';
import {
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  GeoJSONSource,
  type MapOptions,
} from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

import type {
  LngLatTuple,
  MapGeoJsonFeatureCollection,
  MapMarkerIcon,
  MapMarkerKind,
  MapMarkerTone,
  RealMapMarker,
  RealMapOverlayState,
  RealMapRoute,
} from './mapTypes';

/* ------------------------------------------------------------------ config -- */

/** Light Mist ground the desaturated raster sits on so the whole map reads cool. */
const BASEMAP_GROUND = '#EDF2F4';

/**
 * Zero-key OpenStreetMap raster basemap. Attribution is intentionally kept.
 *
 * A raster tile is a pre-rendered image, so MapLibre cannot recolour individual
 * roads/parks/labels into SirenGrid semantic colours. What it *can* do is tone
 * the whole tile: here a Light Mist (`#EDF2F4`) `background` layer sits beneath
 * a strongly desaturated, slightly cooled, partly transparent raster so the
 * ground bleeds through. The result keeps OSM road/label detail but visibly
 * belongs to SirenGrid — beige/yellow dominance is pulled out and Navy / Slate
 * / Red overlays stand off the surface.
 */
const BASEMAP_STYLE: NonNullable<MapOptions['style']> = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: [
    {
      id: 'sg-basemap-ground',
      type: 'background',
      paint: { 'background-color': BASEMAP_GROUND },
    },
    {
      id: 'osm',
      type: 'raster',
      source: 'osm',
      paint: {
        // Let the Light Mist ground influence the tone; near-fully desaturate
        // and lift the shadows so the map is light and cool while staying
        // readable (Arabic labels included).
        'raster-opacity': 0.82,
        'raster-saturation': -0.9,
        'raster-contrast': 0.04,
        'raster-hue-rotate': 12,
        'raster-brightness-min': 0.34,
        'raster-brightness-max': 0.96,
      },
    },
  ],
};

/** Presentation viewport near Nasr City. Viewport config only — not incident truth. */
const DEFAULT_CENTER: LngLatTuple = [31.3445, 30.0561];
const DEFAULT_ZOOM = 13.2;

const SOURCE_BOUNDARY = 'sg-boundary';
const SOURCE_ROADS = 'sg-roads';
const SOURCE_ZONES = 'sg-zones';
const SOURCE_ROUTES = 'sg-routes';

/* Palette aligned with the existing SirenGrid design tokens (tokens.css). */
const BOUNDARY_FILL = '#395886';
const BOUNDARY_LINE = '#2C4468';
const ZONES_FILL = '#628ECB';
const ZONES_LINE = '#8AAEE0';
const ROADS_LINE = '#4A76AE';
// Operational route palette (mission section 25): primary route Deep Navy,
// alternate Slate, superseded a muted slate tint.
const ROUTE_PRIMARY = '#2B2D42';
const ROUTE_ALTERNATIVE = '#8D99AE';
const ROUTE_PREVIOUS = '#AEB9CC';

const MARKER_TONE_COLORS: Record<MapMarkerTone, string> = {
  critical: '#D90429',
  primary: '#2B2D42',
  neutral: '#5D7089',
  simulated: '#8D99AE',
};

/** Per-category fill so a marker reads by type even before its label. */
const MARKER_KIND_COLORS: Record<MapMarkerKind, string> = {
  incident: '#EF233C',
  hospital: '#395886',
  resource: '#2B2D42',
  facility: '#5D7089',
};

/** 16px-viewBox pictograms, white stroke, drawn inside the pin. */
const MARKER_ICON_PATHS: Record<MapMarkerIcon, string> = {
  incident:
    '<path d="M8 3.2 14 13H2z" fill="none" stroke="#fff" stroke-width="1.7" stroke-linejoin="round"/><path d="M8 6.6v3.1M8 11.3v.05" stroke="#fff" stroke-width="1.7" stroke-linecap="round"/>',
  ambulance:
    '<rect x="2.4" y="5" width="11.2" height="6.4" rx="1.2" fill="none" stroke="#fff" stroke-width="1.6"/><path d="M8 6.7v3M6.5 8.2h3" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/><circle cx="5" cy="12" r="1.15" fill="#fff"/><circle cx="11" cy="12" r="1.15" fill="#fff"/>',
  fire:
    '<path d="M8 2.6c1.7 2.2 3.2 3.6 3.2 6.1A3.2 3.2 0 0 1 8 12a3.2 3.2 0 0 1-3.2-3.3c0-1.3.5-2.2 1.3-3 .1 1 .7 1.6 1.3 1.9-.2-1.9.3-3.6.6-4z" fill="none" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/>',
  police:
    '<path d="M8 2.6 13 4.4v3.4c0 3-2 4.8-5 5.9-3-1.1-5-2.9-5-5.9V4.4z" fill="none" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/><path d="M6 7.7 7.4 9 10 6" fill="none" stroke="#fff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
  hospital:
    '<rect x="3" y="3.4" width="10" height="9.4" rx="1.1" fill="none" stroke="#fff" stroke-width="1.5"/><path d="M8 5.7v4.4M5.8 7.9h4.4" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/>',
  unit:
    '<circle cx="8" cy="8" r="3" fill="none" stroke="#fff" stroke-width="1.7"/>',
};

const EMPTY_FEATURE_COLLECTION: GeoJSON.FeatureCollection = {
  type: 'FeatureCollection',
  features: [],
};

const NO_MARKERS: readonly RealMapMarker[] = [];
const NO_ROUTES: readonly RealMapRoute[] = [];

/* ------------------------------------------------------------------- props -- */

export interface RealMapCanvasProps {
  boundary?: MapGeoJsonFeatureCollection | null;
  roads?: MapGeoJsonFeatureCollection | null;
  zones?: MapGeoJsonFeatureCollection | null;
  markers?: readonly RealMapMarker[];
  routes?: readonly RealMapRoute[];
  center?: LngLatTuple;
  zoom?: number;
  overlays?: RealMapOverlayState;
  interactive?: boolean;
  className?: string;
  onReady?: () => void;
  onError?: (message: string) => void;
}

/* ----------------------------------------------------------------- helpers -- */

const toTuple = (value: LngLatTuple): [number, number] => [value[0], value[1]];

/**
 * The renderer input types are deliberately `readonly`; MapLibre wants the
 * mutable `@types/geojson` shapes. The structure is identical, so this is the
 * single controlled cast site.
 */
const asGeoJson = (
  collection: MapGeoJsonFeatureCollection,
): GeoJSON.FeatureCollection =>
  collection as unknown as GeoJSON.FeatureCollection;

function routesToFeatureCollection(
  routes: readonly RealMapRoute[],
): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (const route of routes) {
    for (const feature of route.geometry.features) {
      if (!feature.geometry) continue;
      features.push({
        type: 'Feature',
        geometry: feature.geometry as unknown as GeoJSON.Geometry,
        properties: {
          ...(feature.properties ?? {}),
          sg_role: route.role,
          sg_route_id: route.id,
        },
      });
    }
  }
  return { type: 'FeatureCollection', features };
}

function setSourceData(
  map: MapLibreMap,
  sourceId: string,
  data: GeoJSON.FeatureCollection,
): void {
  const source = map.getSource(sourceId);
  if (source instanceof GeoJSONSource) {
    void source.setData(data);
  }
}

function setLayerVisible(map: MapLibreMap, layerId: string, visible: boolean): void {
  if (map.getLayer(layerId)) {
    map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
  }
}

const KIND_DEFAULT_ICON: Record<MapMarkerKind, MapMarkerIcon> = {
  incident: 'incident',
  hospital: 'hospital',
  resource: 'unit',
  facility: 'unit',
};

function markerFill(marker: RealMapMarker): string {
  // Incidents and hospitals carry their category colour so they read at a
  // glance. Responders stay calm/neutral unless committed to the selected
  // incident — a parked fire engine must not look like an alarm.
  if (marker.kind === 'incident') return MARKER_KIND_COLORS.incident;
  if (marker.kind === 'hospital') return MARKER_KIND_COLORS.hospital;
  if (marker.tone === 'critical') return MARKER_TONE_COLORS.critical;
  if (marker.tone === 'primary') return MARKER_TONE_COLORS.primary;
  if (marker.tone === 'simulated') return MARKER_TONE_COLORS.simulated;
  return MARKER_TONE_COLORS.neutral;
}

/**
 * Build the DOM for one marker.
 *
 * The returned element is handed straight to `new Marker({ element })`, so it is
 * the MapLibre marker *root*: MapLibre owns its `position`/`top`/`left` (from
 * `.maplibregl-marker`) and rewrites its `transform` every frame to keep it on
 * its geographic point. We must not set `position` (or any transform) on it — an
 * inline `position: relative` overrides MapLibre's `position: absolute` and the
 * per-frame `translate(x, y)` is then measured from the element's document-flow
 * box instead of the map origin, which is what made markers drift on zoom/pan.
 *
 * All sizing, the `position: relative` context for the absolutely-positioned pin
 * and pulse ring, and the only animation live on an inner wrapper.
 */
function createMarkerElement(marker: RealMapMarker): HTMLDivElement {
  const el = document.createElement('div');
  const description = marker.sublabel
    ? `${marker.label} — ${marker.sublabel}`
    : marker.label;
  el.setAttribute('role', 'img');
  el.setAttribute('aria-label', description);
  el.title = description;
  el.style.pointerEvents = 'none';

  const size = marker.selected ? '30px' : '26px';
  const wrapper = document.createElement('div');
  wrapper.style.cssText =
    `position:relative;width:${size};height:${size};` +
    'display:flex;align-items:center;justify-content:center;';

  const icon = marker.icon ?? KIND_DEFAULT_ICON[marker.kind];
  const fill = markerFill(marker);
  const pin = document.createElement('div');
  pin.style.cssText =
    'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;' +
    `border-radius:50%;background:${fill};` +
    'border:2px solid #fff;box-shadow:0 2px 6px rgba(27,29,43,.32);';
  pin.innerHTML =
    `<svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true">${MARKER_ICON_PATHS[icon]}</svg>`;
  wrapper.appendChild(pin);

  if (marker.selected) {
    const ring = document.createElement('span');
    ring.className = 'sg-marker-ring';
    ring.style.borderColor = fill;
    wrapper.appendChild(ring);
  }

  el.appendChild(wrapper);
  return el;
}

/**
 * Register the fixed source/layer set once, after the style has loaded.
 * Layer insertion order defines the stack:
 * basemap → boundary → zones → roads → previous → alternative → primary route.
 */
function initLayers(map: MapLibreMap): void {
  map.addSource(SOURCE_BOUNDARY, { type: 'geojson', data: EMPTY_FEATURE_COLLECTION });
  map.addLayer({
    id: 'sg-boundary-fill',
    type: 'fill',
    source: SOURCE_BOUNDARY,
    paint: { 'fill-color': BOUNDARY_FILL, 'fill-opacity': 0.08 },
  });
  map.addLayer({
    id: 'sg-boundary-line',
    type: 'line',
    source: SOURCE_BOUNDARY,
    paint: { 'line-color': BOUNDARY_LINE, 'line-width': 1.5, 'line-opacity': 0.7 },
  });

  map.addSource(SOURCE_ZONES, { type: 'geojson', data: EMPTY_FEATURE_COLLECTION });
  map.addLayer({
    id: 'sg-zones-fill',
    type: 'fill',
    source: SOURCE_ZONES,
    paint: { 'fill-color': ZONES_FILL, 'fill-opacity': 0.05 },
  });
  map.addLayer({
    id: 'sg-zones-line',
    type: 'line',
    source: SOURCE_ZONES,
    paint: { 'line-color': ZONES_LINE, 'line-width': 0.6, 'line-opacity': 0.5 },
  });

  map.addSource(SOURCE_ROADS, { type: 'geojson', data: EMPTY_FEATURE_COLLECTION });
  map.addLayer({
    id: 'sg-roads-line',
    type: 'line',
    source: SOURCE_ROADS,
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ROADS_LINE, 'line-width': 1, 'line-opacity': 0.55 },
  });

  map.addSource(SOURCE_ROUTES, { type: 'geojson', data: EMPTY_FEATURE_COLLECTION });
  map.addLayer({
    id: 'sg-routes-previous',
    type: 'line',
    source: SOURCE_ROUTES,
    filter: ['==', 'sg_role', 'previous'],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': ROUTE_PREVIOUS,
      'line-width': 3,
      'line-opacity': 0.7,
      'line-dasharray': [1.5, 1.5],
    },
  });
  map.addLayer({
    id: 'sg-routes-alternative',
    type: 'line',
    source: SOURCE_ROUTES,
    filter: ['==', 'sg_role', 'alternative'],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': ROUTE_ALTERNATIVE,
      'line-width': 3,
      'line-opacity': 0.85,
      'line-dasharray': [2, 1.5],
    },
  });
  map.addLayer({
    id: 'sg-routes-primary',
    type: 'line',
    source: SOURCE_ROUTES,
    filter: ['==', 'sg_role', 'primary'],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ROUTE_PRIMARY, 'line-width': 4.5 },
  });
}

/* --------------------------------------------------------------- component -- */

export function RealMapCanvas({
  boundary,
  roads,
  zones,
  markers = NO_MARKERS,
  routes = NO_ROUTES,
  center,
  zoom,
  overlays,
  interactive,
  className,
  onReady,
  onError,
}: RealMapCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);

  // Keep the latest callbacks / initial-view values without re-subscribing.
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const centerRef = useRef(center);
  centerRef.current = center;
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const interactiveRef = useRef(interactive);
  interactiveRef.current = interactive;

  // --- map instance lifecycle (one per mount) --------------------------------
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const map = new MapLibreMap({
      container,
      style: BASEMAP_STYLE,
      center: toTuple(centerRef.current ?? DEFAULT_CENTER),
      zoom: zoomRef.current ?? DEFAULT_ZOOM,
      interactive: interactiveRef.current !== false,
    });
    mapRef.current = map;

    map.addControl(
      new NavigationControl({ showCompass: false, showZoom: true }),
      'top-right',
    );

    const handleError = (event: unknown): void => {
      const detail = (event as { error?: { message?: string } })?.error;
      onErrorRef.current?.(detail?.message ?? 'Map rendering error');
    };
    const handleLoad = (): void => {
      initLayers(map);
      setReady(true);
      onReadyRef.current?.();
    };
    map.on('error', handleError);
    map.on('load', handleLoad);

    const resizeObserver = new ResizeObserver(() => {
      map.resize();
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      map.off('load', handleLoad);
      map.off('error', handleError);
      mapRef.current = null;
      setReady(false);
      map.remove();
    };
  }, []);

  // --- boundary / roads / zones data ---------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setSourceData(
      map,
      SOURCE_BOUNDARY,
      boundary ? asGeoJson(boundary) : EMPTY_FEATURE_COLLECTION,
    );
    setSourceData(
      map,
      SOURCE_ROADS,
      roads ? asGeoJson(roads) : EMPTY_FEATURE_COLLECTION,
    );
    setSourceData(
      map,
      SOURCE_ZONES,
      zones ? asGeoJson(zones) : EMPTY_FEATURE_COLLECTION,
    );
  }, [ready, boundary, roads, zones]);

  // --- route data ---------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setSourceData(map, SOURCE_ROUTES, routesToFeatureCollection(routes));
  }, [ready, routes]);

  // --- markers (rebuilt on change, removed on unmount) -------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const instances = markers.map((marker) =>
      // `anchor: 'center'` — these are circular pins, so their geographic point
      // is their centre. MapLibre keeps the root transform under its control;
      // only the inner wrapper's pulse ring animates.
      new Marker({ element: createMarkerElement(marker), anchor: 'center' })
        .setLngLat(toTuple(marker.coordinate))
        .addTo(map),
    );
    return () => {
      for (const instance of instances) instance.remove();
    };
  }, [ready, markers]);

  // --- overlay visibility ----------------------------------------------------
  const showBoundary = overlays?.boundary !== false;
  const showRoads = overlays?.roads !== false;
  const showZones = overlays?.zones !== false;
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setLayerVisible(map, 'sg-boundary-fill', showBoundary);
    setLayerVisible(map, 'sg-boundary-line', showBoundary);
    setLayerVisible(map, 'sg-roads-line', showRoads);
    setLayerVisible(map, 'sg-zones-fill', showZones);
    setLayerVisible(map, 'sg-zones-line', showZones);
  }, [ready, showBoundary, showRoads, showZones]);

  // --- camera prop updates -------------------------------------------------
  const lng = center?.[0];
  const lat = center?.[1];
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const next: { center?: [number, number]; zoom?: number } = {};
    if (lng != null && lat != null) next.center = [lng, lat];
    if (zoom != null) next.zoom = zoom;
    if (next.center || next.zoom != null) {
      map.easeTo({ ...next, duration: 300 });
    }
  }, [ready, lng, lat, zoom]);

  // --- interactivity toggle ---------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const gestures = [
      map.dragPan,
      map.scrollZoom,
      map.boxZoom,
      map.dragRotate,
      map.keyboard,
      map.doubleClickZoom,
      map.touchZoomRotate,
      map.touchPitch,
    ];
    for (const gesture of gestures) {
      if (interactive === false) gesture.disable();
      else gesture.enable();
    }
  }, [ready, interactive]);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ position: 'absolute', inset: 0 }}
    />
  );
}
