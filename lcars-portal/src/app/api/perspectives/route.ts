import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';
import fs from 'node:fs/promises';
import path from 'node:path';

const PERSPECTIVES_DIR = path.join(process.cwd(), 'perspectives');

interface PerspectiveMeta {
  label: string;
  category: string;
}

const REGISTRY: Record<string, PerspectiveMeta> = {
  'obama':           { label: 'Barack Obama',         category: 'politics'   },
  'picard':          { label: 'Jean-Luc Picard',      category: 'command'    },
  'covey':           { label: 'Stephen Covey',         category: 'business'   },
  'churchill':       { label: 'Winston Churchill',     category: 'politics'   },
  'drucker':         { label: 'Peter Drucker',         category: 'business'   },
  'sun-tzu':         { label: 'Sun Tzu',               category: 'strategy'   },
  'feynman':         { label: 'Richard Feynman',       category: 'science'    },
  'frankl':          { label: 'Viktor Frankl',         category: 'philosophy' },
  'brown':           { label: 'Brené Brown',           category: 'resilience' },
  'jobs':            { label: 'Steve Jobs',            category: 'business'   },
  'nooyi':           { label: 'Indra Nooyi',           category: 'business'   },
  'ardern':          { label: 'Jacinda Ardern',        category: 'politics'   },
  'ginsburg':        { label: 'Ruth Bader Ginsburg',   category: 'politics'   },
  'thich-nhat-hanh':      { label: 'Thich Nhat Hanh',      category: 'philosophy' },
  'editorial-strategist': { label: 'Editorial Strategist', category: 'content'   },
};

export async function GET(request: NextRequest) {
  const supabase = await createSupabaseServerClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const { searchParams } = new URL(request.url);
  const name = searchParams.get('name');
  const category = searchParams.get('category');

  if (name) {
    const safe = name.replace(/[^a-z0-9-]/g, '');
    try {
      const content = await fs.readFile(path.join(PERSPECTIVES_DIR, `${safe}.md`), 'utf-8');
      const meta = REGISTRY[safe];
      return NextResponse.json({ name: safe, label: meta?.label ?? safe, category: meta?.category ?? 'other', content });
    } catch {
      return NextResponse.json({ error: 'Perspective not found' }, { status: 404 });
    }
  }

  try {
    const files = await fs.readdir(PERSPECTIVES_DIR);
    let perspectives = files
      .filter((f) => f.endsWith('.md'))
      .map((f) => {
        const key = f.replace('.md', '');
        const meta = REGISTRY[key];
        return { name: key, label: meta?.label ?? key, category: meta?.category ?? 'other' };
      })
      .sort((a, b) => a.label.localeCompare(b.label));

    if (category) {
      perspectives = perspectives.filter((p) => p.category === category);
    }

    return NextResponse.json({ perspectives });
  } catch {
    return NextResponse.json({ perspectives: [] });
  }
}

// POST — synthesise multiple perspective responses into a single unified view
export async function POST(request: NextRequest) {
  const supabase = await createSupabaseServerClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  try {
    const body = await request.json() as {
      question: string;
      responses: { label: string; response: string }[];
    };

    if (!body.question || !body.responses?.length) {
      return NextResponse.json({ error: 'question and responses required' }, { status: 400 });
    }

    const panel = body.responses.map((r) => `### ${r.label}\n${r.response}`).join('\n\n---\n\n');

    const systemPrompt = `You are a neutral facilitator synthesising the collective wisdom of a distinguished advisory panel.

You have received individual perspectives from each advisor on the question below. Your task is to:

1. **Common Ground** — surface the themes and insights that multiple advisors share
2. **Key Tensions** — name where advisors meaningfully disagree and why that disagreement matters
3. **Synthesis** — a single integrated recommendation that honours the strongest insights from across the panel
4. **What each voice uniquely adds** — one sentence per advisor on their distinctive contribution

Be direct, honest about disagreement, and structured. Do not flatten real differences into false consensus. If the panel divides, say so and explain what the divide reveals.`;

    const userMessage = `**Question:** ${body.question}\n\n---\n\n${panel}`;

    const aiRes = await fetch(`${process.env.NEXTAUTH_URL ?? ''}/api/ai/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', cookie: request.headers.get('cookie') ?? '' },
      body: JSON.stringify({
        messages: [{ role: 'user', content: userMessage }],
        systemPrompt,
        stream: false,
      }),
    });

    const aiData = await aiRes.json() as { content?: string; error?: string };
    if (aiData.error) return NextResponse.json({ error: aiData.error }, { status: 500 });

    return NextResponse.json({ synthesis: aiData.content });
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 });
  }
}
