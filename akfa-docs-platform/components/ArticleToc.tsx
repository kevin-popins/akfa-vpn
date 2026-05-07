export function ArticleToc({ toc }: { toc: Array<{ id: string; text: string; level: number }> }) {
  return (
    <aside className="toc">
      <div className="toc-card">
        <p className="toc-title">На странице</p>
        {toc.length ? (
          toc.map((item) => (
            <a
              key={`${item.id}-${item.text}`}
              className="toc-link"
              style={{ paddingLeft: item.level === 3 ? 22 : 10 }}
              href={`#${item.id}`}
            >
              {item.text}
            </a>
          ))
        ) : (
          <div className="toc-link">Оглавление появится в статьях с заголовками.</div>
        )}
      </div>
    </aside>
  );
}
