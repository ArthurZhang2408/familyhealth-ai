import React from 'react';
import { View, Text, Pressable, Appearance } from 'react-native';
import { AnimatedSalkIcon } from './AnimatedSalkIcon';
import { logger } from '@/services/logger';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { LightColors, DarkColors } from '@/constants/colors';

interface State {
  hasError: boolean;
}

/**
 * Screen-level error boundary — catches rendering crashes and shows
 * a branded recovery screen instead of a white screen.
 *
 * Uses Appearance API directly (class components can't use hooks).
 */
export class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  State
> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    logger.error('app', 'Screen crash', {
      error: error.message,
      stack: info.componentStack?.slice(0, 500),
    });
  }

  handleRestart = () => {
    this.setState({ hasError: false });
  };

  render() {
    if (this.state.hasError) {
      const Colors =
        Appearance.getColorScheme() === 'dark' ? DarkColors : LightColors;

      return (
        <View
          style={{
            flex: 1,
            backgroundColor: Colors.background,
            justifyContent: 'center',
            alignItems: 'center',
            padding: Spacing.xl,
          }}
        >
          <AnimatedSalkIcon size={64} />
          <Text
            style={{
              fontSize: FontSize.xl,
              fontWeight: FontWeight.bold,
              color: Colors.text,
              marginTop: Spacing.lg,
              textAlign: 'center',
            }}
          >
            Something went wrong
          </Text>
          <Text
            style={{
              fontSize: FontSize.md,
              color: Colors.textSecondary,
              marginTop: Spacing.sm,
              textAlign: 'center',
            }}
          >
            An unexpected error occurred. Tap below to try again.
          </Text>
          <Pressable
            onPress={this.handleRestart}
            style={({ pressed }) => ({
              marginTop: Spacing.lg,
              paddingVertical: Spacing.sm,
              paddingHorizontal: Spacing.lg,
              backgroundColor: Colors.primary,
              borderRadius: BorderRadius.md,
              opacity: pressed ? 0.8 : 1,
            })}
          >
            <Text
              style={{
                fontSize: FontSize.md,
                fontWeight: FontWeight.semibold,
                color: '#FFFFFF',
              }}
            >
              Try Again
            </Text>
          </Pressable>
        </View>
      );
    }

    return this.props.children;
  }
}
