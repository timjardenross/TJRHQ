# Caddy v3 — SEC-01 self-improvement containment (NOT DEPLOYED)

Status: **draft, offline-validated only. Do not deploy.** The production secret
is still unrotated and appears in historical logs. v3 must not go live until
rotation and log redaction are confirmed (see "Deployment gate" below).

Files in this directory:

| File | Purpose |
|---|---|
| `Caddyfile.v3` | Candidate config. Copy of the live v2 file with only the self-improvement handling changed in both site blocks. |
| `validate_v3.sh` | Offline checks. Read-only on `/etc/caddy`, never reloads Caddy. |
| `README-v3.md` | This file. |

Baseline: the live v2 file at `/etc/caddy/Caddyfile` has sha256
`1a309347d05c5d943f2d3ddf23250bb5a62d40f78b9ca679172d482e08ad2ee6`.
`Caddyfile.v3` has sha256 `a90ce2d7890086a5fdb8a3a59bd9ec9e9f71baceb558d09ed9d9513fc40f267e`.

## What changed

Only the self-improvement block in each of the two site blocks changed (bare IP
`https://109.123.227.196` and `https://109-123-227-196.sslip.io`). Site addresses,
`tls internal`, upstreams, the context/tts/changedetection/uptime/default routes,
security headers, and both log blocks (header-delete filter) are byte-identical
to v2.

v2 had one blanket rule: any non-GET/HEAD method on `/self-improvement*` and
`/api/self-improvement*` returned 403. v3 replaces it with ordered rules:

| Rule | Matcher | Response |
|---|---|---|
| A | OPTIONS on any self-improvement path (headers irrelevant) | 403 |
| B | any method other than GET, HEAD, POST on self-improvement paths | 403 |
| C | POST on self-improvement paths that is not one of the four exact write paths | 403 |
| D | POST on one of the four write paths with no `X-Self-Improvement-Secret` header present | 403 |
| (proxy) | everything else: GET/HEAD reads, and POST with the header on the four write paths | unchanged proxy to `127.0.0.1:8892` (`/self-improvement/*`) or to the LCARS catch-all `127.0.0.1:3200` (`/api/self-improvement/*`) |

Write allowlist (exact path match, no prefix):

- `/self-improvement/api/decide`
- `/self-improvement/api/opportunity/decide`
- `/api/self-improvement/decide`
- `/api/self-improvement/opportunities/decide`

### Exact diff (v2 to v3), from `diff -u`

```diff
--- Caddyfile.v2
+++ Caddyfile.v3
@@ -61,18 +61,60 @@
 
 	# Self-Improvement Dashboard — same pattern; dashboard.py does its own
 	# auth (X-Self-Improvement-Secret), Caddy just proxies the header through.
-	# SEC-01 temporary containment (PROPOSED, NOT APPLIED): block state-changing
-	# methods on the self-improvement dashboard AND its LCARS-portal proxy routes
-	# (/api/self-improvement/* on :3200 is public via the catch-all). GET/HEAD stay open
-	# for the LCARS read path. Remove when SEC-01 Option B lands.
-	@siWrite {
+	#
+	# SEC-01 v3 (NOT DEPLOYED — see deploy/caddy/README-v3.md). Replaces the v2
+	# blanket non-GET deny with narrowly scoped rules. Caddy evaluates `handle`
+	# blocks top-down and the first match wins, so every deny below sits ABOVE
+	# the proxy handle. Write allowlist (exact path match, POST only):
+	#   /self-improvement/api/decide
+	#   /self-improvement/api/opportunity/decide
+	#   /api/self-improvement/decide
+	#   /api/self-improvement/opportunities/decide
+
+	# Rule A: OPTIONS is always denied on these paths, with or without headers.
+	@siOptions {
+		path /self-improvement /self-improvement/* /api/self-improvement /api/self-improvement/*
+		method OPTIONS
+	}
+	handle @siOptions {
+		respond "Forbidden" 403
+	}
+
+	# Rule B: only GET, HEAD and POST are ever allowed on these paths.
+	@siBadMethod {
 		path /self-improvement /self-improvement/* /api/self-improvement /api/self-improvement/*
-		not method GET HEAD
+		not method GET HEAD POST
+	}
+	handle @siBadMethod {
+		respond "Forbidden" 403
+	}
+
+	# Rule C: POST is only allowed on the four exact write paths. `path` matches
+	# URL.Path (query strings are ignored) and exact paths have no wildcard, so
+	# trailing-slash or sub-path variants are NOT allowlisted and fail closed.
+	@siPostNotAllowlisted {
+		path /self-improvement /self-improvement/* /api/self-improvement /api/self-improvement/*
+		method POST
+		not path /self-improvement/api/decide /self-improvement/api/opportunity/decide /api/self-improvement/decide /api/self-improvement/opportunities/decide
+	}
+	handle @siPostNotAllowlisted {
+		respond "Forbidden" 403
+	}
+
+	# Rule D: allowlisted POST without the secret header is denied at the edge.
+	# Header PRESENCE only (`*`) — Caddy does not authenticate; Flask validates
+	# the value and returns 401 on a wrong secret.
+	@siWriteNoSecret {
+		path /self-improvement/api/decide /self-improvement/api/opportunity/decide /api/self-improvement/decide /api/self-improvement/opportunities/decide
+		method POST
+		not header X-Self-Improvement-Secret *
 	}
-	handle @siWrite {
+	handle @siWriteNoSecret {
 		respond "Forbidden" 403
 	}
 
+	# Everything else falls through unchanged: GET/HEAD reads, and POST with a
+	# header on the four write paths.
 	handle_path /self-improvement/* {
 		reverse_proxy 127.0.0.1:8892
 	}
@@ -158,18 +200,60 @@
 
 	# Self-Improvement Dashboard — same pattern; dashboard.py does its own
 	# auth (X-Self-Improvement-Secret), Caddy just proxies the header through.
-	# SEC-01 temporary containment (PROPOSED, NOT APPLIED): block state-changing
-	# methods on the self-improvement dashboard AND its LCARS-portal proxy routes
-	# (/api/self-improvement/* on :3200 is public via the catch-all). GET/HEAD stay open
-	# for the LCARS read path. Remove when SEC-01 Option B lands.
-	@siWrite {
+	#
+	# SEC-01 v3 (NOT DEPLOYED — see deploy/caddy/README-v3.md). Replaces the v2
+	# blanket non-GET deny with narrowly scoped rules. Caddy evaluates `handle`
+	# blocks top-down and the first match wins, so every deny below sits ABOVE
+	# the proxy handle. Write allowlist (exact path match, POST only):
+	#   /self-improvement/api/decide
+	#   /self-improvement/api/opportunity/decide
+	#   /api/self-improvement/decide
+	#   /api/self-improvement/opportunities/decide
+
+	# Rule A: OPTIONS is always denied on these paths, with or without headers.
+	@siOptions {
+		path /self-improvement /self-improvement/* /api/self-improvement /api/self-improvement/*
+		method OPTIONS
+	}
+	handle @siOptions {
+		respond "Forbidden" 403
+	}
+
+	# Rule B: only GET, HEAD and POST are ever allowed on these paths.
+	@siBadMethod {
+		path /self-improvement /self-improvement/* /api/self-improvement /api/self-improvement/*
+		not method GET HEAD POST
+	}
+	handle @siBadMethod {
+		respond "Forbidden" 403
+	}
+
+	# Rule C: POST is only allowed on the four exact write paths. `path` matches
+	# URL.Path (query strings are ignored) and exact paths have no wildcard, so
+	# trailing-slash or sub-path variants are NOT allowlisted and fail closed.
+	@siPostNotAllowlisted {
+		path /self-improvement /self-improvement/* /api/self-improvement /api/self-improvement/*
+		method POST
+		not path /self-improvement/api/decide /self-improvement/api/opportunity/decide /api/self-improvement/decide /api/self-improvement/opportunities/decide
+	}
+	handle @siPostNotAllowlisted {
+		respond "Forbidden" 403
+	}
+
+	# Rule D: allowlisted POST without the secret header is denied at the edge.
+	# Header PRESENCE only (`*`) — Caddy does not authenticate; Flask validates
+	# the value and returns 401 on a wrong secret.
+	@siWriteNoSecret {
+		path /self-improvement/api/decide /self-improvement/api/opportunity/decide /api/self-improvement/decide /api/self-improvement/opportunities/decide
+		method POST
+		not header X-Self-Improvement-Secret *
 	}
-	handle @siWrite {
+	handle @siWriteNoSecret {
 		respond "Forbidden" 403
 	}
 
+	# Everything else falls through unchanged: GET/HEAD reads, and POST with a
+	# header on the four write paths.
 	handle_path /self-improvement/* {
 		reverse_proxy 127.0.0.1:8892
 	}
```

## Threat rationale

- **A (OPTIONS always 403).** Preserves the v2 OPTIONS restriction. OPTIONS is a
  CORS preflight and has no legitimate use against these endpoints from the
  Vercel-hosted app. Denying it regardless of headers closes preflight-driven
  probing of the write endpoints.
- **B (method allowlist GET/HEAD/POST).** Any other verb (PUT, PATCH, DELETE,
  TRACE, custom verbs) has no defined use on these routes. Denying at the edge
  shrinks the attack surface without relying on Flask to reject them.
- **C (POST only on the four write paths).** The v2 rule blocked all writes,
  which also broke the legitimate decide flows. Narrowing to exact paths means a
  new or unknown POST endpoint under `/self-improvement*` is denied by default
  (fail closed). Exact matching (not prefix) means `/.../decide/`, `/.../decide/x`
  and other variants are not allowlisted.
- **D (no secret header, 403 at the edge).** Cheap, early rejection of
  unauthenticated writes. This is **not authentication**: Caddy checks only that
  the header is present. The Flask app validates the value and is still the
  gate. Presence checks are a defence-in-depth filter, not a control in
  their own right.
- **Proxy fallthrough.** GET/HEAD reads stay open because the LCARS read path
  depends on them (v2 comment). Those reads are still authenticated by Flask.

Known limits, deliberately accepted:

- Path matching is on the decoded `URL.Path` and is case-sensitive. A request to
  a mixed-case variant of a write path is not allowlisted and falls to rule C
  (POST) or to the LCARS catch-all, which does not serve these routes.
- Query strings are ignored by `path`. `POST /self-improvement/api/decide?x=1` is
  treated as the write path. This is the same route in Flask, so it is intended.
- A header sent with an empty value still counts as present (Caddy `*` is a
  presence check). Flask must reject empty or wrong values; this is the
  defence-in-depth boundary.
- `/api/self-improvement/*` paths are not routed to `:8892` by Caddy (they go to
  the LCARS catch-all on `:3200`), exactly as in v2. The deny rules cover them
  anyway, because they are declared in the same site block.

## Expected responses

| Case | Expected | Enforced by |
|---|---|---|
| GET to a read path, no header | 401 | Flask (Caddy passes it through) |
| OPTIONS to any self-improvement path, with or without header | 403 | Caddy rule A |
| POST to a write path, no `X-Self-Improvement-Secret` header | 403 | Caddy rule D |
| POST to a write path, wrong secret value | 401 | Flask (Caddy sees header presence only) |
| POST to a write path, correct secret value | 200 | Flask |
| POST to a non-write self-improvement path (any header) | 403 | Caddy rule C |
| PUT/DELETE/PATCH to any self-improvement path | 403 | Caddy rule B |

Sandbox results (see "Offline verification" below) cover the Caddy-side rows.
The Flask-side 401 and 200 rows are expected from the app's own auth logic and
have **not** been exercised here, because the real Flask services were not run.

## Offline verification

Run from the repo root:

```
bash deploy/caddy/validate_v3.sh
```

The script:

- (a) compares the live `/etc/caddy/Caddyfile` sha256 with the v2 baseline (read-only; warns only);
- (b) runs `caddy validate` on `Caddyfile.v3`;
- (c) checks that both log blocks still contain the header-delete filter (count = 2);
- (d) checks that the POST-scoped matchers reference exactly the four write paths;
- (e) runs `caddy adapt` into a private temp directory and prints route order, asserting the deny routes precede the proxy route in both hosts.

The script never reloads Caddy, never writes to `/etc/caddy`, and never contacts the admin API or a public host.

Sandbox test (127.0.0.1 only, scratch copy, stub upstream, synthetic header
`SYNTH-TEST-VALUE`, `admin off`, processes killed by PID afterward): every row of
the Caddy-side expectations passed on both site ports: OPTIONS 403 with and
without header; POST without header 403; POST with synthetic header 200 from
stub; PUT 403; DELETE 403; POST to a non-write path 403; POST to a trailing-slash
write variant 403; GET reads 200; HEAD 200.

## Rollback (production)

If v3 is deployed and misbehaves, restore the known-good v2 file. It must match
sha256 `1a309347d05c5d943f2d3ddf23250bb5a62d40f78b9ca679172d482e08ad2ee6` before
it is reloaded:

```
sha256sum /path/to/known-good-v2/Caddyfile   # must print 1a309347d05c5d943f2d3ddf23250bb5a62d40f78b9ca679172d482e08ad2ee6
sudo install -m 0644 /path/to/known-good-v2/Caddyfile /etc/caddy/Caddyfile
sudo sha256sum /etc/caddy/Caddyfile          # must print 1a309347...
sudo caddy validate --config /etc/caddy/Caddyfile
sudo caddy reload --config /etc/caddy/Caddyfile --force
```

The v2 file is not kept in this repo. Before any v3 deployment, the operator must
save a copy of the live v2 file outside the repo and confirm its hash. The
known-good copy is the source for rollback. Do not roll back by hand-editing
`/etc/caddy/Caddyfile`.

## Deployment gate

v3 must **not** be deployed until all of the following are confirmed:

1. The production secret (`X-Self-Improvement-Secret` value used by the Flask
   dashboard and its callers) is rotated. The current value is unrotated and
   appears in historical logs.
2. Log redaction is confirmed in production. The header-delete filter is
   present in the v3 log blocks, but historical log lines written before the
   filter took effect may still contain the value. Confirm redaction at the
   point of logging and the handling of existing logs.
3. The rotated secret is updated everywhere it is consumed (Vercel env, local
   callers) before the reload, so legitimate writes are not broken.
4. `validate_v3.sh` passes on the exact file to be deployed, and its sha256 is
   recorded.

Until then, `Caddyfile.v3` is a reviewed candidate only.
