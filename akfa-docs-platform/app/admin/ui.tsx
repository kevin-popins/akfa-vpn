'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Eye, ImagePlus, LogOut, Plus, Save, ShieldCheck, ShieldOff, Trash2 } from 'lucide-react';

import type { Article, ArticleInput } from '@/lib/types';
import { slugify } from '@/lib/slug';

const emptyArticle: ArticleInput = {
  slug: '',
  title: '',
  description: '',
  section: 'Документация',
  sort_order: 100,
  status: 'draft',
  content: '',
};

type PreviewResponse = {
  html: string;
};

type TwoFactorState = {
  id: number;
  email: string;
  totp_enabled: boolean;
  totp_pending: boolean;
};

type TwoFactorSetup = {
  secret: string;
  otpauth_url: string;
  qr_data_url: string;
};

async function api<T>(path: string, csrf: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(path, {
    ...options,
    credentials: 'include',
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      'X-CSRF-Token': csrf,
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) throw new Error(data?.message || `HTTP ${response.status}`);
  return data as T;
}

export function AdminDashboard({ adminEmail, csrf }: { adminEmail: string; csrf: string }) {
  const [articles, setArticles] = useState<Article[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [form, setForm] = useState<ArticleInput>(emptyArticle);
  const [query, setQuery] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [previewHtml, setPreviewHtml] = useState('');
  const [origin, setOrigin] = useState('');
  const [twoFactor, setTwoFactor] = useState<TwoFactorState | null>(null);
  const [twoFactorSetup, setTwoFactorSetup] = useState<TwoFactorSetup | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState('');
  const [disablePassword, setDisablePassword] = useState('');
  const [twoFactorBusy, setTwoFactorBusy] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const selected = articles.find((article) => article.id === selectedId) || null;

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return articles;
    return articles.filter((article) =>
      [article.title, article.section, article.slug].some((value) => value.toLowerCase().includes(normalized)),
    );
  }, [articles, query]);

  async function loadArticles() {
    const rows = await api<Article[]>('/admin/api/articles', csrf);
    setArticles(rows);
    if (!selectedId && rows[0]) selectArticle(rows[0]);
  }

  async function loadTwoFactor() {
    const state = await api<TwoFactorState>('/admin/api/settings/2fa', csrf);
    setTwoFactor(state);
  }

  function selectArticle(article: Article) {
    setSelectedId(article.id);
    setForm({
      slug: article.slug,
      title: article.title,
      description: article.description,
      section: article.section,
      sort_order: article.sort_order,
      status: article.status,
      content: article.content,
    });
    setPreviewHtml('');
  }

  function newArticle() {
    setSelectedId(null);
    setForm(emptyArticle);
    setPreviewHtml('');
  }

  useEffect(() => {
    setOrigin(window.location.origin);
    loadArticles().catch((err) => setError(err instanceof Error ? err.message : 'Статьи недоступны'));
    loadTwoFactor().catch(() => null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function update<K extends keyof ArticleInput>(key: K, value: ArticleInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function setTitle(value: string) {
    setForm((current) => ({
      ...current,
      title: value,
      slug: current.slug || slugify(value),
    }));
  }

  function wrap(prefix: string, suffix = prefix) {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = form.content.slice(start, end) || 'текст';
    const next = `${form.content.slice(0, start)}${prefix}${selectedText}${suffix}${form.content.slice(end)}`;
    update('content', next);
  }

  function insert(text: string) {
    const textarea = textareaRef.current;
    if (!textarea) {
      update('content', `${form.content}\n${text}`);
      return;
    }
    const start = textarea.selectionStart;
    const next = `${form.content.slice(0, start)}${text}${form.content.slice(start)}`;
    update('content', next);
  }

  async function save() {
    setSaving(true);
    setMessage('');
    setError('');
    try {
      const payload = { ...form, slug: form.slug || slugify(form.title) };
      const saved = selected
        ? await api<Article>(`/admin/api/articles/${selected.id}`, csrf, { method: 'PUT', body: JSON.stringify(payload) })
        : await api<Article>('/admin/api/articles', csrf, { method: 'POST', body: JSON.stringify(payload) });
      setMessage('Статья сохранена');
      await loadArticles();
      selectArticle(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Статья не сохранена');
    } finally {
      setSaving(false);
    }
  }

  async function startTwoFactor() {
    setTwoFactorBusy(true);
    setMessage('');
    setError('');
    try {
      const setup = await api<TwoFactorSetup>('/admin/api/settings/2fa/start', csrf, { method: 'POST' });
      setTwoFactorSetup(setup);
      await loadTwoFactor();
      setMessage('Отсканируйте QR-код и подтвердите 6-значный код. 2FA включится только после подтверждения.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось начать настройку 2FA');
    } finally {
      setTwoFactorBusy(false);
    }
  }

  async function confirmTwoFactor() {
    setTwoFactorBusy(true);
    setMessage('');
    setError('');
    try {
      const state = await api<TwoFactorState>('/admin/api/settings/2fa/confirm', csrf, {
        method: 'POST',
        body: JSON.stringify({ code: twoFactorCode }),
      });
      setTwoFactor(state);
      setTwoFactorSetup(null);
      setTwoFactorCode('');
      setMessage('2FA включена');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось подтвердить 2FA');
    } finally {
      setTwoFactorBusy(false);
    }
  }

  async function disableTwoFactor() {
    setTwoFactorBusy(true);
    setMessage('');
    setError('');
    try {
      const state = await api<TwoFactorState>('/admin/api/settings/2fa/disable', csrf, {
        method: 'POST',
        body: JSON.stringify({ password: disablePassword }),
      });
      setTwoFactor(state);
      setTwoFactorSetup(null);
      setDisablePassword('');
      setMessage('2FA отключена');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось отключить 2FA');
    } finally {
      setTwoFactorBusy(false);
    }
  }

  async function remove() {
    if (!selected || !confirm(`Удалить статью "${selected.title}"?`)) return;
    setSaving(true);
    setMessage('');
    setError('');
    try {
      await api(`/admin/api/articles/${selected.id}`, csrf, { method: 'DELETE' });
      setMessage('Статья удалена');
      setSelectedId(null);
      setForm(emptyArticle);
      await loadArticles();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Статья не удалена');
    } finally {
      setSaving(false);
    }
  }

  async function preview() {
    const response = await api<PreviewResponse>('/admin/api/preview', csrf, {
      method: 'POST',
      body: JSON.stringify({ content: form.content }),
    });
    setPreviewHtml(response.html);
  }

  async function uploadImage(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const body = new FormData();
    body.append('file', file);
    try {
      const response = await api<{ url: string }>('/admin/api/uploads', csrf, { method: 'POST', body });
      insert(`\n![Изображение](${response.url})\n`);
      setMessage('Изображение загружено');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Изображение не загружено');
    } finally {
      event.target.value = '';
    }
  }

  async function logout() {
    await api('/admin/api/logout', csrf, { method: 'POST' }).catch(() => null);
    window.location.href = '/admin/login';
  }

  const publicUrl = form.slug ? `${origin || ''}/docs/${form.slug}` : '';

  return (
    <div className="admin-shell">
      <div className="admin-wrap">
        <header className="admin-header">
          <div>
            <div className="brand">
              <span className="brand-mark">A</span>
              <span>AKFA Docs Admin</span>
            </div>
            <p style={{ color: 'var(--muted)', marginBottom: 0 }}>{adminEmail}</p>
          </div>
          <button className="btn secondary" onClick={logout}>
            <LogOut size={16} /> Выйти
          </button>
        </header>

        {message ? <div className="message success">{message}</div> : null}
        {error ? <div className="message error">{error}</div> : null}

        <div className="admin-grid" style={{ marginTop: 16 }}>
          <aside className="admin-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
              <h2 style={{ margin: 0 }}>Статьи</h2>
              <button className="btn" onClick={newArticle}>
                <Plus size={16} /> Создать
              </button>
            </div>
            <input className="search-input" style={{ margin: '14px 0' }} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск" />
            <div className="article-list">
              {filtered.map((article) => (
                <button className={article.id === selectedId ? 'active' : ''} key={article.id} onClick={() => selectArticle(article)}>
                  <strong>{article.title}</strong>
                  <br />
                  <span style={{ color: 'var(--muted)' }}>{article.section} · {article.status === 'published' ? 'Опубликована' : 'Черновик'}</span>
                </button>
              ))}
            </div>
          </aside>

          <main className="admin-card">
            <section className="security-panel">
              <div>
                <h2 style={{ margin: 0 }}>Безопасность</h2>
                <p style={{ color: 'var(--muted)', marginTop: 6, marginBottom: 0 }}>
                  Двухфакторная защита для входа в админку.
                </p>
              </div>
              {twoFactor?.totp_enabled ? (
                <div className="twofa-box">
                  <span className="status-pill success"><ShieldCheck size={15} /> 2FA включена</span>
                  <div className="field">
                    <label>Пароль для отключения</label>
                    <input value={disablePassword} onChange={(event) => setDisablePassword(event.target.value)} type="password" />
                  </div>
                  <button className="btn danger" type="button" onClick={disableTwoFactor} disabled={twoFactorBusy || !disablePassword}>
                    <ShieldOff size={16} /> Отключить 2FA
                  </button>
                </div>
              ) : (
                <div className="twofa-box">
                  <span className="status-pill">2FA выключена</span>
                  {!twoFactorSetup ? (
                    <button className="btn" type="button" onClick={startTwoFactor} disabled={twoFactorBusy}>
                      <ShieldCheck size={16} /> Включить 2FA
                    </button>
                  ) : (
                    <div className="twofa-setup">
                      <p style={{ color: 'var(--muted)', marginTop: 0 }}>2FA включится только после подтверждения кода.</p>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={twoFactorSetup.qr_data_url} alt="QR-код 2FA" />
                      <code>{twoFactorSetup.secret}</code>
                      <div className="field">
                        <label>6-значный код</label>
                        <input
                          value={twoFactorCode}
                          onChange={(event) => setTwoFactorCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
                          inputMode="numeric"
                        />
                      </div>
                      <button className="btn" type="button" onClick={confirmTwoFactor} disabled={twoFactorBusy || twoFactorCode.length !== 6}>
                        Подтвердить
                      </button>
                    </div>
                  )}
                </div>
              )}
            </section>

            <div className="form-grid">
              <div className="field">
                <label>Заголовок</label>
                <input value={form.title} onChange={(event) => setTitle(event.target.value)} />
              </div>
              <div className="field">
                <label>Slug</label>
                <input value={form.slug} onChange={(event) => update('slug', slugify(event.target.value))} />
              </div>
              <div className="field">
                <label>Публичный URL</label>
                <div className="public-url-row">
                  <input value={publicUrl} readOnly placeholder="/docs/slug" />
                  {form.slug ? (
                    <a className="btn secondary" href={`/docs/${form.slug}`} target="_blank" rel="noreferrer">
                      Открыть
                    </a>
                  ) : null}
                </div>
              </div>
              <div className="field">
                <label>Раздел</label>
                <input value={form.section} onChange={(event) => update('section', event.target.value)} />
              </div>
              <div className="field">
                <label>Порядок</label>
                <input type="number" value={form.sort_order} onChange={(event) => update('sort_order', Number(event.target.value))} />
              </div>
              <div className="field">
                <label>Статус</label>
                <select value={form.status} onChange={(event) => update('status', event.target.value as ArticleInput['status'])}>
                  <option value="draft">Черновик</option>
                  <option value="published">Опубликована</option>
                </select>
              </div>
              <div className="field">
                <label>Описание</label>
                <input value={form.description} onChange={(event) => update('description', event.target.value)} />
              </div>
              <div className="field wide">
                <label>Редактор</label>
                <div className="editor-toolbar">
                  <button className="btn secondary" type="button" onClick={() => wrap('**')}>Жирный</button>
                  <button className="btn secondary" type="button" onClick={() => wrap('*')}>Курсив</button>
                  <button className="btn secondary" type="button" onClick={() => insert('\n## Заголовок\n')}>H2</button>
                  <button className="btn secondary" type="button" onClick={() => insert('\n### Подзаголовок\n')}>H3</button>
                  <button className="btn secondary" type="button" onClick={() => insert('\n- пункт списка\n')}>Список</button>
                  <button className="btn secondary" type="button" onClick={() => insert('\n> Важная заметка\n')}>Блок</button>
                  <button className="btn secondary" type="button" onClick={() => insert('[текст ссылки](https://example.com)')}>Ссылка</button>
                  <button className="btn secondary" type="button" onClick={() => insert('<a class="btn" href="https://example.com">Кнопка</a>')}>Кнопка-ссылка</button>
                  <label className="btn secondary" style={{ cursor: 'pointer' }}>
                    <ImagePlus size={16} /> Изображение
                    <input hidden type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={uploadImage} />
                  </label>
                </div>
                <textarea ref={textareaRef} value={form.content} onChange={(event) => update('content', event.target.value)} />
              </div>
            </div>

            <div className="button-row">
              <button className="btn" onClick={save} disabled={saving}>
                <Save size={16} /> {saving ? 'Сохраняем...' : 'Сохранить'}
              </button>
              <button className="btn secondary" onClick={preview}>
                <Eye size={16} /> Предпросмотр
              </button>
              {selected ? (
                <button className="btn danger" onClick={remove} disabled={saving}>
                  <Trash2 size={16} /> Удалить
                </button>
              ) : null}
            </div>

            {previewHtml ? (
              <div>
                <h2>Предпросмотр</h2>
                <div className="content preview" dangerouslySetInnerHTML={{ __html: previewHtml }} />
              </div>
            ) : null}
          </main>
        </div>
      </div>
    </div>
  );
}
