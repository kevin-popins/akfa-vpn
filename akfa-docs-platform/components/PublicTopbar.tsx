import Link from 'next/link';

import { listPublishedArticles } from '@/lib/db';
import { publicRoutes } from '@/lib/routes';

export function PublicTopbar() {
  const faq = listPublishedArticles().find((article) => article.section === 'FAQ');
  const faqHref = faq ? `/docs/${faq.slug}` : publicRoutes.faq;

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link href="/" className="brand">
          <span className="brand-mark">A</span>
          <span>AKFA VPN</span>
        </Link>
        <nav className="topnav" aria-label="Главная навигация">
          <Link href={publicRoutes.docs}>Документация</Link>
          <Link href={faqHref}>Решение проблем</Link>
          <Link href={faqHref}>FAQ</Link>
        </nav>
      </div>
    </header>
  );
}
