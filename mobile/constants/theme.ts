export const Spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

export const FontSize = {
  xs: 12,
  sm: 14,
  md: 16,
  lg: 18,
  xl: 22,
  xxl: 28,
  xxxl: 34,
} as const;

export const FontWeight = {
  regular: '400' as const,
  medium: '500' as const,
  semibold: '600' as const,
  bold: '700' as const,
};

export const BorderRadius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  full: 9999,
} as const;

export const Shadow = {
  sm: {
    boxShadow: '0 1px 2px rgba(0, 0, 0, 0.05)',
  },
  md: {
    boxShadow: '0 4px 6px rgba(0, 0, 0, 0.07)',
  },
  lg: {
    boxShadow: '0 10px 15px rgba(0, 0, 0, 0.1)',
  },
} as const;

export const Theme = {
  Spacing,
  FontSize,
  FontWeight,
  BorderRadius,
  Shadow,
} as const;
