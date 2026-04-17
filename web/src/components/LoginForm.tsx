import { useState } from 'react';
import { GoogleLogin, type CredentialResponse } from '@react-oauth/google';
import { loginWithGoogle } from '../services/auth';

interface LoginFormProps {
  onSuccess: () => void;
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

export function LoginForm({ onSuccess }: LoginFormProps) {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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
      <div className="login-form">
        <h1>Remote Control</h1>
        <p className="login-subtitle">Sign in with Google to connect</p>

        {error && <div className="error-message">{error}</div>}

        {GOOGLE_CLIENT_ID ? (
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
            {loading && <p className="login-subtitle">Signing in...</p>}
          </div>
        ) : (
          <div className="error-message">
            Google sign-in is not configured. Set <code>VITE_GOOGLE_CLIENT_ID</code> to enable login.
          </div>
        )}
      </div>
    </div>
  );
}
