import { useMemo } from 'react';
import { Platform } from 'react-native';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, BorderRadius } from '@/constants/theme';

/**
 * Theme-aware styles for @ronradtke/react-native-markdown-display.
 * Automatically adapts to light/dark mode via useColors().
 */
export function useMarkdownStyles() {
  const Colors = useColors();

  return useMemo(
    () => ({
      body: {
        color: Colors.text,
        fontSize: FontSize.md,
        lineHeight: 24,
      },
      heading1: {
        color: Colors.text,
        fontSize: FontSize.xxl,
        fontWeight: '700' as const,
        marginTop: Spacing.lg,
        marginBottom: Spacing.sm,
      },
      heading2: {
        color: Colors.text,
        fontSize: FontSize.xl,
        fontWeight: '700' as const,
        marginTop: Spacing.lg,
        marginBottom: Spacing.sm,
      },
      heading3: {
        color: Colors.text,
        fontSize: FontSize.lg,
        fontWeight: '600' as const,
        marginTop: Spacing.md,
        marginBottom: Spacing.xs,
      },
      heading4: {
        color: Colors.text,
        fontSize: FontSize.md,
        fontWeight: '600' as const,
        marginTop: Spacing.md,
        marginBottom: Spacing.xs,
      },
      heading5: {
        color: Colors.text,
        fontSize: FontSize.sm,
        fontWeight: '600' as const,
        marginTop: Spacing.sm,
        marginBottom: Spacing.xs,
      },
      heading6: {
        color: Colors.textSecondary,
        fontSize: FontSize.sm,
        fontWeight: '600' as const,
        marginTop: Spacing.sm,
        marginBottom: Spacing.xs,
      },
      strong: {
        fontWeight: '600' as const,
      },
      em: {
        fontStyle: 'italic' as const,
      },
      link: {
        color: Colors.primary,
        textDecorationLine: 'none' as const,
      },
      blockquote: {
        backgroundColor: Colors.surfaceSecondary,
        borderLeftWidth: 3,
        borderLeftColor: Colors.primary,
        paddingHorizontal: Spacing.md,
        paddingVertical: Spacing.sm,
        marginVertical: Spacing.sm,
        borderRadius: BorderRadius.sm,
      },
      code_inline: {
        backgroundColor: Colors.surfaceSecondary,
        color: Colors.text,
        fontSize: FontSize.sm,
        fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
        paddingHorizontal: Spacing.xs,
        paddingVertical: 2,
        borderRadius: 4,
      },
      code_block: {
        backgroundColor: Colors.surfaceSecondary,
        color: Colors.text,
        fontSize: FontSize.sm,
        fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
        padding: Spacing.md,
        borderRadius: BorderRadius.sm,
        marginVertical: Spacing.sm,
      },
      fence: {
        backgroundColor: Colors.surfaceSecondary,
        color: Colors.text,
        fontSize: FontSize.sm,
        fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
        padding: Spacing.md,
        borderRadius: BorderRadius.sm,
        marginVertical: Spacing.sm,
      },
      bullet_list: {
        marginVertical: Spacing.xs,
      },
      ordered_list: {
        marginVertical: Spacing.xs,
      },
      list_item: {
        marginVertical: 2,
      },
      hr: {
        backgroundColor: Colors.border,
        height: 1,
        marginVertical: Spacing.md,
      },
      table: {
        borderWidth: 1,
        borderColor: Colors.border,
        borderRadius: BorderRadius.sm,
        marginVertical: Spacing.sm,
      },
      thead: {
        backgroundColor: Colors.surfaceSecondary,
      },
      th: {
        padding: Spacing.sm,
        borderWidth: 0.5,
        borderColor: Colors.border,
        fontWeight: '600' as const,
      },
      td: {
        padding: Spacing.sm,
        borderWidth: 0.5,
        borderColor: Colors.border,
      },
      paragraph: {
        marginTop: 0,
        marginBottom: Spacing.sm,
      },
    }),
    [Colors],
  );
}
