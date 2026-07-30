import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const EXTRACTED_TEXT_PREVIEW_CHARS = 4000;
const CHUNK_PREVIEW_COUNT = 3;

// USS-TJR-MSN-0205D: single document detail — includes a bounded preview
// of extracted_text and the first few chunks, but never the raw embedding
// vectors (large, no UI use).
export async function GET(
  _request: NextRequest,
  { params }: { params: { id: string } },
) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) {
    return NextResponse.json({ error: 'Document ID required' }, { status: 400 });
  }

  try {
    const supabase = await createSupabaseServerClient();

    const { data: doc, error: docErr } = await supabase
      .from('processing_documents')
      .select('*')
      .eq('id', id)
      .maybeSingle();
    if (docErr) throw docErr;
    if (!doc) {
      return NextResponse.json({ error: 'Document not found', id }, { status: 404 });
    }

    const fullText: string = doc.extracted_text ?? '';
    const truncated = fullText.length > EXTRACTED_TEXT_PREVIEW_CHARS;

    const { data: chunks, error: chunksErr } = await supabase
      .from('processing_chunks')
      .select('id, chunk_index, chunk_text, embedding_model, embedded_at')
      .eq('document_id', id)
      .order('chunk_index', { ascending: true })
      .limit(CHUNK_PREVIEW_COUNT);
    if (chunksErr) throw chunksErr;

    return NextResponse.json({
      document: {
        ...doc,
        extracted_text: fullText.slice(0, EXTRACTED_TEXT_PREVIEW_CHARS),
        extracted_text_truncated: truncated,
      },
      chunk_preview: chunks ?? [],
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Failed to load document', detail }, { status: 500 });
  }
}
