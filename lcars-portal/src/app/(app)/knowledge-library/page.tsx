import { redirect } from 'next/navigation';

export default function KnowledgeLibraryPage() {
  redirect('/knowledge-workbench?domain=library');
}
