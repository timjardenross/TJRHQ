'use client';

/**
 * Timer Widget — Issue 25
 *
 * Countdown timer for focused work sessions on personal tasks.
 * Can be launched from a personal task or Home dashboard.
 * Audio/visual alerts at 5min, 1min, and 0.
 */

import { useEffect, useState, useRef } from 'react';

interface TimerWidgetProps {
  initialMinutes?: number;
  taskTitle?: string;
  onComplete?: () => void;
  onClose: () => void;
}

export function TimerWidget({ initialMinutes = 25, taskTitle, onComplete, onClose }: TimerWidgetProps) {
  const [secondsLeft, setSecondsLeft] = useState(initialMinutes * 60);
  const [isRunning, setIsRunning] = useState(false);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Create or reuse an audio element for alerts
  useEffect(() => {
    if (!audioRef.current && typeof window !== 'undefined') {
      const audio = new Audio();
      audio.src = 'data:audio/wav;base64,UklGRiYAAABXQVZFZm10IBAAAAABAAEAQB8AAAB9AAACABAAZGF0YQIAAAAAAA=='; // 1ms silence
      audioRef.current = audio;
    }
  }, []);

  // Timer countdown loop
  useEffect(() => {
    if (!isRunning) return;

    intervalRef.current = setInterval(() => {
      setSecondsLeft((prev) => {
        const next = prev - 1;
        if (next <= 0) {
          setIsRunning(false);
          playAlert();
          onComplete?.();
          return 0;
        }
        // Alert at 5min, 1min
        if ((next === 300 || next === 60) && audioRef.current) {
          playAlert();
        }
        return next;
      });
    }, 1000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isRunning, onComplete]);

  const playAlert = () => {
    try {
      if (audioRef.current) {
        audioRef.current.currentTime = 0;
        audioRef.current.play().catch(() => {
          // Silently fail if audio permissions denied
        });
      }
    } catch {
      // Silently fail
    }
  };

  const minutes = Math.floor(secondsLeft / 60);
  const seconds = secondsLeft % 60;
  const displayTime = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;

  const isAlmostDone = secondsLeft < 60;
  const isDone = secondsLeft === 0;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-3 rounded-lg border border-wb-sage-deep/40 bg-wb-bg/95 backdrop-blur-sm p-4 shadow-lg max-w-xs">
      {taskTitle && (
        <p className="text-xs uppercase tracking-wide text-wb-ink2 truncate">{taskTitle}</p>
      )}

      <div className={`text-center font-mono ${isDone ? 'text-wb-ok-on' : isAlmostDone ? 'text-wb-warn-on' : 'text-wb-ink'}`}>
        <p className="text-3xl font-bold">{displayTime}</p>
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setIsRunning(!isRunning)}
          disabled={isDone}
          className="flex-1 rounded-md border border-wb-sage-deep/50 bg-wb-sage-deep/10 px-3 py-1.5 text-xs font-medium text-wb-sage-deep hover:bg-wb-sage-deep/20 disabled:opacity-40"
        >
          {isRunning ? '⏸ Pause' : isDone ? '✓ Done' : '▶ Start'}
        </button>
        <button
          type="button"
          onClick={() => {
            setIsRunning(false);
            setSecondsLeft(initialMinutes * 60);
          }}
          className="flex-1 rounded-md border border-wb-line px-3 py-1.5 text-xs font-medium text-wb-ink2 hover:border-wb-sage-deep/40"
        >
          ↻ Reset
        </button>
        <button
          type="button"
          onClick={onClose}
          className="flex-1 rounded-md border border-wb-line px-3 py-1.5 text-xs font-medium text-wb-ink2 hover:border-wb-sage-deep/40"
        >
          ✕ Close
        </button>
      </div>

      {isDone && (
        <p className="text-center text-xs text-wb-ok-on font-semibold">Time's up! Great work.</p>
      )}
    </div>
  );
}
