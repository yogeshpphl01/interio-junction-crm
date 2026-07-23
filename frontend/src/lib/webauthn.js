/*
  <module name="lib/webauthn" layer="frontend-data">
    <purpose>
      Thin wrappers around the WebAuthn/FIDO2 ceremonies (passkeys, A8). Uses
      @simplewebauthn/browser, whose JSON in/out matches the backend's py_webauthn
      verifier exactly, so options pass straight through and the credential the
      browser produces posts back verbatim.
    </purpose>
  </module>
*/
import { startRegistration, startAuthentication } from "@simplewebauthn/browser";
import { api } from "@/lib/api";

export function passkeySupported() {
  // WebAuthn needs a secure context (HTTPS, or localhost in dev). On a plain
  // http://IP host the ceremony would throw, so hide the passkey UI there —
  // it appears once the app is served over HTTPS with WEBAUTHN_* configured.
  return typeof window !== "undefined" && !!window.PublicKeyCredential && window.isSecureContext;
}

// Enroll a passkey for the signed-in staff member.
export async function registerPasskey(label) {
  const { data: options } = await api.post("/auth/passkey/register/options");
  const attResp = await startRegistration(options);
  await api.post("/auth/passkey/register/verify", { credential: attResp, label });
}

// Authenticate with a passkey → returns { user, access_token, refresh_token }.
export async function beginPasskeyLogin(email) {
  const { data: options } = await api.post("/auth/passkey/login/options", { email });
  const authResp = await startAuthentication(options);
  const { data } = await api.post("/auth/passkey/login/verify", { credential: authResp });
  return data;
}

export async function listPasskeys() {
  const { data } = await api.get("/auth/passkey/list");
  return data.passkeys || [];
}

export async function deletePasskey(id) {
  await api.delete(`/auth/passkey/${id}`);
}

// The user cancelling the browser prompt throws a DOMException — treat as a soft
// cancel rather than an error to surface.
export function isPasskeyCancel(e) {
  return e?.name === "NotAllowedError" || e?.name === "AbortError";
}
