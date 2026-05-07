'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { Menu, X } from 'lucide-react';

import type { Article } from '@/lib/types';

export function MobileDocsMenu({ articles, activeSlug }: { articles: Article[]; activeSlug?: string }) {
  const [open, setOpen] = useState(false);
  const grouped = useMemo(() => {
    return articles.reduce<Record<string, Article[]>>((acc, article) => {
      acc[article.section] = acc[article.section] || [];
      acc[article.section].push(article);
      return acc;
    }, {});
  }, [articles]);

  return (
    <div className="mobile-docs-menu">
      <button className="btn secondary mobile-menu-trigger" type="button" onClick={() => setOpen(true)}>
        <Menu size={18} /> Разделы
      </button>
      {open ? (
        <div className="mobile-drawer" role="dialog" aria-modal="true" aria-label="Навигация по документации">
          <button className="mobile-drawer-backdrop" type="button" aria-label="Закрыть меню" onClick={() => setOpen(false)} />
          <aside className="mobile-drawer-panel">
            <div className="mobile-drawer-head">
              <strong>Разделы</strong>
              <button className="btn secondary" type="button" onClick={() => setOpen(false)} aria-label="Закрыть меню">
                <X size={18} />
              </button>
            </div>
            {Object.entries(grouped).map(([section, rows]) => (
              <div key={section}>
                <h2 className="side-section">{section}</h2>
                {rows.map((article) => (
                  <Link
                    className={`side-link ${article.slug === activeSlug ? 'active' : ''}`}
                    href={`/docs/${article.slug}`}
                    key={article.id}
                    onClick={() => setOpen(false)}
                  >
                    {article.title}
                  </Link>
                ))}
              </div>
            ))}
          </aside>
        </div>
      ) : null}
    </div>
  );
}
