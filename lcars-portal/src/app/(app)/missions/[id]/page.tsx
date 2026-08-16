import { redirect } from 'next/navigation';

export default function MissionDetailPage({
  params,
}: {
  params: { id: string };
}) {
  redirect(`/mission-workbench/${encodeURIComponent(params.id)}`);
}
