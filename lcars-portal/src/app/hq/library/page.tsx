'use client';

import Link from 'next/link';
import { Suspense, useEffect, useState, type FormEvent } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useHq } from '@/lib/hq/HqProvider';
import { searchLibrary } from '@/lib/hq/data';
import { useAsync } from '@/lib/hq/useAsync';
import type { HqLibraryItem } from '@/lib/hq/model';
import { ErrorLine, Loading } from '../_components/ui';

const TYPES = ['All', 'Knowledge', 'Document', 'Intelligence', 'Brief', 'Content'] as const;

function Inner() {
  const router = useRouter();
  const params = useSearchParams();
  const q = params.get('q') ?? '';
  const [text, setText] = useState(q);
  const [type, setType] = useState<(typeof TYPES)[number]>('All');
  const { openNew } = useHq();
  const res = useAsync(() => searchLibrary(q), [q]);
  useEffect(() => setText(q), [q]);

  const items = (res.data?.items ?? []).filter((i) => type === 'All' || i.type === type);
  const places = new Set(items.map((i) => i.store));

  function submit(e: FormEvent) {
    e.preventDefault();
    const t = text.trim();
    router.replace(t ? `/hq/library?q=${encodeURIComponent(t)}` : '/hq/library', { scroll: false });
  }

  const row = (i: HqLibraryItem) => {
    const external = /^https?:\/\//.test(i.legacyHref);
    const body = (
      <>
        <span className="t">{i.title}</span>
        <span className="s">{i.excerpt}{i.date ? ` · ${new Date(i.date).toLocaleDateString()}` : ''}</span>
        <span className="r"><span className="hq-tag">{i.type}</span><span className="hq-pill info">{i.store}</span></span>
      </>
    );
    return external
      ? <a key={i.id} className="hq-row" href={i.legacyHref} target="_blank" rel="noopener noreferrer">{body}</a>
      : <Link key={i.id} className="hq-row" href={i.legacyHref}>{body}</Link>;
  };

  return (
    <>
      <div className="hq-head">
        <h1>Library</h1>
        <p className="hq-lead">Search knowledge, documents, saved intelligence, briefs and content. Each item stays where it is stored.</p>
      </div>
      <form onSubmit={submit} role="search">
        <label htmlFor="hq-lib-q" className="hq-muted" style={{ fontSize: '.84rem' }}>Search the library</label>
        <input id="hq-lib-q" className="hq-input" type="search" value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" placeholder="Search everything you have saved" />
      </form>
      <div className="hq-chips" role="group" aria-label="Type">
        {TYPES.map((t) => <button key={t} type="button" className="hq-chip" aria-pressed={type === t} onClick={() => setType(t)}>{t === 'All' ? 'All types' : t}</button>)}
      </div>
      {res.loading && <Loading what="results" />}
      {res.error && <ErrorLine what="the library" detail={res.error} />}
      {res.data && res.data.unavailable.length > 0 && <ErrorLine what={res.data.unavailable.join(', ')} />}
      {res.data && (
        <p className="hq-muted" style={{ fontSize: '.85rem' }} role="status">
          {q ? `${items.length} ${items.length === 1 ? 'result' : 'results'} across ${places.size} ${places.size === 1 ? 'place' : 'places'}` : 'Recent and saved'}
        </p>
      )}
      {res.data && items.length === 0 && (
        <div className="hq-quiet">Nothing matches. Try fewer words, or{' '}
          <button type="button" className="hq-link inline" onClick={() => openNew({ type: 'research', text: q, context: null })}>capture a research request</button> (it is not run automatically).
        </div>
      )}
      {items.map(row)}
      <div className="hq-quiet">HQ links to the original and keeps no second copy. Notion and other stores are not changed.</div>
    </>
  );
}

export default function HqLibrary() {
  return <Suspense fallback={<Loading what="the library" />}><Inner /></Suspense>;
}
