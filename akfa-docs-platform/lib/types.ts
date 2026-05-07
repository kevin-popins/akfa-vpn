export type ArticleStatus = 'draft' | 'published';

export type Article = {
  id: number;
  slug: string;
  title: string;
  description: string;
  section: string;
  sort_order: number;
  status: ArticleStatus;
  content: string;
  created_at: string;
  updated_at: string;
};

export type ArticleInput = {
  slug: string;
  title: string;
  description: string;
  section: string;
  sort_order: number;
  status: ArticleStatus;
  content: string;
};

export type AdminUser = {
  id: number;
  email: string;
  password_hash: string;
  totp_secret: string | null;
  pending_totp_secret: string | null;
  totp_enabled: number;
  totp_confirmed_at: string | null;
  created_at: string;
};
