import Link from 'next/link';

import { articleHref, groupArticles } from '@/lib/articles';
import type { Article } from '@/lib/types';

export function DocsSidebar({ articles, activeSlug }: { articles: Article[]; activeSlug?: string }) {
  return (
    <aside className="sidebar">
      <div className="side-card">
        <p className="side-title">Разделы</p>
        {groupArticles(articles).map(([section, rows]) => (
          <div key={section}>
            <div className="side-section">{section}</div>
            {rows.map((article) => (
              <Link
                key={article.id}
                href={articleHref(article)}
                className={`side-link ${article.slug === activeSlug ? 'active' : ''}`}
              >
                {article.title}
              </Link>
            ))}
          </div>
        ))}
      </div>
    </aside>
  );
}
