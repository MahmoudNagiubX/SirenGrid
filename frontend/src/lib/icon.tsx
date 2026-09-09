import {
  Ambulance,
  ArrowRight,
  Brain,
  Car,
  Check,
  ChevronDown,
  ChevronUp,
  CircleCheck,
  CircleDot,
  ClipboardList,
  Clock,
  Database,
  FileText,
  Flame,
  Gauge,
  GitCompare,
  HeartPulse,
  Hospital,
  Image,
  LayoutGrid,
  ListChecks,
  Map as MapIcon,
  MapPin,
  Minus,
  Navigation,
  OctagonX,
  Pencil,
  Phone,
  Plus,
  Radar,
  RadioTower,
  RefreshCw,
  Route,
  Search,
  Shield,
  ShieldCheck,
  Siren,
  SlidersHorizontal,
  Sparkles,
  TriangleAlert,
  Truck,
  UserRound,
  UserRoundCheck,
  X,
  type LucideIcon,
  type LucideProps,
} from 'lucide-react';

/**
 * `Ico` — kebab-case Lucide glyph renderer, ported from the design project's `Ico` helper
 * (ui_kits/operations_center/shell.jsx).
 *
 * Fills its parent box (width/height 100%) and defaults to a 2px stroke so one coherent icon
 * family and weight is used across nav, markers, tiles and controls. The registry is an explicit
 * allow-list (not a dynamic dump of all of Lucide) so the bundle only ships icons actually used.
 */
const REGISTRY: Record<string, LucideIcon> = {
  ambulance: Ambulance,
  'arrow-right': ArrowRight,
  brain: Brain,
  car: Car,
  check: Check,
  'chevron-down': ChevronDown,
  'chevron-up': ChevronUp,
  'circle-check': CircleCheck,
  'circle-dot': CircleDot,
  'clipboard-list': ClipboardList,
  clock: Clock,
  database: Database,
  'file-text': FileText,
  flame: Flame,
  gauge: Gauge,
  'git-compare': GitCompare,
  'heart-pulse': HeartPulse,
  hospital: Hospital,
  image: Image,
  'layout-grid': LayoutGrid,
  'list-checks': ListChecks,
  map: MapIcon,
  'map-pin': MapPin,
  minus: Minus,
  navigation: Navigation,
  'octagon-x': OctagonX,
  pencil: Pencil,
  phone: Phone,
  plus: Plus,
  radar: Radar,
  'radio-tower': RadioTower,
  'refresh-cw': RefreshCw,
  route: Route,
  search: Search,
  shield: Shield,
  'shield-check': ShieldCheck,
  siren: Siren,
  'sliders-horizontal': SlidersHorizontal,
  sparkles: Sparkles,
  'triangle-alert': TriangleAlert,
  truck: Truck,
  'user-round': UserRound,
  'user-round-check': UserRoundCheck,
  x: X,
};

interface IcoProps extends Omit<LucideProps, 'ref'> {
  n: string;
}

export function Ico({ n, strokeWidth = 2, ...rest }: IcoProps) {
  const Cmp = REGISTRY[n];
  if (!Cmp) {
    if (import.meta.env.DEV) console.warn(`[Ico] unregistered icon "${n}"`);
    return <span style={{ display: 'flex', width: '100%', height: '100%' }} />;
  }
  return <Cmp width="100%" height="100%" strokeWidth={strokeWidth} {...rest} />;
}
