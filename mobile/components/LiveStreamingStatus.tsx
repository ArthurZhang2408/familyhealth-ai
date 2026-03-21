import { useEffect, useMemo, useRef, useState } from 'react';
import { View } from 'react-native';
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { StatusWordCycler } from '@/components/StatusWordCycler';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize } from '@/constants/theme';
import { exitFade, enterFade } from '@/constants/animations';
import type { AgentStep } from '@/types/api';

// ── Phase logic ───────────────────────────────────────────────────────

type Phase = 'waiting' | 'agent' | 'thinking' | 'done';

const PHASE_ORDER: Record<Phase, number> = { waiting: 0, agent: 1, thinking: 2, done: 3 };

// ── Word pools ────────────────────────────────────────────────────────
// Full pool passed to cycler for all phases. Cycler handles rotation.

const POOLS = {
  chat: {
    waiting: [
      'Let me think...',
      'One moment...',
      'Working on it...',
      'Looking into this...',
      'Give me a second...',
      'Hmm, let me see...',
    ],
    web_search: [
      'Looking that up...',
      'Searching for answers...',
      'Checking reliable sources...',
      'Finding information...',
      'Browsing a few sources...',
      'Digging into this...',
    ],
    search_patient_memory: [
      'Checking what I remember...',
      'Looking at our past conversations...',
      'Reviewing your history...',
      'Checking my notes on you...',
      'Looking back at what you told me...',
    ],
    save_to_memory: [
      'Making a note of that...',
      'Remembering this for next time...',
      'Saving that to your record...',
    ],
    thinking: [
      'Thinking about this...',
      'Working on a thoughtful answer...',
      'Considering the best way to explain...',
      'Putting together an answer...',
      'Weighing the options...',
      'Thinking this through...',
    ],
    reassurance: ['Still working on a thorough response...'],
  },
  diagnosis: {
    waiting: [
      'Let me think...',
      'One moment...',
      'Working on it...',
      'Looking into this...',
      'Give me a second...',
      'Considering the details...',
    ],
    web_search: [
      'Checking medical literature...',
      'Reviewing clinical studies...',
      'Looking at the evidence...',
      'Searching medical databases...',
      'Reading the latest research...',
      'Checking clinical guidelines...',
      'Looking at published cases...',
    ],
    search_patient_memory: [
      'Reviewing your health history...',
      'Checking your past visits...',
      'Looking at your medical records...',
      'Reviewing what you\'ve told me...',
      'Checking your medical background...',
      'Looking at your health timeline...',
    ],
    save_to_memory: [
      'Noting that in your record...',
      'Updating your health notes...',
      'Remembering this for future visits...',
    ],
    thinking: [
      'Putting the pieces together...',
      'Considering the possibilities...',
      'Working through this carefully...',
      'Analyzing your symptoms...',
      'Weighing the clinical picture...',
      'Narrowing down what this could be...',
      'Thinking through the differentials...',
    ],
    reassurance: ['Still working on a thorough response...'],
  },
} as const;

type PoolKey = keyof (typeof POOLS)['chat'];

// ── Component ─────────────────────────────────────────────────────────

interface Props {
  isBusy: boolean;
  isStreaming: boolean;
  agentSteps: AgentStep[];
  thinkingContent: string;
  streamingContent: string;
  sendStartTime: number | null;
  mode: 'chat' | 'diagnosis';
}

const TIMER_CAP_S = 30;

export function LiveStreamingStatus({
  isBusy,
  isStreaming,
  agentSteps,
  thinkingContent,
  streamingContent,
  sendStartTime,
  mode,
}: Props) {
  const Colors = useColors();
  const [elapsed, setElapsed] = useState(0);
  const prevPhaseRef = useRef<Phase>('waiting');
  const lastToolRef = useRef<string | undefined>(undefined);

  // Reset on new send
  useEffect(() => {
    if (sendStartTime) {
      prevPhaseRef.current = 'waiting';
      lastToolRef.current = undefined;
    }
  }, [sendStartTime]);

  // Determine raw phase
  let rawPhase: Phase = 'waiting';
  if (streamingContent.length > 0 || !isBusy) {
    rawPhase = 'done';
  } else if (thinkingContent.length > 0) {
    rawPhase = 'thinking';
  } else if (agentSteps.some((s) => s.status === 'active')) {
    rawPhase = 'agent';
  }

  // Sticky forward phase
  const phase: Phase = PHASE_ORDER[rawPhase] >= PHASE_ORDER[prevPhaseRef.current]
    ? rawPhase
    : prevPhaseRef.current;

  // Haptic on phase transition
  useEffect(() => {
    if (phase !== prevPhaseRef.current && phase !== 'done') {
      if (process.env.EXPO_OS === 'ios') {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      }
    }
    prevPhaseRef.current = phase;
  }, [phase]);

  // Track latest tool (sticky)
  const activeTool = agentSteps.findLast((s) => s.status === 'active')?.tool;
  if (activeTool && activeTool !== lastToolRef.current) {
    lastToolRef.current = activeTool;
  }
  const currentTool = activeTool ?? lastToolRef.current;

  // Timer
  useEffect(() => {
    if (!sendStartTime) {
      setElapsed(0);
      return;
    }
    const tick = () => setElapsed(Math.floor((Date.now() - sendStartTime) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [sendStartTime]);

  // Build words for the cycler
  const capped = elapsed >= TIMER_CAP_S;

  const words = useMemo(() => {
    if (capped) return [...POOLS[mode].reassurance];

    const modePool = POOLS[mode];

    if (phase === 'thinking') {
      return [...modePool.thinking];
    }

    if (phase === 'agent' && currentTool) {
      const key = currentTool as PoolKey;
      const pool = key in modePool ? modePool[key] : modePool.waiting;
      return [...pool];
    }

    return [...modePool.waiting];
  }, [mode, phase, currentTool, capped]);

  if (phase === 'done') return null;

  return (
    <Animated.View
      entering={enterFade()}
      exiting={exitFade()}
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingVertical: Spacing.sm,
      }}
    >
      <StatusWordCycler words={words} slowPulse={capped} />
      {elapsed >= 1 && !capped && (
        <Animated.Text
          entering={FadeIn.duration(200)}
          exiting={FadeOut.duration(150)}
          style={{
            fontSize: FontSize.xs,
            color: Colors.textMuted,
            fontVariant: ['tabular-nums'],
          }}
        >
          {elapsed}s
        </Animated.Text>
      )}
    </Animated.View>
  );
}
