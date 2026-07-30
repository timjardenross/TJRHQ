'use client';

/**
 * Root Layout Client Wrapper — Issue 25 Integration
 *
 * Provides FocusMode context and TimerWidget at the root level,
 * available globally across all routes.
 */

import { ReactNode, useState } from 'react';
import { FocusModeProvider, FocusModeSensor } from '@/components/FocusMode';
import { TimerWidget } from '@/components/TimerWidget';

export function RootLayoutClient({ children }: { children: ReactNode }) {
  const [showTimer, setShowTimer] = useState(false);
  const [timerMinutes, setTimerMinutes] = useState(25);
  const [timerTaskTitle, setTimerTaskTitle] = useState<string | undefined>();

  const launchTimer = (minutes: number = 25, taskTitle?: string) => {
    setTimerMinutes(minutes);
    setTimerTaskTitle(taskTitle);
    setShowTimer(true);
  };

  const closeTimer = () => {
    setShowTimer(false);
  };

  // Expose timer launch globally via window object (for components that need it)
  if (typeof window !== 'undefined') {
    (window as any).__tjr_launch_timer = launchTimer;
  }

  return (
    <FocusModeProvider>
      <FocusModeSensor>
        {children}
        {showTimer && (
          <TimerWidget
            initialMinutes={timerMinutes}
            taskTitle={timerTaskTitle}
            onClose={closeTimer}
          />
        )}
      </FocusModeSensor>
    </FocusModeProvider>
  );
}
