"""OAuth for MCP clients, with Supabase Auth as the authorization server.

Supabase runs the OAuth 2.1 flow (client registration, /authorize, /token).
This server only has to say where that is and host the consent screen:

- /.well-known/oauth-protected-resource[/mcp] tells an MCP client which
  authorization server issues tokens for /mcp (RFC 9728). A 401 from /mcp
  points here in its WWW-Authenticate header.
- /oauth/consent is where Supabase sends the browser mid-flow, with an
  authorization_id. You sign in with the same email and password as the
  Android app, see which app is asking, and approve or deny.

The tokens Supabase issues are ordinary Supabase user JWTs, so server/auth.py
verifies them unchanged, including the COURTSIDE_ALLOWED_EMAILS check.

Supabase setup: Authentication > OAuth Server: enable it, allow dynamic
client registration, and set the authorization path to /oauth/consent with
the Site URL set to this server's origin.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


def public_origin(request: Request) -> str:
    """This server's origin as clients see it (Vercel terminates TLS in front of us)."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def resource_metadata_url(request: Request) -> str:
    return f"{public_origin(request)}/.well-known/oauth-protected-resource/mcp"


def _supabase() -> str:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise HTTPException(503, "SUPABASE_URL is not configured")
    return url


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
def protected_resource(request: Request) -> dict:
    return {
        "resource": f"{public_origin(request)}/mcp",
        "authorization_servers": [f"{_supabase()}/auth/v1"],
        "bearer_methods_supported": ["header"],
        "resource_name": "Courtside",
    }


@router.get("/oauth/consent", response_class=HTMLResponse)
def consent() -> HTMLResponse:
    anon = os.environ.get("SUPABASE_ANON_KEY", "")
    if not anon:
        raise HTTPException(503, "SUPABASE_ANON_KEY is not configured")
    # Both values are public by design; json.dumps keeps them inert inside the script.
    page = CONSENT_PAGE.replace("__CONFIG__", json.dumps({"auth": f"{_supabase()}/auth/v1", "anon": anon}))
    return HTMLResponse(page, headers={
        # No third-party code on a page that takes your password.
        "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                                   f"connect-src {_supabase()}; form-action 'none'; frame-ancestors 'none'; "
                                   "base-uri 'none'",
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
    })


CONSENT_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Courtside sign-in</title>
<style>
  :root { --bg: #f6f6f4; --card: #fff; --text: #1b1b1a; --muted: #6b6b66; --line: #dcdcd6; --accent: #1f6f50; --err: #b3261e; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #151514; --card: #1f1f1d; --text: #ececea; --muted: #a2a29c; --line: #36362f; --accent: #4fb388; --err: #f2b8b5; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 16px;
         background: var(--bg); color: var(--text); font: 16px/1.45 system-ui, sans-serif; }
  main { width: 100%; max-width: 380px; background: var(--card); border: 1px solid var(--line);
         border-radius: 12px; padding: 24px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  p { margin: 0 0 16px; color: var(--muted); }
  label { display: block; font-size: 14px; margin: 12px 0 4px; }
  input { width: 100%; padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px;
          background: transparent; color: var(--text); font: inherit; }
  button { width: 100%; margin-top: 16px; padding: 11px; border-radius: 8px; border: 1px solid var(--accent);
           background: var(--accent); color: #fff; font: inherit; font-weight: 600; cursor: pointer; }
  button.secondary { background: transparent; color: var(--text); border-color: var(--line); margin-top: 8px; }
  button:disabled { opacity: .6; cursor: default; }
  .err { color: var(--err); margin-top: 12px; min-height: 1.4em; }
  [hidden] { display: none !important; }
  strong { color: var(--text); }
</style>
</head>
<body>
<main>
  <section id="signin">
    <h1>Sign in to Courtside</h1>
    <p>Use the same account as the Courtside app.</p>
    <form id="form">
      <label for="email">Email</label>
      <input id="email" type="email" autocomplete="username" required>
      <label for="password">Password</label>
      <input id="password" type="password" autocomplete="current-password" required>
      <button id="go" type="submit">Sign in</button>
    </form>
  </section>
  <section id="consent" hidden>
    <h1>Allow access?</h1>
    <p><strong id="client">An app</strong> wants to manage your fantasy team as <strong id="who"></strong>:
       read your league and, with your go-ahead in the chat, change your lineup and roster.</p>
    <button id="approve">Allow</button>
    <button id="deny" class="secondary">Deny</button>
  </section>
  <div class="err" id="err" role="alert"></div>
</main>
<script>
const CONFIG = __CONFIG__;
const id = new URLSearchParams(location.search).get("authorization_id");
const $ = (x) => document.getElementById(x);
let token = null;

function fail(msg) { $("err").textContent = msg; }

async function call(method, path, body) {
  const r = await fetch(CONFIG.auth + path, {
    method,
    headers: { apikey: CONFIG.anon, "Content-Type": "application/json",
               ...(token ? { Authorization: "Bearer " + token } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.msg || data.error_description || data.message || ("HTTP " + r.status));
  return data;
}

async function decide(action) {
  for (const b of document.querySelectorAll("button")) b.disabled = true;
  try {
    const res = await call("POST", "/oauth/authorizations/" + encodeURIComponent(id) + "/consent", { action });
    location.assign(res.redirect_url);
  } catch (e) {
    fail(e.message);
    for (const b of document.querySelectorAll("button")) b.disabled = false;
  }
}

if (!id) {
  $("signin").hidden = true;
  fail("This page is part of connecting an app to Courtside; open it from that app.");
}

$("form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  fail("");
  $("go").disabled = true;
  try {
    const s = await call("POST", "/token?grant_type=password", { email: $("email").value.trim(), password: $("password").value });
    token = s.access_token;
    const d = await call("GET", "/oauth/authorizations/" + encodeURIComponent(id));
    if (d.redirect_url && !d.authorization_id) { location.assign(d.redirect_url); return; }  // already approved
    $("client").textContent = (d.client && d.client.name) || "An app";
    $("who").textContent = (d.user && d.user.email) || $("email").value.trim();
    $("signin").hidden = true;
    $("consent").hidden = false;
  } catch (e) {
    fail(e.message);
  } finally {
    $("go").disabled = false;
  }
});
$("approve").addEventListener("click", () => decide("approve"));
$("deny").addEventListener("click", () => decide("deny"));
</script>
</body>
</html>
"""
