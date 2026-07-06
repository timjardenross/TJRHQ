// Retired — mock-data page duplicating the real Knowledge Hub.
// MSN-0328 (WP-B): this page rendered lib/mockData.knowledgeArticles, a
// fixed mock set never connected to any live table — /knowledge and
// /knowledge-library are the real, live-data destinations.
import { redirect } from 'next/navigation';
export default function KnowledgeBasePage() {
  redirect('/knowledge');
}
