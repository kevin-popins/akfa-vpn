import { notFound } from 'next/navigation';

import { ArticleView } from '@/components/ArticleView';
import { getPublishedArticle } from '@/lib/db';

export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const article = getPublishedArticle(slug);
  if (!article) return {};
  return {
    title: article.title,
    description: article.description,
  };
}

export default async function DocsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const article = getPublishedArticle(slug);
  if (!article) notFound();
  return <ArticleView article={article} />;
}
