/*
 * {{PROJECT_NAME}} — sign-in.
 *
 * Replaces the template's static auth markup with a form that actually
 * authenticates. The session is persisted by the core, so a device that signs
 * in while connected keeps working through an outage for as long as its access
 * token lives.
 */
'use client';

import { useAuth } from '@hybrid/offline-core';
import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';

export function SignIn() {
  const login = useAuth((state) => state.login);
  const router = useRouter();

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
      router.push('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed.');
    } finally {
      setPending(false);
    }
  }

  return (
    <main
      style={{
        minHeight: '100dvh',
        display: 'grid',
        placeItems: 'center',
        padding: 'var(--ax-space-6)',
      }}
    >
      <section className="ax-card" style={{ width: 'min(420px, 100%)' }}>
        <div className="ax-card__header">
          <h1
            style={{
              margin: 0,
              fontFamily: 'var(--ax-font-display)',
              fontSize: 'var(--ax-text-lg)',
              color: 'var(--ax-text-strong)',
            }}
          >
            {{PROJECT_NAME}}
          </h1>
        </div>

        <form className="ax-card__body" onSubmit={handleSubmit}>
          <label style={{ display: 'block', marginBottom: 'var(--ax-space-4)' }}>
            <span style={{ display: 'block', fontSize: 'var(--ax-text-sm)', color: 'var(--ax-text-muted)', marginBottom: 'var(--ax-space-2)' }}>
              Username
            </span>
            <input
              className="ax-input"
              style={{ width: '100%' }}
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
            />
          </label>

          <label style={{ display: 'block', marginBottom: 'var(--ax-space-4)' }}>
            <span style={{ display: 'block', fontSize: 'var(--ax-text-sm)', color: 'var(--ax-text-muted)', marginBottom: 'var(--ax-space-2)' }}>
              Password
            </span>
            <input
              className="ax-input"
              style={{ width: '100%' }}
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
          </label>

          {error && (
            <p style={{ margin: '0 0 var(--ax-space-4)', fontSize: 'var(--ax-text-sm)', color: 'var(--ax-danger, #b33)' }}>
              {error}
            </p>
          )}

          <button type="submit" className="ax-btn ax-btn--primary" disabled={pending} style={{ width: '100%' }}>
            <span className="ax-btn__label">{pending ? 'Signing in…' : 'Sign in'}</span>
          </button>

          <p style={{ margin: 'var(--ax-space-4) 0 0', fontSize: 'var(--ax-text-sm)', color: 'var(--ax-text-muted)' }}>
            Seeded users: <code>mor_user</code>, <code>mut_user</code> — <code>demo1234</code>
          </p>
        </form>
      </section>
    </main>
  );
}
