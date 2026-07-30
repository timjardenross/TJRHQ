/**
 * Hook to launch the global timer from any component.
 *
 * Usage:
 *   const launchTimer = useTimerLauncher();
 *   launchTimer(25, "My Task");
 */

export function useTimerLauncher() {
  return (minutes?: number, taskTitle?: string) => {
    if (typeof window !== 'undefined' && (window as any).__tjr_launch_timer) {
      (window as any).__tjr_launch_timer(minutes, taskTitle);
    }
  };
}
