import { redirect } from 'next/navigation';

// Moved 2026-10-18: the exercise catalogue is now the Exercises tab of Knowledge.
export default function ExerciseLibraryRedirect() {
  redirect('/knowledge-workbench?tab=exercises');
}
