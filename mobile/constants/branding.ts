import type { IconName } from '@/components/Icon';

/**
 * Centralized branding constants.
 *
 * Every user-facing string, tagline, and icon choice lives here so a
 * rebrand only touches this file (+ app.json for native identifiers).
 */

// ── App identity ────────────────────────────────────────────────────
export const AppName = 'Salk';
export const AppTagline = "Your family's health companion";

// ── Screen copy ─────────────────────────────────────────────────────
// Prompt suggestions are now generated dynamically by services/suggestions.ts
export const Copy = {
  signup: {
    title: 'Create account',
    subtitle: "Your family's health, one app",
  },
  welcome: {
    title: 'Welcome',
    subtitle:
      'Your AI health companion for the whole family. Create a profile to get started.',
    cta: 'Get started',
  },
  home: {
    chat: {
      title: 'Health Chat',
      subtitle:
        'Ask any health question about medications, conditions, or test results.',
      placeholder: 'Ask a health question\u2026',
    },
    diagnosis: {
      title: 'AI Diagnosis',
      subtitle:
        'Describe symptoms for a structured AI-assisted assessment.',
      placeholder: 'Describe your symptoms\u2026',
    },
  },
} as const;

// ── Brand icon ──────────────────────────────────────────────────────
export const BrandIcon: IconName = 'heart-clipboard';
export const BrandIconSize = 28;
export const BrandIconContainerSize = 56;

/** Login screen logo — rendered as an image, not an icon. */
export const LoginIcon = {
  containerSize: 64,
} as const;
