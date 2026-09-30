/**
 * LoginGate: minimal authentication surface shown before any protected workspaces.
 * Displays only when the user is not authenticated. Accepts a bearer token
 * into memory, calls /api/v1/session/me, and stores the server-resolved identity.
 */
import { type FormEvent, useState } from "react";
import { authenticateWithToken } from "../stores/identity";

export function LoginGate() {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!token.trim()) {
      setError("Please enter your access token.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const ok = await authenticateWithToken(token.trim());
      if (!ok) {
        setError("Authentication failed. Check your token and try again.");
      }
    } catch {
      setError("Connection error. Is the server running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-gate">
      <div className="login-card">
        <div className="login-logo">⬡</div>
        <h1 className="login-title">AIOS-0X Command Center</h1>
        <p className="login-subtitle">Enter your access token to continue</p>
        <form onSubmit={handleSubmit}>
          <input
            type="password"
            className="login-input"
            placeholder="Bearer token"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            autoFocus
            disabled={loading}
          />
          {error && <p className="login-error">{error}</p>}
          <button
            type="submit"
            className="login-button"
            disabled={loading || !token.trim()}
          >
            {loading ? "Authenticating…" : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
