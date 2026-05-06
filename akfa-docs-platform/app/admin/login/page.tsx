'use client';

import { useState } from 'react';

export default function AdminLoginPage() {
  const [email, setEmail] = useState('admin@example.com');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [tempToken, setTempToken] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setMessage('');
    try {
      const response = await fetch('/admin/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || 'Не удалось войти');
      if (data.requires_2fa) {
        setTempToken(data.temp_token);
        setMessage('');
        return;
      }
      window.location.href = '/admin';
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось войти');
    } finally {
      setLoading(false);
    }
  }

  async function submit2fa(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setMessage('');
    try {
      const response = await fetch('/admin/api/login/2fa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ temp_token: tempToken, code }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || 'Не удалось проверить код');
      window.location.href = '/admin';
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось проверить код');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-box">
      <form className="admin-card" onSubmit={tempToken ? submit2fa : submit}>
        <div className="brand" style={{ marginBottom: 24 }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="brand-logo admin-brand-logo" src="/assets/akfa-logo.svg" alt="AKFA VPN" />
        </div>
        {message ? <div className="message error">{message}</div> : null}
        {tempToken ? (
          <div className="field" style={{ marginTop: 14 }}>
            <label>Код из приложения</label>
            <input
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="6 цифр"
            />
          </div>
        ) : (
          <>
            <div className="field" style={{ marginTop: 14 }}>
              <label>Email</label>
              <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="username" />
            </div>
            <div className="field" style={{ marginTop: 14 }}>
              <label>Пароль</label>
              <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" />
            </div>
          </>
        )}
        <button className="btn" style={{ width: '100%', marginTop: 18 }} disabled={loading}>
          {loading ? 'Проверяем...' : tempToken ? 'Подтвердить вход' : 'Войти'}
        </button>
        {tempToken ? (
          <button className="btn secondary" style={{ width: '100%', marginTop: 10 }} type="button" onClick={() => setTempToken('')}>
            Ввести пароль заново
          </button>
        ) : null}
      </form>
    </div>
  );
}
