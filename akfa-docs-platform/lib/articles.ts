import type { Article } from './types';

export const SECTION_ORDER = ['Android / Happ', 'iPhone / iPad / Happ', 'Windows / FlClashX', 'macOS / FlClashX', 'FAQ'];

export function groupArticles(articles: Article[]) {
  const groups = new Map<string, Article[]>();
  for (const article of articles) {
    const rows = groups.get(article.section) || [];
    rows.push(article);
    groups.set(article.section, rows);
  }
  return [...groups.entries()].sort(([a], [b]) => {
    const ai = SECTION_ORDER.indexOf(a);
    const bi = SECTION_ORDER.indexOf(b);
    if (ai !== -1 || bi !== -1) return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    return a.localeCompare(b, 'ru');
  });
}

export function articleHref(article: Article) {
  return `/docs/${article.slug}`;
}
