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
  MapMarkerTone,
  RealMapMarker,
  RealMapOverlayState,
  RealMapRoute,
} from './mapTypes';

/* ------------------------------------------------------------------ config -- */

/** Zero-key OpenStreetMap raster basemap. Attribution is intentionally kept. */
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
      id: 'osm',
      type: 'raster',
      source: 'osm',
      paint: {
        'raster-opacity': 0.92,
        'raster-saturation': -0.35,
        'raster-brightness-min': 0.18,
        'raster-brightness-max': 0.98,
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
const ROUTE_PRIMARY = '#2F7DE1';
const ROUTE_ALTERNATIVE = '#93A4BE';
const ROUTE_PREVIOUS = '#AEB9CC';

const MARKER_TONE_COLORS: Record<MapMarkerTone, string> = {
  critical: '#D90429',
  primary: '#395886',
  neutral: '#5D7089',
  simulated: '#A7AEBD',
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

function createMarkerElement(marker: RealMapMarker): HTMLDivElement {
  const el = document.createElement('div');
  const description = marker.sublabel
    ? `${marker.label} — ${marker.sublabel}`
    : marker.label;
  el.setAttribute('role', 'img');
  el.setAttribute('aria-label', description);
  el.title = description;
  el.style.width = '16px';
  el.style.height = '16px';
  el.style.boxSizing = 'border-box';
  el.style.borderRadius = '50%';
  el.style.border = '2px solid #FFFFFF';
  el.style.boxShadow = '0 1px 4px rgba(27, 29, 43, 0.35)';
  el.style.background = MARKER_TONE_COLORS[marker.tone ?? 'neutral'];
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
      new Marker({ element: createMarkerElement(marker) })
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
