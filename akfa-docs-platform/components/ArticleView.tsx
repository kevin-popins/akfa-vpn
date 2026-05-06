import { ArticleToc } from './ArticleToc';
import { DocsSidebar } from './DocsSidebar';
import { MobileDocsMenu } from './MobileDocsMenu';
import { PublicTopbar } from './PublicTopbar';
import { extractToc, renderMarkdown } from '@/lib/markdown';
import { listPublishedArticles } from '@/lib/db';
import type { Article } from '@/lib/types';

function withHeadingIds(html: string, toc: Array<{ id: string; text: string; level: number }>) {
  let next = html;
  for (const item of toc) {
    const tag = `h${item.level}`;
    const escaped = item.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    next = next.replace(new RegExp(`<${tag}>\\s*${escaped}\\s*</${tag}>`), `<${tag} id="${item.id}">${item.text}</${tag}>`);
  }
  return next;
}

export function ArticleView({ article }: { article: Article }) {
  const articles = listPublishedArticles();
  const toc = extractToc(article.content);
  const html = withHeadingIds(renderMarkdown(article.content), toc);

  return (
    <div className="shell">
      <PublicTopbar />
      <MobileDocsMenu articles={articles} activeSlug={article.slug} />
      <div className="docs-layout">
        <div className="desktop-sidebar">
          <DocsSidebar articles={articles} activeSlug={article.slug} />
        </div>
        <main className="article">
          <h1>{article.title}</h1>
          <p className="description">{article.description}</p>
          <div className="content" dangerouslySetInnerHTML={{ __html: html }} />
        </main>
        <ArticleToc toc={toc} />
      </div>
    </div>
  );
}
