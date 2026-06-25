# Security Policy & Analysis

This document covers DZ Forge's security model, a self-assessment of the current
code, and how to report a vulnerability.

## Reporting a vulnerability

Please report security issues **privately** — open a
[GitHub Security Advisory](../../security/advisories/new) (preferred) or contact the maintainer
directly rather than filing a public issue. Include steps to reproduce and the affected file/endpoint.
You'll get an acknowledgement and a fix or mitigation as soon as practical.

---

## What DZ Forge is (threat model)

DZ Forge is a **single-user, local** tool: a Python standard-library HTTP server bound to
`127.0.0.1:8777` plus a browser front-end. It reads and writes **DayZ server config files** inside a
single configured `serverRoot`, and can optionally edit a remote server over SFTP. It has no user
accounts, no database, and is not intended to be exposed to a network or the internet.

The assets it protects are your server's config files (and the SSH key you point it at). The main
realistic adversaries are: (a) a malicious **config file** you open from an untrusted source, (b) a
malicious **web page** open in the same browser trying to reach the local API, and (c) a
**man-in-the-middle** on an SFTP connection.

---

## Security strengths (verified in code)

- **Localhost-only:** the server binds `("127.0.0.1", 8777)` — not `0.0.0.0`. It is not reachable
  from the LAN/internet.
- **No CORS headers:** responses set no `Access-Control-Allow-Origin`, so other websites in your
  browser cannot read DZ Forge's responses, and JSON `POST`s from other origins are preflighted and
  blocked.
- **Path confinement:** every file endpoint (`/api/read`, `/api/save`, `/api/delete`, `/api/backups`,
  `/api/restore`) resolves the requested path with `os.path.commonpath([path, EDIT_ROOT]) == EDIT_ROOT`
  and rejects anything outside the configured root (`403 path outside editable root`). `/api/restore`
  validates **both** the backup and target paths. Static file serving uses Python's
  `SimpleHTTPRequestHandler` confined to the app directory.
- **No shell execution / injection:** the only subprocess use (`sftpsrc.py`) calls `subprocess.run`
  with an **argument list** (no `shell=True`), and there is no `eval`/`exec`/`os.system` anywhere.
- **Key-based SFTP with host-key checking:** remote auth uses an SSH private key you provide (never
  copied or stored), driven through the Microsoft-signed `sftp.exe`, with trust-on-first-use host-key
  verification (`accept-new` + a real `known_hosts`) so a changed server key is rejected.
- **Output escaping:** file/config-derived text is HTML-escaped before being inserted into the DOM,
  so a malicious classname/title can't inject script (see F-1).
- **Reversible by default:** every save/delete first copies the original to a timestamped `.bak`, and
  restore is built in.

---

## Findings, status & recommendations

Last reviewed: 2026-06. Fixed items were verified in the running app.

| ID | Severity | Finding | Status / mitigation |
|----|----------|---------|---------------------|
| **F-1** | Medium | **Stored XSS from untrusted config content.** The UI interpolated file-derived strings (item names, classnames, quest titles, NPC names) into `innerHTML` without HTML-escaping. A maliciously crafted config (e.g. a classname containing `<img onerror=…>`) could run script in the page, which has full local read/write to your files via the API. | ✅ **Fixed.** Added an `esc()` helper in `app.html` and `index.html` and applied it to all file-derived values rendered into `innerHTML` (list rows, editor headers, table cells, map tooltips/popups, audit/verify reports). Verified: an injected `<img onerror>` item name now renders as inert text and does not execute. *Residual:* `turrets.html` (the bundled AutomatedTurrets editor) renders class names from **your own** turret config via `innerHTML` — lower risk; escape if you load third-party turret configs. |
| **F-3** | Medium | **SFTP host key not verified.** `sftpsrc.py` used `StrictHostKeyChecking=no` + `UserKnownHostsFile=/dev/null`, so a MITM on the SSH connection went undetected. | ✅ **Fixed.** Now uses `StrictHostKeyChecking=accept-new` with a real per-app `known_hosts` (`.dzforge_known_hosts`): the server's key is remembered on first connect and the connection is **refused if the key later changes**. Still non-interactive and key-auth only. |
| **F-2** | Low–Med | **No auth / CSRF on the local API.** Any local process can call the API. Cross-site reads are blocked (no CORS) and JSON `POST`s are preflighted, but a "simple" cross-site `POST` that still parses as JSON is not preflighted and could reach write endpoints. | **Open (accepted, low real risk).** Mitigated by localhost-only binding and confinement to your server folder. Recommended next: validate the `Origin`/`Host` header (reject non-localhost) to also block DNS-rebinding. |
| **F-4** | Low | **Third-party data egress (OCR).** The optional OCR import in the Turret editor sends images to Google's Gemini API using a key kept in `localStorage`. | **By design / opt-in.** Off unless you set a key and use it; documented in the README. |
| **F-5** | Low | **CDN scripts without SRI (supply chain).** `turrets.html` loads `mammoth.js` from jsDelivr and Google Fonts at runtime (Leaflet is vendored locally). | **Open.** A CSP already restricts script sources. Recommended: vendor locally or add Subresource Integrity + pin versions. |
| **F-6** | Info | **Unsigned executable.** The PyInstaller build is unsigned → SmartScreen / Smart App Control warnings or blocks. | **Not a vulnerability.** Code-sign for wide distribution; otherwise run from source (`start.bat`). |
| **F-7** | Low | **No request-size limit.** `_body()` reads `Content-Length` bytes without a cap (local DoS only). | **Open (low).** Add a sane maximum body size. |

None of the findings allow remote compromise on a default setup: the server is localhost-only and
file access is confined to your configured server folder. The two medium findings (**F-1** XSS and
**F-3** SFTP host-key) are now **fixed**; the remaining open items are low-severity and local-only.

---

## Hardening tips for users

- Only open config files from sources you trust (mods, marketplaces) — see **F-1**.
- Don't port-forward or reverse-proxy port 8777. There's no reason to expose it.
- For SFTP, use a dedicated key with least privilege, and confirm your server's host key out-of-band.
- Keep backups (DZ Forge makes them automatically) — and your own off-box copies of critical files.

> DZ Forge edits configuration only; it does not harden your live server. Review your server's own
> `serverDZ.cfg`, BattlEye, RCon and firewall settings separately.
