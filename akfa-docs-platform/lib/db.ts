import fs from 'node:fs';
import Database from 'better-sqlite3';
import bcrypt from 'bcryptjs';

import { appConfig } from './config';
import { canonicalArticleSlugs, initialArticles, legacySeedSlugs } from './seed-content';
import type { AdminUser, Article, ArticleInput } from './types';

let db: Database.Database | null = null;
const CURRENT_SEED_REVISION = 1;

const primaryLegacySlugsBySeedKey: Record<string, string[]> = {
  'android-happ': ['android-happ-kak-podklyuchit-vpn'],
  'iphone-happ': ['iphone-ipad-happ-kak-podklyuchit-vpn'],
  'windows-fclashx': ['windows-fclashx-kak-podklyuchit-vpn'],
  'macos-fclashx': ['macos-fclashx-kak-podklyuchit-vpn'],
  faq: [],
};

export function getDb() {
  if (db) return db;
  fs.mkdirSync(appConfig.dataDir, { recursive: true });
  fs.mkdirSync(appConfig.uploadDir, { recursive: true });
  db = new Database(appConfig.dbPath);
  db.pragma('journal_mode = WAL');
  migrate(db);
  seed(db);
  return db;
}

function migrate(database: Database.Database) {
  database.exec(`
    CREATE TABLE IF NOT EXISTS admins (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      totp_secret TEXT,
      pending_totp_secret TEXT,
      totp_enabled INTEGER NOT NULL DEFAULT 0,
      totp_confirmed_at TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS articles (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      slug TEXT NOT NULL UNIQUE,
      title TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      section TEXT NOT NULL DEFAULT 'Документация',
      sort_order INTEGER NOT NULL DEFAULT 100,
      status TEXT NOT NULL DEFAULT 'draft',
      content TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);
    CREATE INDEX IF NOT EXISTS idx_articles_section_sort ON articles(section, sort_order);
  `);
  addColumn(database, 'admins', 'totp_secret', 'TEXT');
  addColumn(database, 'admins', 'pending_totp_secret', 'TEXT');
  addColumn(database, 'admins', 'totp_enabled', 'INTEGER NOT NULL DEFAULT 0');
  addColumn(database, 'admins', 'totp_confirmed_at', 'TEXT');
  addColumn(database, 'articles', 'seed_key', 'TEXT');
  addColumn(database, 'articles', 'seed_revision', 'INTEGER NOT NULL DEFAULT 0');
}

function addColumn(database: Database.Database, table: string, column: string, definition: string) {
  const columns = database.prepare(`PRAGMA table_info(${table})`).all() as Array<{ name: string }>;
  if (!columns.some((item) => item.name === column)) {
    database.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${definition}`);
  }
}

function seed(database: Database.Database) {
  const adminCount = database.prepare('SELECT COUNT(*) as count FROM admins').get() as { count: number };
  if (adminCount.count === 0) {
    database.prepare('INSERT INTO admins (email, password_hash) VALUES (?, ?)').run(
      appConfig.adminEmail,
      bcrypt.hashSync(appConfig.adminPassword, 12),
    );
  }

  const insertStarter = database.prepare(`
    INSERT INTO articles (slug, title, description, section, sort_order, status, content, seed_key, seed_revision, updated_at)
    VALUES (@slug, @title, @description, @section, @sort_order, @status, @content, @seed_key, @seed_revision, CURRENT_TIMESTAMP)
  `);
  const updateStarter = database.prepare(`
    UPDATE articles
    SET slug = @slug,
        title = @title,
        description = @description,
        section = @section,
        sort_order = @sort_order,
        status = @status,
        content = @content,
        seed_key = @seed_key,
        seed_revision = @seed_revision,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = @id
  `);
  const hideLegacy = database.prepare(`
    UPDATE articles
    SET status = 'draft', updated_at = CURRENT_TIMESTAMP
    WHERE slug = ? AND slug NOT IN (${canonicalArticleSlugs.map(() => '?').join(',')})
  `);
  const transaction = database.transaction((rows: ArticleInput[]) => {
    for (const row of rows) {
      const seedKey = row.slug;
      const legacySlugs = primaryLegacySlugsBySeedKey[seedKey] || [];
      const starter = findStarterArticle(database, seedKey, row.slug, legacySlugs);
      if (!starter) {
        insertStarter.run({ ...row, seed_key: seedKey, seed_revision: CURRENT_SEED_REVISION });
        continue;
      }
      if (starter.seed_revision >= CURRENT_SEED_REVISION) continue;

      const shouldUseCanonicalSlug = starter.slug === row.slug || legacySlugs.includes(starter.slug);
      updateStarter.run({
        ...row,
        id: starter.id,
        slug: shouldUseCanonicalSlug ? row.slug : starter.slug,
        seed_key: seedKey,
        seed_revision: CURRENT_SEED_REVISION,
      });
    }
    for (const slug of legacySeedSlugs) hideLegacy.run(slug, ...canonicalArticleSlugs);
  });
  transaction(initialArticles());
}

function findStarterArticle(database: Database.Database, seedKey: string, canonicalSlug: string, legacySlugs: string[]) {
  const bySeedKey = database.prepare('SELECT id, slug, seed_revision FROM articles WHERE seed_key = ? ORDER BY id LIMIT 1').get(seedKey) as
    | { id: number; slug: string; seed_revision: number }
    | undefined;
  if (bySeedKey) return bySeedKey;

  const candidates = [canonicalSlug, ...legacySlugs];
  return database
    .prepare(
      `SELECT id, slug, seed_revision FROM articles
       WHERE slug IN (${candidates.map(() => '?').join(',')})
       ORDER BY CASE WHEN slug = ? THEN 0 ELSE 1 END, id
       LIMIT 1`,
    )
    .get(...candidates, canonicalSlug) as { id: number; slug: string; seed_revision: number } | undefined;
}

export function listPublishedArticles() {
  return getDb()
    .prepare('SELECT * FROM articles WHERE status = ? ORDER BY section, sort_order, title')
    .all('published') as Article[];
}

export function listAllArticles() {
  return getDb().prepare('SELECT * FROM articles ORDER BY section, sort_order, title').all() as Article[];
}

export function getPublishedArticle(slug: string) {
  return getDb().prepare('SELECT * FROM articles WHERE slug = ? AND status = ?').get(slug, 'published') as Article | undefined;
}

export function getArticle(slug: string) {
  return getDb().prepare('SELECT * FROM articles WHERE slug = ?').get(slug) as Article | undefined;
}

export function getArticleById(id: number) {
  return getDb().prepare('SELECT * FROM articles WHERE id = ?').get(id) as Article | undefined;
}

export function createArticle(input: ArticleInput) {
  const result = getDb()
    .prepare(`
      INSERT INTO articles (slug, title, description, section, sort_order, status, content, updated_at)
      VALUES (@slug, @title, @description, @section, @sort_order, @status, @content, CURRENT_TIMESTAMP)
    `)
    .run(input);
  return getArticleById(Number(result.lastInsertRowid));
}

export function updateArticle(id: number, input: ArticleInput) {
  getDb()
    .prepare(`
      UPDATE articles
      SET slug = @slug,
          title = @title,
          description = @description,
          section = @section,
          sort_order = @sort_order,
          status = @status,
          content = @content,
          updated_at = CURRENT_TIMESTAMP
      WHERE id = @id
    `)
    .run({ ...input, id });
  return getArticleById(id);
}

export function deleteArticle(id: number) {
  getDb().prepare('DELETE FROM articles WHERE id = ?').run(id);
}

export function findAdminByEmail(email: string) {
  return getDb().prepare('SELECT * FROM admins WHERE email = ?').get(email) as AdminUser | undefined;
}

export function findAdminById(id: number) {
  return getDb().prepare('SELECT * FROM admins WHERE id = ?').get(id) as AdminUser | undefined;
}

export function updateAdminTotpPending(id: number, secret: string) {
  getDb()
    .prepare('UPDATE admins SET pending_totp_secret = ? WHERE id = ?')
    .run(secret, id);
  return findAdminById(id);
}

export function confirmAdminTotp(id: number, secret: string) {
  getDb()
    .prepare(`
      UPDATE admins
      SET totp_secret = ?,
          pending_totp_secret = NULL,
          totp_enabled = 1,
          totp_confirmed_at = CURRENT_TIMESTAMP
      WHERE id = ?
    `)
    .run(secret, id);
  return findAdminById(id);
}

export function disableAdminTotp(id: number) {
  getDb()
    .prepare(`
      UPDATE admins
      SET totp_secret = NULL,
          pending_totp_secret = NULL,
          totp_enabled = 0,
          totp_confirmed_at = NULL
      WHERE id = ?
    `)
    .run(id);
  return findAdminById(id);
}
