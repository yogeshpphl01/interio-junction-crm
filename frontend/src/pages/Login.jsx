/*
  <page name="Login" route="/login">
    <purpose>Email/password sign-in. Delegates to useAuth().login and redirects
    to "/" on success. Fields start BLANK (no credential hints) for security.</purpose>
  </page>
*/
import { useState } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import ForgotPasswordModal from "@/components/ForgotPasswordModal";

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showForgot, setShowForgot] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    const res = await login(email, password);
    setSubmitting(false);
    if (res.ok) navigate("/");
    else setError(res.error);
  };

  return (
    <div className="min-h-screen flex paper-bg">
      <div className="flex-1 flex items-center justify-center px-6 py-10">
        <div className="w-full max-w-md" data-testid="login-card">
          <div className="flex items-center gap-3 mb-12">
            <div className="w-10 h-10 rounded-md bg-clay flex items-center justify-center">
              <span className="font-serif text-white text-2xl leading-none">i</span>
            </div>
            <div>
              <div className="font-serif text-xl text-ink leading-none">Interio Junction</div>
              <div className="text-[10px] tracking-[0.18em] uppercase text-ink-muted mt-1">Workshop CRM</div>
            </div>
          </div>

          <div className="mb-10 animate-fade-up">
            <div className="text-[10px] uppercase tracking-[0.22em] text-clay font-semibold mb-3">
              Welcome back
            </div>
            <h1 className="font-serif text-4xl sm:text-5xl text-ink leading-none">
              Where every<br />
              <span className="italic">project</span> finds its grain.
            </h1>
            <p className="mt-5 text-ink-soft text-sm max-w-sm leading-relaxed">
              Sign in to manage modular interior projects from first enquiry through factory handover.
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4" data-testid="login-form">
            <div>
              <label className="text-[11px] uppercase tracking-[0.12em] text-ink-soft font-semibold">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                data-testid="login-email-input"
                className="mt-1.5 w-full bg-bone-paper border border-edge rounded-md px-3 py-2.5 text-ink focus:border-clay focus:ring-2 focus:ring-clay/20 outline-none"
                placeholder="you@interiojunction.com"
              />
            </div>
            <div>
              <div className="flex items-center justify-between">
                <label className="text-[11px] uppercase tracking-[0.12em] text-ink-soft font-semibold">Password</label>
                <button
                  type="button"
                  onClick={() => setShowForgot(true)}
                  data-testid="login-forgot-password-link"
                  className="text-[11px] text-clay hover:text-clay-deep font-medium"
                >
                  Forgot password?
                </button>
              </div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                data-testid="login-password-input"
                className="mt-1.5 w-full bg-bone-paper border border-edge rounded-md px-3 py-2.5 text-ink focus:border-clay focus:ring-2 focus:ring-clay/20 outline-none"
                placeholder="••••••••"
              />
            </div>
            {error && (
              <div data-testid="login-error" className="text-sm text-clay-deep bg-clay/10 border border-clay/30 rounded-md px-3 py-2">
                {error}
              </div>
            )}
            <button
              type="submit"
              disabled={submitting}
              data-testid="login-submit-btn"
              className="w-full bg-clay hover:bg-clay-deep disabled:opacity-60 text-white rounded-md py-2.5 font-medium transition-colors"
            >
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>
      </div>

      <div className="hidden lg:block flex-1 relative">
        <img
          src="https://images.pexels.com/photos/30857234/pexels-photo-30857234.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=900&w=1200"
          alt="Modern workshop kitchen"
          className="absolute inset-0 w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-tr from-[#2A2421]/40 via-transparent to-clay/10" />
        <div className="absolute bottom-12 left-12 right-12 text-white">
          <div className="text-[10px] uppercase tracking-[0.22em] text-bone-deep">A workshop-precision CRM</div>
          <div className="font-serif text-3xl mt-2 max-w-md leading-tight">
            Six measured stages, from enquiry to handover.
          </div>
        </div>
      </div>

      <Toaster richColors position="top-right" />
      {showForgot && <ForgotPasswordModal initialEmail={email} onClose={() => setShowForgot(false)} />}
    </div>
  );
}
