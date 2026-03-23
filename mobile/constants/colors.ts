const light = {
  // Brand — vibrant blue from icon gradient
  primary: '#2563EB',
  primaryDark: '#1d4ed8',
  primaryLight: '#dbeafe',
  accent: '#10b981',

  // Backgrounds — crisp, barely-tinted white
  background: '#f8fafc',
  surface: '#ffffff',
  surfaceSecondary: '#f1f5f9',

  // Text
  text: '#0f172a',
  textSecondary: '#475569',
  textMuted: '#94a3b8',
  textInverse: '#ffffff',

  // Borders
  border: '#e2e8f0',
  borderFocus: '#2563EB',

  // Status
  error: '#ef4444',
  errorLight: '#fee2e2',
  warning: '#f59e0b',
  warningLight: '#fef3c7',
  success: '#10b981',
  successLight: '#d1fae5',
  info: '#3b82f6',
  infoLight: '#dbeafe',

  // Urgency
  urgencyLow: '#10b981',
  urgencyMedium: '#f59e0b',
  urgencyHigh: '#f97316',
  urgencyEmergency: '#ef4444',

  // Relationship badges
  relationshipSelf: '#8b5cf6',
  relationshipParent: '#3b82f6',
  relationshipSpouse: '#ec4899',
  relationshipChild: '#f59e0b',
  relationshipSibling: '#10b981',
  relationshipOther: '#64748b',
} as const;

const dark = {
  // Brand — bright blue that pops on dark, emerald accent
  primary: '#60a5fa',       // blue-400, vivid on dark
  primaryDark: '#3b82f6',   // blue-500
  primaryLight: '#1e3a5f',  // blue-900, muted tint for disabled states
  accent: '#34d399',        // emerald-400

  // Backgrounds — breathable dark with soft blue warmth, visible tier steps
  background: '#111827',    // soft charcoal, hint of blue
  surface: '#1e293b',       // clear lift — cards, sidebar, inputs
  surfaceSecondary: '#334155', // obvious step — dropdowns, hover, selected

  // Text — clean whites with enough warmth
  text: '#f8fafc',          // near-white, crisp
  textSecondary: '#94a3b8', // slate-400
  textMuted: '#64748b',     // slate-500
  textInverse: '#111827',   // dark text on bright buttons

  // Borders — slightly more visible for definition
  border: 'rgba(255, 255, 255, 0.10)',
  borderFocus: '#60a5fa',

  // Status
  error: '#f87171',         // red-400
  errorLight: '#7f1d1d',    // red-900
  warning: '#fbbf24',       // amber-400
  warningLight: '#78350f',  // amber-900
  success: '#34d399',       // emerald-400
  successLight: '#064e3b',  // emerald-900
  info: '#60a5fa',          // blue-400
  infoLight: '#1e3a5f',     // blue-900

  // Urgency
  urgencyLow: '#34d399',
  urgencyMedium: '#fbbf24',
  urgencyHigh: '#fb923c',
  urgencyEmergency: '#f87171',

  // Relationship badges
  relationshipSelf: '#a78bfa',
  relationshipParent: '#60a5fa',
  relationshipSpouse: '#f472b6',
  relationshipChild: '#fbbf24',
  relationshipSibling: '#34d399',
  relationshipOther: '#94a3b8',
} as const;

export type ColorPalette = { [K in keyof typeof light]: string };

// Type-safety: if you add a key to `light`, TypeScript will error here
// until you add the same key to `dark` (and vice versa).
const _checkDarkCoversLight: Record<keyof typeof light, string> = dark;
const _checkLightCoversDark: Record<keyof typeof dark, string> = light;

export const LightColors: ColorPalette = light;
export const DarkColors: ColorPalette = dark;

// Static export for non-component code (keep backward compat during migration)
export const Colors = light;
