import type { ReactNode } from 'react';
import { GlassPanel } from '../components';
import { Ico } from '../lib/icon';
import { IconTile } from '../components';
import type { LegendItem, MapView, OverlayKey, RouteMode, MapTone } from '../data/mock';
import { GLASS_CHIP } from './glassChip';
import type { JsonRecord } from '../api/types';

/**
 * Ported from ui_kits/operations_center/map.jsx.
 *
 * `DenseMap` is an SVG stylisation of Nasr City that stands in as the VISUAL LANGUAGE
 * reference for the real map layer. It is deliberately isolated here: the operational map
 * (tiles / vector basemap, live routes, live markers) will replace the <svg> body in a later
 * phase without touching the surrounding Operations Center chrome, overlays or panels.
 */

const MAP_W = 1600;
const MAP_H = 900;

interface Arterial {
  d: string;
  w: number;
  name: string;
  lx: number;
  ly: number;
  rot: number;
  traffic: 'med' | 'high' | 'none' | 'low';
}

const ARTERIALS: Arterial[] = [
  { d: 'M -20 372 L 1620 336', w: 17, name: 'Abbas El Akkad St.', lx: 180, ly: 356, rot: -1.3, traffic: 'med' },
  { d: 'M 690 -20 L 622 920', w: 14, name: 'Makram Ebeid St.', lx: 664, ly: 690, rot: 86, traffic: 'high' },
  { d: 'M 268 -20 L 452 920', w: 13, name: 'Tayaran St.', lx: 372, ly: 790, rot: 79, traffic: 'none' },
  { d: 'M -20 560 L 1620 524', w: 14, name: 'El Nasr Rd.', lx: 1020, ly: 545, rot: -1.3, traffic: 'med' },
  { d: 'M 1064 -20 L 1196 920', w: 16, name: 'Mostafa El Nahhas St.', lx: 1128, ly: 430, rot: 82, traffic: 'none' },
  { d: 'M -20 136 L 1620 112', w: 12, name: 'Youssef Abbas St.', lx: 150, ly: 128, rot: -1, traffic: 'none' },
  { d: 'M -20 762 L 1620 786', w: 12, name: 'Ahmed Al Zomor St.', lx: 900, ly: 782, rot: 1, traffic: 'low' },
  { d: 'M 880 -20 L 812 920', w: 11, name: 'Hassan El Mamoun St.', lx: 852, ly: 220, rot: 84, traffic: 'none' },
  { d: 'M 1380 -20 L 1470 920', w: 13, name: 'Autostrad Rd.', lx: 1424, ly: 300, rot: 81, traffic: 'high' },
  { d: 'M -20 240 L 1620 214', w: 11, name: 'Al Batrawy St.', lx: 1200, ly: 228, rot: -1, traffic: 'none' },
  { d: 'M -20 660 L 1620 636', w: 11, name: 'Zaker Hussein St.', lx: 1130, ly: 650, rot: -1, traffic: 'low' },
  { d: 'M 470 -20 L 392 920', w: 10, name: 'Anwar El Mofty St.', lx: 432, ly: 170, rot: 83, traffic: 'none' },
];

const PARKS = [
  { x: 540, y: 60, w: 210, h: 96 },
  { x: 950, y: 596, w: 168, h: 84 },
  { x: 120, y: 470, w: 120, h: 66 },
  { x: 1230, y: 300, w: 130, h: 74 },
];

const DISTRICTS = [
  { n: 'RABAA', x: 130, y: 84 },
  { n: 'AL NOZHA', x: 1300, y: 190 },
  { n: 'AL HAY AL SABEA', x: 60, y: 430 },
  { n: 'AL HAY AL THAMEN', x: 230, y: 730 },
  { n: 'AL HAY AL ASHR', x: 1290, y: 720 },
  { n: 'AL HAY AL TASEA', x: 760, y: 862 },
];

const POIS = [
  { n: 'Genena Mall', x: 300, y: 620 },
  { n: 'Sports Club', x: 1000, y: 648 },
  { n: 'International Park', x: 560, y: 118 },
  { n: 'City Stars', x: 930, y: 232 },
  { n: 'Al Azhar University', x: 1180, y: 400 },
  { n: 'Military Academy', x: 700, y: 700 },
];

const NODES: [number, number][] = [
  [341, 364], [663, 357], [381, 560], [649, 546], [1064, 240], [1196, 660],
  [845, 336], [812, 560], [455, 240], [400, 660], [1400, 350], [1440, 545],
];

const TRAFFIC_COLOR: Record<'low' | 'med' | 'high', string> = {
  low: 'var(--blue-300)',
  med: 'var(--map-congestion-med)',
  high: 'var(--map-congestion-high)',
};

const ROUTE_MAIN = 'M 401 660 L 348 392 Q 341 364 368 363 L 646 358';
const ROUTE_ALT = 'M 401 660 L 383 570 Q 379 549 400 548 L 628 546 Q 651 545 653 522 L 661 374';
const CLOSURE: [number, number] = [498, 361];

function mapBlocks() {
  const out: ReactNode[] = [];
  for (let bx = -20; bx < MAP_W; bx += 46) {
    for (let by = -10; by < MAP_H; by += 38) {
      const w = 29 + ((bx * 7 + by * 3) % 11);
      const h = 20 + ((bx * 5 + by * 11) % 11);
      out.push(
        <rect
          key={bx + '-' + by}
          x={bx + ((bx * 3) % 5)}
          y={by + ((by * 5) % 5)}
          width={w}
          height={h}
          rx="2"
          fill="var(--map-block)"
          opacity={0.55 + ((bx + by) % 5) * 0.07}
        />,
      );
    }
  }
  return out;
}

function minorStreets() {
  const out: ReactNode[] = [];
  for (let y = 14; y < MAP_H; y += 38) {
    out.push(<line key={'h' + y} x1="-20" y1={y} x2={MAP_W} y2={y - 10} stroke="var(--map-road-minor)" strokeWidth="3" />);
  }
  for (let x = -20; x < MAP_W; x += 46) {
    out.push(<line key={'v' + x} x1={x} y1="-20" x2={x + 28} y2={MAP_H} stroke="var(--map-road-minor)" strokeWidth="3" />);
  }
  return out;
}

export interface DenseMapProps {
  view?: MapView;
  overlays?: Partial<Record<OverlayKey, boolean>>;
  route?: RouteMode;
  backendMode?: boolean;
  routeGeometry?: JsonRecord | null;
  children?: ReactNode;
}

const MAP_BOUNDS = { minLon: 31.25, maxLon: 31.45, minLat: 30.00, maxLat: 30.12 };

// eslint-disable-next-line react-refresh/only-export-components
export function projectCoordinate(coordinate: { lat: number; lon: number }): { left: string; top: string } {
  const left = ((coordinate.lon - MAP_BOUNDS.minLon) / (MAP_BOUNDS.maxLon - MAP_BOUNDS.minLon)) * 100;
  const top = (1 - (coordinate.lat - MAP_BOUNDS.minLat) / (MAP_BOUNDS.maxLat - MAP_BOUNDS.minLat)) * 100;
  return { left: `${Math.max(0, Math.min(100, left))}%`, top: `${Math.max(0, Math.min(100, top))}%` };
}

function geometryPath(geometry: JsonRecord | null | undefined): string | null {
  if (!geometry || geometry.type !== 'LineString' || !Array.isArray(geometry.coordinates)) return null;
  const points = geometry.coordinates.filter((point): point is [number, number] => Array.isArray(point) && point.length >= 2 && typeof point[0] === 'number' && typeof point[1] === 'number');
  if (points.length === 0) return null;
  return points.map(([lon, lat], index) => {
    const x = ((lon - MAP_BOUNDS.minLon) / (MAP_BOUNDS.maxLon - MAP_BOUNDS.minLon)) * MAP_W;
    const y = (1 - (lat - MAP_BOUNDS.minLat) / (MAP_BOUNDS.maxLat - MAP_BOUNDS.minLat)) * MAP_H;
    return `${index === 0 ? 'M' : 'L'} ${x} ${y}`;
  }).join(' ');
}

export function DenseMap({ view = 'city', overlays = {}, route = 'plan', backendMode = false, routeGeometry, children }: DenseMapProps) {
  const box = view === 'incident' ? '250 210 1000 562' : view === 'hospital' ? '330 200 1080 607' : '0 0 1600 900';
  const showTraffic = overlays.traffic !== false;
  const replan = route === 'replan';
  const primary = replan ? ROUTE_ALT : ROUTE_MAIN;
  const previous = replan ? ROUTE_MAIN : ROUTE_ALT;
  const actualRoute = geometryPath(routeGeometry);
  return (
    <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', background: 'var(--map-land)' }}>
      <svg width="100%" height="100%" viewBox={box} preserveAspectRatio="xMidYMid slice" style={{ position: 'absolute', inset: 0 }}>
        <rect x="-20" y="-20" width={MAP_W + 40} height={MAP_H + 40} fill="var(--map-land)" />
        <path d="M -40 706 Q 340 636 720 692 T 1660 656" fill="none" stroke="var(--map-water)" strokeWidth="40" />
        {mapBlocks()}
        {PARKS.map((p, i) => (
          <rect key={'pk' + i} x={p.x} y={p.y} width={p.w} height={p.h} rx="10" fill="#DCE4DA" />
        ))}
        {minorStreets()}
        {ARTERIALS.map((a, i) => (
          <path key={'ac' + i} d={a.d} fill="none" stroke="var(--map-road-highway)" strokeWidth={a.w + 7} strokeLinecap="round" />
        ))}
        {ARTERIALS.map((a, i) => (
          <path key={'ai' + i} d={a.d} fill="none" stroke={a.w > 13 ? '#FDFEFF' : '#FBFCFE'} strokeWidth={a.w} strokeLinecap="round" />
        ))}
        {showTraffic &&
          ARTERIALS.filter((a) => a.traffic !== 'none').map((a, i) => (
            <path
              key={'at' + i}
              d={a.d}
              fill="none"
              stroke={TRAFFIC_COLOR[a.traffic as 'low' | 'med' | 'high']}
              strokeWidth={a.traffic === 'high' ? 4 : 3.6}
              opacity={a.traffic === 'high' ? 0.8 : 0.72}
              strokeLinecap="round"
              strokeDasharray={a.traffic === 'high' ? '1 0' : '34 20'}
            />
          ))}
        {NODES.map(([x, y], i) => (
          <circle key={'n' + i} cx={x} cy={y} r="4.2" fill="#fff" stroke="var(--map-road-highway)" strokeWidth="1.8" />
        ))}
        {overlays.coverage && !backendMode && (
          <g>
            <circle cx="300" cy="230" r="190" fill="var(--map-coverage-fill)" stroke="var(--map-coverage-line)" strokeWidth="1.6" strokeDasharray="8 8" />
            <circle cx="1240" cy="630" r="210" fill="var(--map-coverage-fill)" stroke="var(--map-coverage-line)" strokeWidth="1.6" strokeDasharray="8 8" />
            <circle cx="560" cy="740" r="150" fill="var(--map-coverage-fill)" stroke="var(--map-coverage-line)" strokeWidth="1.6" strokeDasharray="8 8" />
            <g>
              <circle cx="1120" cy="200" r="176" fill="var(--map-gap-fill)" stroke="var(--map-gap-line)" strokeWidth="2.4" strokeDasharray="10 7" />
              <text x="1010" y="330" textAnchor="middle" fontFamily="var(--font-en)" fontSize="27" fontWeight="700" fill="var(--red-700)" stroke="#fff" strokeWidth="6" style={{ paintOrder: 'stroke' }}>
                ZONE C · 78%
              </text>
              <text x="1010" y="357" textAnchor="middle" fontFamily="var(--font-en)" fontSize="17" fontWeight="600" fill="var(--red-700)" stroke="#fff" strokeWidth="5" style={{ paintOrder: 'stroke' }}>
                was 92% before dispatch
              </text>
            </g>
            <g stroke="var(--color-accent)" strokeWidth="5" fill="none" strokeLinecap="round">
              <path d="M 1150 600 C 1128 500 1122 440 1126 420" strokeDasharray="14 10" />
              <path d="M 1112 434 L 1126 412 L 1140 434" />
            </g>
          </g>
        )}
        {overlays.corridor && !backendMode && <path d={primary} fill="none" stroke="var(--map-corridor)" strokeWidth="24" opacity="0.22" strokeLinecap="round" />}
        {actualRoute && (
          <g>
            <path d={actualRoute} fill="none" stroke="var(--map-route-primary)" strokeWidth="20" opacity="0.14" strokeLinecap="round" strokeLinejoin="round" />
            <path d={actualRoute} fill="none" stroke="#fff" strokeWidth="13" opacity="0.95" strokeLinecap="round" strokeLinejoin="round" />
            <path d={actualRoute} fill="none" stroke="var(--map-route-primary)" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
          </g>
        )}
        {!backendMode && !actualRoute && route !== 'none' && (
          <g>
            <path d={primary} fill="none" stroke="var(--map-route-primary)" strokeWidth="20" opacity="0.14" strokeLinecap="round" strokeLinejoin="round" />
            <path d={previous} fill="none" stroke="#fff" strokeWidth="10" opacity="0.9" strokeLinecap="round" strokeLinejoin="round" />
            <path d={previous} fill="none" stroke="var(--map-route-alt)" strokeWidth="6" strokeDasharray="10 9" strokeLinecap="round" strokeLinejoin="round" />
            <path d={primary} fill="none" stroke="#fff" strokeWidth="13" opacity="0.95" strokeLinecap="round" strokeLinejoin="round" />
            <path d={primary} fill="none" stroke="var(--map-route-primary)" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
            <path d={primary} fill="none" stroke="rgba(255,255,255,.85)" strokeWidth="3" strokeDasharray="10 26" strokeLinecap="round" style={{ animation: 'sg-dash 1.6s linear infinite' }} />
          </g>
        )}
        {overlays.closure && !backendMode && (
          <g>
            <circle cx={CLOSURE[0]} cy={CLOSURE[1]} r="22" fill="#fff" stroke="var(--color-critical)" strokeWidth="3" />
            <path
              d={`M ${CLOSURE[0] - 8} ${CLOSURE[1] - 8} L ${CLOSURE[0] + 8} ${CLOSURE[1] + 8} M ${CLOSURE[0] + 8} ${CLOSURE[1] - 8} L ${CLOSURE[0] - 8} ${CLOSURE[1] + 8}`}
              stroke="var(--color-critical)"
              strokeWidth="3.6"
              strokeLinecap="round"
            />
          </g>
        )}
        {!backendMode && <g>
          <circle cx="663" cy="357" r="54" fill="var(--map-incident)" opacity="0.12" />
          <circle cx="663" cy="357" r="20" fill="var(--map-incident)" opacity="0.22" style={{ transformOrigin: '663px 357px', animation: 'sg-pulse 2.4s ease-out infinite' }} />
          <circle cx="663" cy="357" r="11" fill="var(--map-incident)" stroke="#fff" strokeWidth="3.5" />
        </g>}
        <g fontFamily="var(--font-en)" fontWeight="600" stroke="var(--map-label-halo)" style={{ paintOrder: 'stroke' }}>
          {ARTERIALS.map((a, i) => (
            <text key={'al' + i} x={a.lx} y={a.ly} fontSize="15" fill="var(--map-label)" transform={`rotate(${a.rot} ${a.lx} ${a.ly})`} strokeWidth="4.5">
              {a.name}
            </text>
          ))}
          {DISTRICTS.map((d, i) => (
            <text key={'d' + i} x={d.x} y={d.y} fontSize="15" letterSpacing="2" fill="var(--slate-600)" strokeWidth="4.5">
              {d.n}
            </text>
          ))}
          {POIS.map((p, i) => (
            <g key={'p' + i}>
              <circle cx={p.x - 11} cy={p.y - 4} r="4" fill="var(--slate-400)" stroke="#fff" strokeWidth="1.6" />
              <text x={p.x} y={p.y} fontSize="13.5" fill="var(--slate-600)" strokeWidth="4">
                {p.n}
              </text>
            </g>
          ))}
        </g>
      </svg>
      {children}
    </div>
  );
}

export function FacilityPin({ icon, label, tone = 'navy', left, top }: { icon: string; label?: string; tone?: MapTone; left: string; top: string }) {
  return (
    <div className="sg-rise" style={{ position: 'absolute', left, top, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, transform: 'translate(-50%,-50%)' }}>
      <div style={{ padding: 4, borderRadius: '50%', ...GLASS_CHIP }}>
        <IconTile icon={<Ico n={icon} />} tint={tone} shape="circle" size={30} />
      </div>
      {label && (
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-primary)', padding: '2px 7px', borderRadius: 'var(--radius-pill)', whiteSpace: 'nowrap', ...GLASS_CHIP }}>
          {label}
        </span>
      )}
    </div>
  );
}

export function MapMarker({ icon, label, sub, tone = 'blue', left, top }: { icon: string; label: string; sub?: string; tone?: MapTone; left: string; top: string }) {
  return (
    <div className="sg-rise" style={{ position: 'absolute', left, top, display: 'flex', alignItems: 'center', gap: 10, padding: '6px 14px 6px 6px', borderRadius: 'var(--radius-md)', whiteSpace: 'nowrap', ...GLASS_CHIP }}>
      <IconTile icon={<Ico n={icon} />} tint={tone} shape="circle" size={32} />
      <div>
        <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)' }}>{label}</div>
        {sub && <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)' }}>{sub}</div>}
      </div>
    </div>
  );
}

export function MapControls({
  overlays,
  setOverlay,
}: {
  overlays: Partial<Record<OverlayKey, boolean>>;
  setOverlay: (k: OverlayKey, v: boolean) => void;
}) {
  const rows: [OverlayKey, string, string][] = [
    ['traffic', 'Traffic', 'gauge'],
    ['coverage', 'Coverage', 'shield-check'],
    ['corridor', 'Corridor', 'route'],
    ['closure', 'Closures', 'octagon-x'],
  ];
  return (
    <GlassPanel padding={6} style={{ position: 'absolute', top: 16, right: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
      {rows.map(([k, l, i]) => {
        const on = !!overlays[k];
        return (
          <button
            key={k}
            onClick={() => setOverlay(k, !on)}
            aria-pressed={on}
            title={l}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 9,
              padding: '5px 11px 5px 5px',
              border: 'none',
              background: on ? 'var(--color-accent-soft)' : 'transparent',
              borderRadius: 'var(--radius-md)',
              cursor: 'pointer',
              fontFamily: 'var(--font-en)',
              fontSize: 13,
              fontWeight: 600,
              color: on ? 'var(--color-accent)' : 'var(--color-text-secondary)',
            }}
          >
            <IconTile icon={<Ico n={i} />} tint={on ? 'blue' : 'slate'} size={28} />
            {l}
          </button>
        );
      })}
    </GlassPanel>
  );
}

export function MapLegend({ items }: { items: LegendItem[] }) {
  return (
    <GlassPanel padding={11} style={{ position: 'absolute', bottom: 16, left: 16 }}>
      <div style={{ display: 'flex', gap: 18, alignItems: 'center', fontSize: 12.5, fontWeight: 500, color: 'var(--color-text-secondary)' }}>
        {items.map((it, i) => (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <span style={{ width: it.dot ? 10 : 24, height: it.dot ? 10 : 5, borderRadius: it.dot ? '50%' : 3, background: it.color }} />
            {it.label}
          </span>
        ))}
      </div>
    </GlassPanel>
  );
}

export function MapScale() {
  return (
    <div style={{ position: 'absolute', bottom: 16, right: 16, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
      <div style={{ display: 'flex', flexDirection: 'column', borderRadius: 'var(--radius-md)', overflow: 'hidden', ...GLASS_CHIP }}>
        {(['plus', 'minus'] as const).map((n) => (
          <span
            key={n}
            style={{
              width: 34,
              height: 32,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--color-text-secondary)',
              borderBottom: n === 'plus' ? '0.5px solid var(--color-border-hairline)' : 'none',
            }}
          >
            <span style={{ width: 15, height: 15, display: 'flex' }}>
              <Ico n={n} />
            </span>
          </span>
        ))}
      </div>
      <div style={{ width: 38, height: 38, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', ...GLASS_CHIP }}>
        <span style={{ width: 16, height: 16, color: 'var(--color-accent)', display: 'flex' }}>
          <Ico n="navigation" />
        </span>
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)', padding: '3px 10px', borderRadius: 'var(--radius-pill)', ...GLASS_CHIP }}>500 m</div>
    </div>
  );
}
