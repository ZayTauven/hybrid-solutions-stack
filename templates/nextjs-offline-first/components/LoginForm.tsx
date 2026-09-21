'use client';

import { useState, type FormEvent } from 'react';

import { useAuth } from '@/hooks/useAuth';

export function LoginForm() {
  const login = useAuth((state) => state.login);
  const [username, setUsername] = useState('mor_user');
  const [password, setPassword] = useState('demo1234');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);

    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed.');
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="card stack" onSubmit={handleSubmit}>
      <h2>Sign in</h2>

      <label className="stack">
        <span className="muted">Username</span>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
        />
      </label>

      <label className="stack">
        <span className="muted">Password</span>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
      </label>

      {error && <p className="error">{error}</p>}

      <div className="row">
        <button className="primary" type="submit" disabled={pending}>
          {pending ? 'Signing in…' : 'Sign in'}
        </button>
        <span className="muted">Seeded users: mor_user, mut_user — demo1234</span>
      </div>
    </form>
  );
}
