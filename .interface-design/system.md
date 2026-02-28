# FamilyHealth AI — Design System

## Spacing
Grid: 4px base. Scale: 4 (xs), 8 (sm), 16 (md), 24 (lg), 32 (xl), 48 (xxl).
Source: `constants/theme.ts → Spacing`

## Typography
Sizes: 12 (xs), 14 (sm), 16 (md), 18 (lg), 22 (xl), 28 (xxl), 34 (xxxl).
Weights: 400, 500, 600, 700. Source: `constants/theme.ts → FontSize, FontWeight`

## Colors
Source: `constants/colors.ts → Colors`. No hardcoded hex values allowed.
Opacity suffixes (e.g. `Colors.primary + '20'`) are permitted for tints.

## Border Radius
Scale: 8 (sm), 12 (md), 16 (lg), 24 (xl), 9999 (full).
Always use `borderCurve: 'continuous'` unless capsule shape.

## Depth
Primary: 1px border (`Colors.border`). Secondary: `Shadow.sm` boxShadow for cards.
Never use legacy React Native shadow/elevation props.

## Interactive
Press feedback: `opacity: pressed ? 0.7–0.85 : 1`. Haptics: iOS only, Light/Medium/Success.

## Buttons
- Primary CTA: `Colors.primary` bg, `md` padding, `md` radius, `Shadow.sm`
- Send button: 44x44, `full` radius, `Colors.primary`
- Toggle: `full` radius, active = primary tint bg + primary border

## Cards
`Colors.surface` bg, `lg` radius, `md–lg` padding, `Shadow.sm`, `borderCurve: 'continuous'`

## Text
Headers: xl/xxl + bold. Body: md + regular. Labels: xs + semibold + muted + uppercase. Metadata: xs + muted.
