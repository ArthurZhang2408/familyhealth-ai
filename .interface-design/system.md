# FamilyHealth AI — Design System

## Intent
A caretaker managing family health — stressed, sometimes scared, often checking at night.
The interface must feel calm and trustworthy, like talking to a knowledgeable friend.
Not clinical-cold, not startup-playful. Warm paper, not cool glass.

## Design Philosophy
- **Claude/ChatGPT-inspired**: sidebar-first, content-focused, no bottom tabs
- **iOS-native feel**: continuous border curves, haptics, system font scaling
- **Bubble design language**: no line separations, capsule shapes, floating elements
- **Dark mode as first-class**: 3-tier slate-blue surfaces, desaturated status colors, border-glow shadows

## Navigation Pattern
- Drawer sidebar for session history (swipe or hamburger)
- Main screen is always a conversation or report detail
- Profile pill in header center (tap → formSheet picker)
- Mode toggle (Chat/Diagnosis) in header right on new conversation screen
- Settings via user avatar capsule in sidebar footer
- No bottom tabs

## Color System
Source: `constants/colors.ts` — dual palettes (`LightColors`, `DarkColors`).
Access via `useColors()` hook — never import `Colors` statically in components.
Bidirectional compile-time check: adding a key to either palette forces the other.
Opacity suffixes permitted for tints (e.g. `Colors.primary + '20'`).

### Light
- Surfaces: `#f0f9ff` (bg) → `#ffffff` (surface) → `#f8fafc` (surfaceSecondary)
- Primary: `#0891b2` (teal-600)
- Text: `#0f172a` / `#64748b` / `#94a3b8`
- Borders: `#e2e8f0` (solid)

### Dark
- Surfaces: `#0c1220` (bg) → `#151f30` (surface) → `#1c2940` (surfaceSecondary)
- Primary: `#22d3ee` (cyan-400, lighter for dark backgrounds)
- Text: `#edf2f7` / `#94a3b8` / `#64748b`
- Borders: `rgba(255, 255, 255, 0.08)` (glow, not line)
- Status colors desaturated one step (red-400, amber-400, emerald-400)

## Shadows
Access via `useShadow()` hook — never use `Shadow` from theme constants directly.
- Light mode: traditional `boxShadow` (subtle drop shadows)
- Dark mode: `0 0 0 1px rgba(255,255,255,0.06-0.10)` ring shadows (drop shadows invisible on dark)
- Never use legacy RN shadow/elevation props

## Spacing
Grid: 4px base. Scale: 4 (xs), 8 (sm), 16 (md), 24 (lg), 32 (xl), 48 (xxl).
Source: `constants/theme.ts → Spacing`. No hardcoded pixel values.

## Typography
Static sizes: 12 (xs), 14 (sm), 16 (md), 18 (lg), 22 (xl), 28 (xxl), 34 (xxxl).
Sidebar uses `useDynamicFonts()` — scales with `useWindowDimensions().fontScale` and screen width.
Weights: 400, 500, 600, 700 via `FontWeight` constants.

## Border Radius
Scale: 8 (sm), 12 (md), 16 (lg), 24 (xl), 9999 (full).
Always `borderCurve: 'continuous'` on rounded elements.

## Icons
`@expo/vector-icons` (Ionicons, Feather, MaterialCommunityIcons) via centralized `components/Icon.tsx`.
When migrating to dev builds, swap internals to `expo-image` SF Symbols without changing call sites.

## Interactive
- Press: `opacity: pressed ? 0.6–0.85 : 1`
- Haptics: iOS only (`process.env.EXPO_OS === 'ios'`), Light/Medium/Success feedback styles
- Active sidebar item: `primary + '15'` background, primary text color, semibold weight

## Component Patterns

### Chat Input (capsule)
Floating capsule with `Shadow.md`, `BorderRadius.xl`. No border-top line.
`+` button left (attach), text input center, send button right (40x40 circle, primary bg).

### Chat Bubble
User: primary bg, no border. Assistant: surface bg, 1px border.
`animate` prop: only true for newly sent messages, false for historical (prevents bounce on load).

### Sidebar Footer
User capsule (avatar initial + first name, pill shape, bordered) on left.
Circular `+` new-conversation button (48x48, primary bg) on right.
`justifyContent: 'space-between'`, generous bottom padding including safe area.

### Mode Toggle
Header pill showing current mode icon + label. Chat = primary tint, Diagnosis = accent tint.
Tapping toggles. Only visible on new conversation screen.

### Profile Pill
Header center. Avatar circle (relationship color) + name + chevron-down.
Tapping opens formSheet profile picker.

### FormSheet Modals
Use `ScrollView` (not `FlatList`) inside formSheets — known Expo bug with FlatList layout.
No `contentInsetAdjustmentBehavior` inside sheets. No `KeyboardAvoidingView` wrapping (iOS sheets handle keyboard natively).

### Loading State
Skeleton chat bubbles on themed background. No white flash, no spinner, no text.
