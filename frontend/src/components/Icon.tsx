import {
  ArrowDown,
  ArrowUp,
  AudioLines,
  Captions,
  Check,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Circle,
  CircleArrowDown,
  CircleCheck,
  CircleMinus,
  CircleX,
  ClipboardPaste,
  Copy,
  Film,
  Folder,
  FolderOpen,
  Info,
  LayoutGrid,
  Library,
  Link,
  List,
  Loader,
  Moon,
  Music,
  OctagonX,
  PanelLeft,
  Play,
  Plus,
  RotateCw,
  Scissors,
  Search,
  Settings,
  SlidersHorizontal,
  Stethoscope,
  Sun,
  SunMoon,
  Trash2,
  TriangleAlert,
  WandSparkles,
  X,
  type LucideIcon,
} from 'lucide-react';

/**
 * Icons are requested by their SF Symbols name, so the vocabulary matches Apple's HIG.
 * SF Symbols themselves cannot be used inside a web view, so each name maps to the closest
 * glyph of Lucide (ISC licence), drawn with SF-like rounded strokes.
 */
const SYMBOLS = {
  magnifyingglass: Search,
  'arrow.down.circle': CircleArrowDown,
  'books.vertical': Library,
  scissors: Scissors,
  stethoscope: Stethoscope,
  gearshape: Settings,
  'sun.max.fill': Sun,
  'moon.fill': Moon,
  'circle.lefthalf.filled': SunMoon,
  'sidebar.left': PanelLeft,
  trash: Trash2,
  plus: Plus,
  folder: Folder,
  'folder.badge.plus': FolderOpen,
  'play.fill': Play,
  'arrow.clockwise': RotateCw,
  'xmark.circle': CircleX,
  xmark: X,
  'doc.on.doc': Copy,
  'exclamationmark.triangle.fill': TriangleAlert,
  'checkmark.circle.fill': CircleCheck,
  circle: Circle,
  'xmark.octagon.fill': OctagonX,
  'info.circle': Info,
  'square.grid.2x2': LayoutGrid,
  'list.bullet': List,
  'music.note': Music,
  film: Film,
  'chevron.right': ChevronRight,
  'chevron.down': ChevronDown,
  'chevron.up': ChevronUp,
  'arrow.up': ArrowUp,
  'arrow.down': ArrowDown,
  link: Link,
  'wand.and.stars': WandSparkles,
  captions: Captions,
  waveform: AudioLines,
  'minus.circle': CircleMinus,
  'doc.on.clipboard': ClipboardPaste,
  checkmark: Check,
  'slider.horizontal.3': SlidersHorizontal,
  'progress.indicator': Loader,
} satisfies Record<string, LucideIcon>;

export type SymbolName = keyof typeof SYMBOLS;

/** Filled symbols drawn solid; other ".fill" names get SF's hierarchical two-tone treatment. */
const SOLID = new Set<SymbolName>(['sun.max.fill', 'moon.fill', 'play.fill']);

export function Icon({
  name,
  size = 16,
  tone,
  label,
  className,
}: {
  name: SymbolName;
  size?: number;
  /** "multicolor" status colours, as SF Symbols renders them. */
  tone?: 'green' | 'yellow' | 'red' | 'accent' | 'secondary';
  /** Only for an icon that stands alone and carries meaning; decorative icons stay hidden. */
  label?: string;
  className?: string;
}) {
  const Glyph = SYMBOLS[name];
  const filled = name.endsWith('.fill');
  return (
    <Glyph
      size={size}
      strokeWidth={1.75}
      fill={filled ? 'currentColor' : 'none'}
      fillOpacity={filled ? (SOLID.has(name) ? 1 : 0.22) : undefined}
      className={['sf', tone ? `sf-${tone}` : '', className ?? ''].join(' ').trim()}
      aria-hidden={label ? undefined : true}
      role={label ? 'img' : undefined}
      aria-label={label}
      focusable={false}
    />
  );
}
