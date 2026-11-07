#!/usr/bin/env bash
# Offline checks for deploy/caddy/Caddyfile.v3 (SEC-01 self-improvement containment).
#
# Read-only with respect to production: never reloads Caddy, never writes to
# /etc/caddy, never contacts the admin API or any public host. The only thing it
# reads from /etc/caddy is the live file's sha256 (for the baseline warning).
#
# Usage: deploy/caddy/validate_v3.sh   (exit 0 = all checks passed)

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
V3="$HERE/Caddyfile.v3"
LIVE="/etc/caddy/Caddyfile"
BASELINE_SHA256="1a309347d05c5d943f2d3ddf23250bb5a62d40f78b9ca679172d482e08ad2ee6"
EXPECTED_WRITE_PATHS="/self-improvement/api/decide /self-improvement/api/opportunity/decide /api/self-improvement/decide /api/self-improvement/opportunities/decide"

fail=0
pass() { printf 'PASS  %s\n' "$1"; }
bad()  { printf 'FAIL  %s\n' "$1"; fail=1; }
warn() { printf 'WARN  %s\n' "$1"; }

if [[ ! -f "$V3" ]]; then
    bad "Caddyfile.v3 not found at $V3"
    exit 1
fi

# (a) Live baseline hash (read-only). Warn, do not fail, if it differs.
echo "== (a) live baseline"
if [[ -r "$LIVE" ]]; then
    live_sha="$(sha256sum "$LIVE" | awk '{print $1}')"
    if [[ "$live_sha" == "$BASELINE_SHA256" ]]; then
        pass "live $LIVE matches v2 baseline $BASELINE_SHA256"
    else
        warn "live $LIVE sha256 is $live_sha, expected v2 baseline $BASELINE_SHA256 — live config has changed since v3 was written; re-review before any deploy"
    fi
else
    warn "live $LIVE not readable by this user; baseline hash not checked"
fi

# (b) Validate the v3 file offline.
echo "== (b) caddy validate"
validate_out="$(caddy validate --config "$V3" --adapter caddyfile 2>&1)"
validate_rc=$?
if [[ $validate_rc -eq 0 ]] && grep -q 'Valid configuration' <<<"$validate_out"; then
    pass "caddy validate: Valid configuration"
else
    bad "caddy validate failed (rc=$validate_rc)"
    grep -v '"level":"info"' <<<"$validate_out" | tail -20
fi

# (c) Both log blocks must still delete the secret header from logs.
echo "== (c) log header-delete filter"
delete_count="$(grep -c 'request>headers>X-Self-Improvement-Secret delete' "$V3")"
if [[ "$delete_count" == "2" ]]; then
    pass "header-delete filter present in both log blocks (count=$delete_count)"
else
    bad "expected 2 header-delete filters, found $delete_count"
fi

# (d) Only the four write paths may be POST-allowed. Check the two POST-related
#     named matchers reference exactly that set, and that no other POST rule exists.
echo "== (d) POST allowlist"
post_rule_count="$(grep -c 'method POST' "$V3")"
if [[ "$post_rule_count" == "4" ]]; then
    pass "exactly two POST-scoped matchers per site block (4 total: deny-non-allowlisted, deny-missing-header)"
else
    bad "expected 4 'method POST' matchers (2 per site), found $post_rule_count"
fi
# Each `path` line that sits inside a POST matcher's block: pull the exact-path
# list from the `not path` line (deny-non-allowlisted) and from the allowlisted
# path line (deny-missing-header). Both must equal the expected four paths.
# Every site block (2 of them) must carry the same lists.
allow_from_not="$(grep -E '^\s+not path /self-improvement/api/decide' "$V3" | sed -E 's/^\s+not path //' | tr -s ' ')"
allow_from_nosec="$(awk '/^\t@siWriteNoSecret \{/{f=1;next} f&&/^\t\tpath /{sub(/^\t\tpath /,"");print;f=0}' "$V3" | tr -s ' ')"
not_bad="$(grep -vxF "$EXPECTED_WRITE_PATHS" <<<"$allow_from_not" | grep -c .)"
nosec_bad="$(grep -vxF "$EXPECTED_WRITE_PATHS" <<<"$allow_from_nosec" | grep -c .)"
if [[ "$(grep -c . <<<"$allow_from_not")" == "2" && "$not_bad" == "0" ]]; then
    pass "deny-non-allowlisted exempts exactly the four write paths (both sites)"
else
    bad "deny-non-allowlisted exemption list differs from expected: '$allow_from_not'"
fi
if [[ "$(grep -c . <<<"$allow_from_nosec")" == "2" && "$nosec_bad" == "0" ]]; then
    pass "deny-missing-header applies to exactly the four write paths (both sites)"
else
    bad "deny-missing-header path list differs from expected: '$allow_from_nosec'"
fi
if grep -q 'not header X-Self-Improvement-Secret \*' "$V3"; then
    pass "missing-secret rule uses header presence (*)"
else
    bad "missing-secret rule not found"
fi

# (e) Adapted-route order summary. Adapt to a private temp dir, never to /etc.
echo "== (e) adapted route order"
TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT
if caddy adapt --config "$V3" --adapter caddyfile > "$TMPD/v3.json" 2>"$TMPD/adapt.err"; then
    python3 - "$TMPD/v3.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
ok = True
for sname, srv in d["apps"]["http"]["servers"].items():
    for r in srv.get("routes", []):
        hosts = [h for m in r.get("match", []) if "host" in m for h in m["host"]]
        if not hosts:
            continue
        print(f"  server={sname} host={','.join(hosts)}")
        routes = r["handle"][0].get("routes", [])
        proxy_idx = None
        deny_idx = []
        for i, rt in enumerate(routes):
            match = json.dumps(rt.get("match", []))
            kinds = []
            for h in rt.get("handle", []):
                if h["handler"] == "subroute":
                    for sub in h.get("routes", []):
                        for hh in sub.get("handle", []):
                            if hh["handler"] == "static_response" and str(hh.get("status_code")) == "403":
                                kinds.append("403")
                            elif hh["handler"] == "reverse_proxy":
                                kinds.append("proxy " + ",".join(u["dial"] for u in hh["upstreams"]))
                elif h["handler"] == "reverse_proxy":
                    kinds.append("proxy " + ",".join(u["dial"] for u in h["upstreams"]))
            if "self-improvement" in match:
                if "403" in kinds:
                    deny_idx.append(i)
                if kinds and kinds[0].startswith("proxy 127.0.0.1:8892"):
                    proxy_idx = i
                print(f"    [{i}] {'/'.join(kinds) or 'subroute'}  match={match[:110]}")
        if proxy_idx is None and not deny_idx:
            print("    (no self-improvement routes on this server block; skipped)")
            continue
        if proxy_idx is None:
            ok = False
            print("    ERROR: no self-improvement proxy route found")
        elif not deny_idx or max(deny_idx) >= proxy_idx:
            ok = False
            print("    ERROR: a deny route is not before the proxy route")
        else:
            print(f"    OK: {len(deny_idx)} deny routes precede proxy route [{proxy_idx}]")
sys.exit(0 if ok else 1)
PYEOF
    if [[ $? -eq 0 ]]; then pass "deny routes precede the self-improvement proxy in both hosts"; else bad "route order check failed"; fi
else
    bad "caddy adapt failed"
    cat "$TMPD/adapt.err" >&2
fi

echo
if [[ $fail -eq 0 ]]; then
    echo "ALL CHECKS PASSED (offline only; v3 is NOT deployed — see README-v3.md)"
else
    echo "ONE OR MORE CHECKS FAILED"
fi
exit $fail
