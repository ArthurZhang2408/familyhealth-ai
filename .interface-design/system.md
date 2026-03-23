# Salk — Design System

## Intent
A caretaker managing family health — stressed, sometimes scared, often checking at night.
The interface must feel calm and trustworthy, like talking to a knowledgeable friend.
Vibrant and confident, like a well-made Apple app. Not clinical-cold, not startup-playful.

## Design Philosophy
- **Claude/ChatGPT-inspired**: sidebar-first, content-focused, no bottom tabs
- **iOS-native feel**: continuous border curves, haptics, system font scaling
- **Bubble design language**: no line separations, capsule shapes, floating elements
- **Dark mode as first-class**: 3-tier slate-blue surfaces, desaturated status colors, border-glow shadows
- **Dynamic sizing**: all header elements scale with system font setting + screen width via `useHeaderScale()`

## Navigation Pattern
- Drawer sidebar for session history (swipe or hamburger)
- Main screen is always a conversation or report detail
- Profile name in header center (tap → formSheet picker)
- Mode toggle (Chat/Diagnosis) icon-only in header right on new conversation screen
- Compose (pen-square) icon in header right on active chat/diagnosis screens
- Settings via user avatar capsule in sidebar footer
- No bottom tabs

## Header System
Custom `HeaderBar` component replaces React Navigation's default header entirely for full layout control.

### Components
- **`HeaderBar`** — flex row: left slot, center slot (flex:1), right slot. Uses `useSafeAreaInsets()` for status bar. Height = `buttonSize + Spacing.sm * 2`
- **`HeaderIconButton`** — the one component for ALL circular header buttons. Takes `icon`, `onPress`, optional `tint`. Includes haptic via `useHapticPress()`
- **`ProfilePill`** — name text + chevron-down. No avatar circle. Height matches `buttonSize`
- **`ModeToggle`** — wraps `HeaderIconButton` with tint color. Icon-only (no text labels)

### Dynamic Sizing — `useHeaderScale()` hook
All header sizes computed at runtime from `useWindowDimensions()`:
- `buttonSize` — circle diameter, adapts to screen width (base 34-38px), dampened font scale growth
- `iconSize` — 53% of buttonSize
- `accessorySize` — 33% of buttonSize (chevrons, carets)
- `titleSize` — 44% of buttonSize (profile name text)

No static `Header` constants in `theme.ts`. Changing system font scale updates everything live.

### Rules
- ALWAYS use `HeaderIconButton` for header buttons — never inline Pressable with hardcoded sizes
- ALWAYS use `useHeaderScale()` for any header dimension — never hardcode pixel values
- New header buttons get haptics for free via `HeaderIconButton`

## Color System
Source: `constants/colors.ts` — dual palettes (`LightColors`, `DarkColors`).
Access via `useColors()` hook — never import `Colors` statically in components.
Bidirectional compile-time check: adding a key to either palette forces the other.
Opacity suffixes permitted for tints (e.g. `Colors.primary + '20'`).

### Light
- Surfaces: `#f8fafc` (bg) → `#ffffff` (surface) → `#f1f5f9` (surfaceSecondary)
- Primary: `#2563EB` (blue-600), accent: `#10b981` (emerald-500)
- Text: `#0f172a` / `#475569` / `#94a3b8`
- Borders: `#e2e8f0` (solid)

### Dark
- Surfaces: `#111827` (bg) → `#1e293b` (surface) → `#334155` (surfaceSecondary)
- Primary: `#60a5fa` (blue-400), accent: `#34d399` (emerald-400)
- Text: `#f8fafc` / `#94a3b8` / `#64748b`
- Borders: `rgba(255, 255, 255, 0.10)` (glow, not line)
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
Header uses `useHeaderScale()` — `titleSize` derived from `buttonSize`.
Weights: 400, 500, 600, 700 via `FontWeight` constants.

## Border Radius
Scale: 8 (sm), 12 (md), 16 (lg), 24 (xl), 9999 (full).
Always `borderCurve: 'continuous'` on rounded elements.

## Icons
`@expo/vector-icons` (Ionicons, Feather, MaterialCommunityIcons) via centralized `components/Icon.tsx`.
Exported `IconName` type for type-safe icon references.
Available icons: gearshape, arrow-up, paperclip, chat-fill, stethoscope, chevron-down, chevron-up, chevron-right, chevron-back, heart-clipboard, plus, people, doc-search, chat-bubbles, menu, pen-square, camera, image, document, close, checkmark-circle, close-circle, brain, pencil, trash.
When migrating to dev builds, swap internals to `expo-image` SF Symbols without changing call sites.

## Haptics
- `useHapticPress(onPress, style?)` hook — wraps any callback with iOS haptic feedback
- `HeaderIconButton` uses this automatically — no manual haptic code needed for header buttons
- Other interactive elements: guard with `process.env.EXPO_OS === 'ios'`
- Styles: `Light` for navigation/selection, `Medium` for send/confirm actions

## Interactive
- Press: `opacity: pressed ? 0.6–0.85 : 1`
- Active sidebar item: `primary + '15'` background, primary text color, semibold weight

## Component Patterns

### Chat Input (stacked layout)
Rounded container with `BorderRadius.xl`, 1px border, `backgroundColor: surface`. No heavy shadow.
Layout: TextInput on top (generous `Spacing.md` padding), toolbar row below.
Toolbar: `+` attach button left, send button right (36px circle, primary bg).
`hasAttachment` prop: shows "Image attached" indicator, tints + button primary, enables send without text.
`onAttach` opens `useAttachMenu()` action sheet (Camera / Photos / Files).

### Chat Bubble
User: primary bg, no border. Assistant: surface bg, 1px border.
`animate` prop: only true for newly sent messages, false for historical (prevents bounce on load).

### Sidebar Footer
User capsule (avatar initial + first name, pill shape, bordered) on left.
Circular `+` new-conversation button (48x48, primary bg) on right.
`justifyContent: 'space-between'`, generous bottom padding including safe area.

### Mode Toggle
Header icon-only button. Chat = primary tint (chat-fill icon), Diagnosis = accent tint (stethoscope icon).
Wraps `HeaderIconButton` with tint. Only visible on new conversation screen.

### Profile Pill
Header center. Name text + chevron-down (no avatar circle).
Height = `headerScale.buttonSize`. Font = `headerScale.titleSize`.
Tapping opens formSheet profile picker.

### FormSheet Modals
Use `ScrollView` (not `FlatList`) inside formSheets — known Expo bug with FlatList layout.
No `contentInsetAdjustmentBehavior` inside sheets. No `KeyboardAvoidingView` wrapping (iOS sheets handle keyboard natively).
`headerTintColor: Colors.text` on all formSheet screens (settings, profile-picker, profile/new).

### Loading State
Skeleton chat bubbles on themed background. No white flash, no spinner, no text.
