import Link from 'next/link';

import { DocsSidebar } from '@/components/DocsSidebar';
import { PublicTopbar } from '@/components/PublicTopbar';
import { listPublishedArticles } from '@/lib/db';

export const dynamic = 'force-dynamic';

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const params = await searchParams;
  const q = (params.q || '').trim().toLowerCase();
  const articles = listPublishedArticles();
  const rows = q
    ? articles.filter((article) =>
        [article.title, article.description, article.section, article.content].some((value) =>
          value.toLowerCase().includes(q),
        ),
      )
    : [];

  return (
    <div className="shell">
      <PublicTopbar />
      <div className="docs-layout">
        <DocsSidebar articles={articles} />
        <main className="article">
          <h1>Поиск</h1>
          <p className="description">Найдите инструкцию по названию, разделу или тексту статьи.</p>
          <form className="search-box" action="/search">
            <input className="search-input" name="q" defaultValue={q} placeholder="Например: Windows или лимит устройств" />
          </form>
          <div className="content">
            {q ? <h2>Результаты</h2> : null}
            {rows.map((article) => (
              <p key={article.id}>
                <Link href={`/docs/${article.slug}`}>
                  <strong>{article.section}</strong> — {article.title}
                </Link>
                <br />
                <span>{article.description}</span>
              </p>
            ))}
            {q && rows.length === 0 ? <p>Ничего не найдено. Попробуйте другой запрос.</p> : null}
          </div>
        </main>
        <aside className="toc" />
      </div>
    </div>
  );
}
