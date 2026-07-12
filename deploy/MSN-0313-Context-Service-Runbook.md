# MSN-0313-OPS — Restore Captain's Brief assembly (context-service wiring)

**Goal:** make `/captains-brief` (and `/captains-brief-workbench`) assemble again.

The portal calls `GET /api/captain-brief` → `fetch ${CONTEXT_SERVICE_URL}/brief/full`
→ the Flask **context-service** on the VM. The error *"Failed to assemble Captain
Brief"* means the service **was reached but answered with an error** (a network
failure produces the different string *"Failed to reach the Captain Brief service"*).
Cause is one of: **A** auth 401 · **B** assembly 500 · **C** wrong `CONTEXT_SERVICE_URL`
/ service down.

**Facts (from the repo):**
- Unit: `context-service.service` → `python core/context-assembly/context_service.py serve --host 127.0.0.1 --port 5001` (see `deploy/context-service.service`).
- `WorkingDirectory=/opt/starship-endeavour`, venv `platform-runtime/.venv`, `EnvironmentFile=/opt/starship-endeavour/platform-runtime/.env`.
- Binds **127.0.0.1:5001 only** — a **Caddy** route on the VM fronts it publicly (Caddy config lives on the VM, not in the repo).
- Every route except `/health` requires header `X-Context-Service-Secret` == server-side `CONTEXT_SERVICE_SECRET`.
- The portal runs on **Vercel**; `CONTEXT_SERVICE_URL` / `CONTEXT_SERVICE_SECRET` live in the Vercel project env, not on the VM.

---

## Step 0 — SSH in
```bash
ssh <you>@<starship-vm>        # the host running /opt/starship-endeavour
cd /opt/starship-endeavour
```

## Step 1 — Is the service running?
```bash
systemctl status context-service --no-pager
# If inactive/failed:
sudo systemctl enable --now context-service
journalctl -u context-service -n 50 --no-pager      # look for Python tracebacks / import errors
```
If it won't start with an import error (e.g. `No module named flask`):
```bash
platform-runtime/.venv/bin/pip install -r platform-runtime/requirements.txt
sudo systemctl restart context-service
```

## Step 2 — Does it answer locally? (bypasses Caddy + auth)
```bash
curl -s http://127.0.0.1:5001/health ; echo
# expect: {"status":"healthy","service":"context-assembly",...}
```
Now hit the actual brief endpoint locally. Load the server secret from its own env
file (stays on the VM, never printed to chat):
```bash
SECRET=$(grep -E '^CONTEXT_SERVICE_SECRET=' platform-runtime/.env | cut -d= -f2-)
curl -s -H "X-Context-Service-Secret: $SECRET" \
  "http://127.0.0.1:5001/brief/full?limit=5" | head -c 400 ; echo
```
- Body starts with `{"version": ...}` → **the engine is healthy**; the problem is the portal→service hop (Step 3, cause A or C).
- Body is `{"error":"full_captain_brief_failed","detail":"..."}` → **cause B**. Read the `detail`, fix per the traceback in `journalctl`, restart.

## Step 3 — What does the portal point at, and does the secret match?
```bash
# From a machine with the Vercel CLI linked to the lcars-portal project:
vercel env ls production
vercel env pull .env.vercel.check --environment=production   # writes values locally to inspect
grep -E 'CONTEXT_SERVICE_(URL|SECRET)' .env.vercel.check
rm .env.vercel.check      # don't leave secrets lying around
```
Check two things:
1. **`CONTEXT_SERVICE_URL` is the public Caddy HTTPS URL** — **not** `http://127.0.0.1:5001` (that default, on Vercel, points at the serverless box's own loopback → nothing there).
2. **`CONTEXT_SERVICE_SECRET` (Vercel) == `CONTEXT_SERVICE_SECRET` (VM `platform-runtime/.env`)**, byte-for-byte. Mismatch/absence → the service returns `{"error":"unauthorized"}` 401 → *"Failed to assemble Captain Brief"*. **Cause A — the single most likely culprit.**

## Step 4 — Does Caddy actually front the service publicly?
From your laptop (not the VM), using the same URL the portal uses:
```bash
curl -s "$CONTEXT_SERVICE_URL/health" ; echo
# healthy JSON → Caddy → service path works
# HTML / 502 / connection error → Caddy route missing or upstream down → cause C
curl -s -H "X-Context-Service-Secret: <the-secret>" "$CONTEXT_SERVICE_URL/brief/full?limit=5" | head -c 200 ; echo
```
If `/health` fails publicly but works on `127.0.0.1:5001`, the **Caddy reverse-proxy
route to `127.0.0.1:5001` is missing/broken** — add/fix it on the VM and
`sudo systemctl reload caddy`.

---

## Decision table

| What you saw | Cause | Fix |
|---|---|---|
| Step 2 local `/brief/full` returns a `version` doc, but public/portal fails with 401 | **A – auth** | Set Vercel `CONTEXT_SERVICE_SECRET` = the VM value; redeploy the portal |
| Step 2 returns `{"error":"full_captain_brief_failed",...}` | **B – assembly 500** | Fix per the `detail`/traceback (usually a missing dep in `.venv` or a runtime raise); restart the unit |
| `CONTEXT_SERVICE_URL` is `127.0.0.1:5001` or a wrong host; or Step 4 public `/health` fails | **C – URL / service down** | Point `CONTEXT_SERVICE_URL` at the Caddy HTTPS URL; ensure the unit is running + Caddy route exists; redeploy the portal |

## Step 5 — Verify the fix
1. Redeploy the portal if you changed any Vercel env var (env changes need a new deploy).
2. Load `/captains-brief-workbench` (or `/captains-brief`) authenticated.
3. **Success:** the brief renders (summary, confidence, sections). **Still failing:** the page now shows a `Cause: <detail>` line under the error — jump back to the matching row above. *(That `Cause:` line is the diagnosability fix shipped in `5a005f47`; before it, the cause was invisible.)*

**Safety:** read-only diagnosis except for `systemctl restart`, an optional `pip
install`, and Vercel env edits. No DB writes, no data changes. Never paste
`CONTEXT_SERVICE_SECRET` into chat, a URL, or anywhere off the VM/Vercel — only
compare it in place.

---

_Companion to `CAPTAINS-BRIEF-WORKBENCH-MIGRATION-PLAN.md` (§3–4). This runbook is
Phase 0 of that plan — the ops root-cause fix that must land for the (reskinned)
workbench to show real data._
