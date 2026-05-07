import { marked } from 'marked';
import sanitizeHtml from 'sanitize-html';

export function renderMarkdown(content: string) {
  const raw = marked.parse(content || '', {
    async: false,
    gfm: true,
  }) as string;

  return sanitizeHtml(raw, {
    allowedTags: sanitizeHtml.defaults.allowedTags.concat(['img', 'h1', 'h2', 'h3']),
    allowedAttributes: {
      ...sanitizeHtml.defaults.allowedAttributes,
      a: ['href', 'name', 'target', 'rel', 'class'],
      img: ['src', 'alt', 'title', 'width', 'height'],
      code: ['class'],
    },
    allowedSchemes: ['http', 'https', 'mailto', 'tel'],
    transformTags: {
      a: (_tagName, attribs) => ({
        tagName: 'a',
        attribs: {
          ...attribs,
          target: attribs.href?.startsWith('/') ? '' : '_blank',
          rel: attribs.href?.startsWith('/') ? '' : 'noopener noreferrer',
        },
      }),
    },
  });
}

export function extractToc(content: string) {
  const rows: Array<{ id: string; text: string; level: number }> = [];
  for (const match of content.matchAll(/^(#{2,3})\s+(.+)$/gm)) {
    const text = match[2].replace(/[#*_`]/g, '').trim();
    const id = text
      .toLowerCase()
      .replace(/[^a-zа-я0-9]+/gi, '-')
      .replace(/^-+|-+$/g, '');
    rows.push({ id, text, level: match[1].length });
  }
  return rows;
}
