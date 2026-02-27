export const Colors = {
  // Brand
  primary: '#0891b2',       // teal-600
  primaryDark: '#0e7490',   // teal-700
  primaryLight: '#cffafe',  // cyan-100
  accent: '#14b8a6',        // teal-500

  // Backgrounds
  background: '#f0f9ff',    // sky-50
  surface: '#ffffff',
  surfaceSecondary: '#f8fafc', // slate-50

  // Text
  text: '#0f172a',          // slate-900
  textSecondary: '#64748b', // slate-500
  textMuted: '#94a3b8',     // slate-400
  textInverse: '#ffffff',

  // Borders
  border: '#e2e8f0',        // slate-200
  borderFocus: '#0891b2',

  // Status
  error: '#ef4444',         // red-500
  errorLight: '#fee2e2',    // red-100
  warning: '#f59e0b',       // amber-500
  warningLight: '#fef3c7',  // amber-100
  success: '#10b981',       // emerald-500
  successLight: '#d1fae5',  // emerald-100
  info: '#3b82f6',          // blue-500
  infoLight: '#dbeafe',     // blue-100

  // Urgency (for diagnosis)
  urgencyLow: '#10b981',
  urgencyMedium: '#f59e0b',
  urgencyHigh: '#f97316',
  urgencyEmergency: '#ef4444',

  // Relationship badges
  relationshipSelf: '#8b5cf6',     // violet-500
  relationshipParent: '#0891b2',   // teal-600
  relationshipSpouse: '#ec4899',   // pink-500
  relationshipChild: '#f59e0b',    // amber-500
  relationshipSibling: '#10b981',  // emerald-500
  relationshipOther: '#64748b',    // slate-500
} as const;
