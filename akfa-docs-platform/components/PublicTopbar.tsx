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
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="brand-logo" src="/assets/akfa-logo.svg" alt="AKFA VPN" />
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
