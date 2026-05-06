import crypto from 'node:crypto';
import { cookies } from 'next/headers';
import bcrypt from 'bcryptjs';

import { appConfig } from './config';
import { findAdminByEmail, findAdminById } from './db';
import { verifyTotp } from './totp';

const SESSION_COOKIE = 'akfa_docs_session';
const CSRF_COOKIE = 'akfa_docs_csrf';
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 14;

type SessionPayload = {
  kind: 'session';
  adminId: number;
  exp: number;
};

type LoginChallengePayload = {
  kind: 'login_2fa';
  adminId: number;
  exp: number;
};

function base64url(input: Buffer | string) {
  return Buffer.from(input).toString('base64url');
}

function sign(value: string) {
  return crypto.createHmac('sha256', appConfig.sessionSecret).update(value).digest('base64url');
}

function encodeSession(payload: SessionPayload) {
  const body = base64url(JSON.stringify(payload));
  return `${body}.${sign(body)}`;
}

function decodeSession(value: string | undefined): SessionPayload | null {
  if (!value) return null;
  const [body, signature] = value.split('.');
  if (!body || !signature || sign(body) !== signature) return null;
  try {
    const payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8')) as SessionPayload;
    if (payload.kind !== 'session' || !payload.adminId || payload.exp < Math.floor(Date.now() / 1000)) return null;
    return payload;
  } catch {
    return null;
  }
}

export async function currentAdmin() {
  const jar = await cookies();
  const session = decodeSession(jar.get(SESSION_COOKIE)?.value);
  if (!session) return null;
  return findAdminById(session.adminId) || null;
}

export async function requireAdmin() {
  const admin = await currentAdmin();
  if (!admin) throw new Error('UNAUTHORIZED');
  return admin;
}

export async function verifyPassword(email: string, password: string) {
  const admin = findAdminByEmail(email.trim().toLowerCase());
  if (!admin || !(await bcrypt.compare(password, admin.password_hash))) return null;
  return admin;
}

export async function createSessionForAdmin(adminId: number) {
  const exp = Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS;
  const csrf = crypto.randomBytes(24).toString('base64url');
  const jar = await cookies();
  jar.set(SESSION_COOKIE, encodeSession({ kind: 'session', adminId, exp }), {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: SESSION_TTL_SECONDS,
  });
  jar.set(CSRF_COOKIE, csrf, {
    httpOnly: false,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: SESSION_TTL_SECONDS,
  });
  const admin = findAdminById(adminId);
  if (!admin) return null;
  return { admin: publicAdmin(admin), csrf };
}

export async function createSession(email: string, password: string) {
  const admin = await verifyPassword(email, password);
  if (!admin) return null;
  return createSessionForAdmin(admin.id);
}

export async function destroySession() {
  const jar = await cookies();
  jar.delete(SESSION_COOKIE);
  jar.delete(CSRF_COOKIE);
}

export async function assertCsrf(request: Request) {
  const jar = await cookies();
  const expected = jar.get(CSRF_COOKIE)?.value;
  const actual = request.headers.get('x-csrf-token');
  if (!expected || !actual || expected !== actual) {
    throw new Error('CSRF');
  }
}

export async function csrfToken() {
  const jar = await cookies();
  return jar.get(CSRF_COOKIE)?.value || '';
}

export function publicAdmin(admin: { id: number; email: string; totp_enabled?: number | boolean; pending_totp_secret?: string | null }) {
  return {
    id: admin.id,
    email: admin.email,
    totp_enabled: Boolean(admin.totp_enabled),
    totp_pending: Boolean(admin.pending_totp_secret),
  };
}

export function createLoginChallenge(adminId: number) {
  const exp = Math.floor(Date.now() / 1000) + 5 * 60;
  const body = base64url(JSON.stringify({ kind: 'login_2fa', adminId, exp }));
  return `${body}.${sign(body)}`;
}

export function verifyLoginChallenge(token: string | undefined) {
  if (!token) return null;
  const [body, signature] = token.split('.');
  if (!body || !signature || sign(body) !== signature) return null;
  try {
    const payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8')) as LoginChallengePayload;
    if (payload.kind !== 'login_2fa' || !payload.adminId || payload.exp < Math.floor(Date.now() / 1000)) return null;
    return payload;
  } catch {
    return null;
  }
}

export async function verifyPasswordForAdmin(adminId: number, password: string) {
  const admin = findAdminById(adminId);
  if (!admin) return false;
  return bcrypt.compare(password, admin.password_hash);
}

export function adminHasTotp(admin: { totp_enabled?: number | boolean; totp_secret?: string | null }) {
  return Boolean(admin.totp_enabled && admin.totp_secret);
}

export function verifyAdminTotp(admin: { totp_secret?: string | null }, code: string) {
  return Boolean(admin.totp_secret && verifyTotp(admin.totp_secret, code));
}
