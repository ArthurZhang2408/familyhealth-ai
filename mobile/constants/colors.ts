const light = {
  // Brand
  primary: '#0891b2',
  primaryDark: '#0e7490',
  primaryLight: '#cffafe',
  accent: '#14b8a6',

  // Backgrounds
  background: '#f0f9ff',
  surface: '#ffffff',
  surfaceSecondary: '#f8fafc',

  // Text
  text: '#0f172a',
  textSecondary: '#64748b',
  textMuted: '#94a3b8',
  textInverse: '#ffffff',

  // Borders
  border: '#e2e8f0',
  borderFocus: '#0891b2',

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
  relationshipParent: '#0891b2',
  relationshipSpouse: '#ec4899',
  relationshipChild: '#f59e0b',
  relationshipSibling: '#10b981',
  relationshipOther: '#64748b',
} as const;

const dark = {
  // Brand — slightly desaturated for dark surfaces
  primary: '#22d3ee',       // cyan-400, lighter teal pops on dark without glaring
  primaryDark: '#06b6d4',   // cyan-500
  primaryLight: '#164e63',  // cyan-900, muted tint for disabled states
  accent: '#2dd4bf',        // teal-400

  // Backgrounds — 3-tier slate-blue, each step a whisper
  background: '#0c1220',    // near-black with blue undertone
  surface: '#151f30',       // elevated — cards, sidebar, input capsule
  surfaceSecondary: '#1c2940', // highest — dropdowns, hover states

  // Text — warm whites, never pure #fff
  text: '#edf2f7',          // slate-100, easy on the eyes
  textSecondary: '#94a3b8', // slate-400, same as light — reads well on both
  textMuted: '#64748b',     // slate-500, dimmer in dark context
  textInverse: '#0c1220',   // dark text on bright buttons

  // Borders — rgba white glow, not solid lines
  border: 'rgba(255, 255, 255, 0.08)',
  borderFocus: '#22d3ee',

  // Status — desaturated to avoid screaming in the dark
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

  // Relationship badges — same hues, lighter for dark bg
  relationshipSelf: '#a78bfa',
  relationshipParent: '#22d3ee',
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
