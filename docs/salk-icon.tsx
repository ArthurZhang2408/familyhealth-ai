/**
 * Reference SVG icon for Salk — web/React version.
 * The native animated equivalent lives at mobile/components/AnimatedSalkIcon.tsx
 */

interface SalkIconProps {
  size?: number;
}

export function SalkIcon({ size = 120 }: SalkIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ filter: 'drop-shadow(0 4px 12px rgba(0, 0, 0, 0.1))' }}
    >
      {/* Background */}
      <rect width="120" height="120" rx="26" fill="url(#gradient)" />

      {/* Gradient Definitions */}
      <defs>
        <linearGradient id="gradient" x1="0" y1="0" x2="120" y2="120" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#3B82F6" />
          <stop offset="50%" stopColor="#2563EB" />
          <stop offset="100%" stopColor="#10B981" />
        </linearGradient>

        <linearGradient id="lightGradient" x1="0" y1="0" x2="120" y2="120" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0.1" />
        </linearGradient>
      </defs>

      {/* Light overlay for depth */}
      <rect width="120" height="120" rx="26" fill="url(#lightGradient)" />

      {/* Main Icon Design - Family circles with medical cross */}
      <g transform="translate(60, 60)">
        {/* Back circle (represents family member) */}
        <circle cx="-12" cy="8" r="16" fill="white" opacity="0.4" />

        {/* Right circle (represents family member) */}
        <circle cx="12" cy="8" r="16" fill="white" opacity="0.4" />

        {/* Front center circle with medical cross (represents primary user + health) */}
        <circle cx="0" cy="-8" r="20" fill="white" opacity="0.9" />

        {/* Medical Cross inside front circle */}
        <g transform="translate(0, -8)">
          {/* Vertical bar of cross */}
          <rect x="-2" y="-8" width="4" height="16" rx="2" fill="#2563EB" />
          {/* Horizontal bar of cross */}
          <rect x="-8" y="-2" width="16" height="4" rx="2" fill="#2563EB" />

          {/* Small accent circle in center for AI/tech feel */}
          <circle cx="0" cy="0" r="2.5" fill="#10B981" />
        </g>

        {/* Additional subtle accent circles for multi-profile concept */}
        <circle cx="-18" cy="-4" r="10" fill="white" opacity="0.3" />
        <circle cx="18" cy="-4" r="10" fill="white" opacity="0.3" />
      </g>

      {/* Subtle highlight on top edge for polish */}
      <path
        d="M26 0 H94 C108.359 0 120 11.641 120 26 V30 C120 15.641 108.359 4 94 4 H26 C11.641 4 0 15.641 0 30 V26 C0 11.641 11.641 0 26 0 Z"
        fill="white"
        opacity="0.2"
      />
    </svg>
  );
}
