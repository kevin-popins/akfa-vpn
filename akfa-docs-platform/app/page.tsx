import Link from 'next/link';

import { PublicTopbar } from '@/components/PublicTopbar';
import { listPublishedArticles } from '@/lib/db';
import { platformCards } from '@/lib/routes';

export const dynamic = 'force-dynamic';

export default function HomePage() {
  const articles = listPublishedArticles();
  const articleBySection = new Map(articles.map((article) => [article.section, article]));

  return (
    <div className="shell">
      <PublicTopbar />
      <section className="home-hero">
        <div className="hero-panel">
          <span className="eyebrow">База знаний</span>
          <h1>AKFA VPN — инструкции для подключения</h1>
          <p>
            Выберите своё устройство и следуйте пошаговой инструкции. Здесь собраны ссылки на установку приложений,
            подключение профиля и ответы на частые вопросы.
          </p>
          <form className="search-box" action="/search">
            <input className="search-input" name="q" placeholder="Поиск по инструкциям" />
          </form>
        </div>
      </section>
      <section className="platform-grid">
        {platformCards.map((card) => (
          <Link className="platform-card" href={articleBySection.get(card.title)?.slug ? `/docs/${articleBySection.get(card.title)?.slug}` : card.href} key={card.title}>
            <h2>{card.title}</h2>
            <p>{card.text}</p>
          </Link>
        ))}
      </section>
      <section className="home-hero" style={{ paddingTop: 0 }}>
        <div className="card" style={{ padding: 22 }}>
          <h2 style={{ marginTop: 0 }}>Все статьи</h2>
          <div style={{ display: 'grid', gap: 10 }}>
            {articles.map((article) => (
              <Link className="side-link" href={`/docs/${article.slug}`} key={article.id}>
                <strong>{article.section}</strong> — {article.title}
              </Link>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
