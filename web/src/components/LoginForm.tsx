import { useState, type FormEvent } from 'react';
import { GoogleLogin, type CredentialResponse } from '@react-oauth/google';
import { login, loginWithGoogle } from '../services/auth';

interface LoginFormProps {
  onSuccess: () => void;
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

export function LoginForm({ onSuccess }: LoginFormProps) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await login({ password });
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogleSuccess(response: CredentialResponse) {
    if (!response.credential) {
      setError('No credential received from Google');
      return;
    }

    setError(null);
    setLoading(true);

    try {
      await loginWithGoogle({ credential: response.credential });
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Google login failed');
    } finally {
      setLoading(false);
    }
  }

  function handleGoogleError() {
    setError('Google sign-in failed. Please try again.');
  }

  return (
    <div className="login-form-container">
      <form className="login-form" onSubmit={handleSubmit}>
        <h1>Remote Control</h1>
        <p className="login-subtitle">Enter password to connect</p>

        {error && <div className="error-message">{error}</div>}

        <div className="form-group">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            required
            disabled={loading}
            autoFocus
          />
        </div>

        <button type="submit" disabled={loading || !password}>
          {loading ? 'Connecting...' : 'Connect'}
        </button>

        {GOOGLE_CLIENT_ID && (
          <>
            <div className="login-divider">
              <span>or</span>
            </div>

            <div className="google-login-wrapper">
              <GoogleLogin
                onSuccess={handleGoogleSuccess}
                onError={handleGoogleError}
                theme="filled_black"
                size="large"
                width="320"
                text="signin_with"
                shape="rectangular"
              />
            </div>
          </>
        )}
      </form>
    </div>
  );
}
