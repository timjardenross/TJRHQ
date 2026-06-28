import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';
import fs from 'node:fs/promises';
import path from 'node:path';

const PERSPECTIVES_DIR = path.join(process.cwd(), 'perspectives');

const LABELS: Record<string, string> = {
  'obama': 'Barack Obama',
  'picard': 'Jean-Luc Picard',
  'covey': 'Stephen Covey',
  'churchill': 'Winston Churchill',
  'drucker': 'Peter Drucker',
  'marcus-aurelius': 'Marcus Aurelius',
};

export async function GET(request: NextRequest) {
  const supabase = await createSupabaseServerClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const { searchParams } = new URL(request.url);
  const name = searchParams.get('name');

  if (name) {
    // Return content of a single perspective
    const safe = name.replace(/[^a-z0-9-]/g, '');
    try {
      const content = await fs.readFile(path.join(PERSPECTIVES_DIR, `${safe}.md`), 'utf-8');
      return NextResponse.json({ name: safe, label: LABELS[safe] ?? safe, content });
    } catch {
      return NextResponse.json({ error: 'Perspective not found' }, { status: 404 });
    }
  }

  // List all available perspectives
  try {
    const files = await fs.readdir(PERSPECTIVES_DIR);
    const perspectives = files
      .filter((f) => f.endsWith('.md'))
      .map((f) => {
        const key = f.replace('.md', '');
        return { name: key, label: LABELS[key] ?? key };
      });
    return NextResponse.json({ perspectives });
  } catch {
    return NextResponse.json({ perspectives: [] });
  }
}
