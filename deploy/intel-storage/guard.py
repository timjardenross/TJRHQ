#!/usr/bin/env python3
# ruff: noqa: SIM115  (small single-user command-line tools)
"""Sample production health and enforce stop thresholds for background storage work. Read-only: HTTP GETs on loopback, /proc, statvfs.

  guard.py sample --seconds 300 --out baseline.json      record a baseline
  guard.py watch --baseline baseline.json --stop-file F  sample until F's directory is removed or a threshold trips (then create F)
"""
import argparse
import json
import os
import shutil
import statistics
import sys
import time
import urllib.error
import urllib.request

PROBES = {"portal": "http://127.0.0.1:3200/", "model_router": "http://127.0.0.1:8891/health", "backend": "http://127.0.0.1:5000/health",
          "context": "http://127.0.0.1:5001/health", "ollama": "http://127.0.0.1:11434/api/version"}
MIN_MEM_GIB, MAX_LOAD, MIN_DISK_GIB, DISK_REVIEW_GIB = 6.0, 8.0, 60, 80
LATENCY_FACTOR, LATENCY_FLOOR_S = 2.0, 0.25       # trip when the recent median exceeds max(2 x baseline p95, baseline p95 + 250 ms)
QUIET = ((6, 30, 7, 30), (12, 15, 12, 45), (17, 40, 18, 20))      # brief windows: background work pauses


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_open = urllib.request.build_opener(_NoRedirect).open


def probe(url):
    start = time.monotonic()
    try:
        with _open(url, timeout=5):
            ok = True
    except urllib.error.HTTPError as exc:
        ok = exc.code < 500
    except Exception:  # noqa: BLE001 - any failure to answer is the measurement
        ok = False
    return ok, time.monotonic() - start


def sample():
    mem = next(int(x.split()[1]) for x in open("/proc/meminfo") if x.startswith("MemAvailable")) / 1048576
    cpu = open("/proc/stat").readline().split()[1:]
    return {"t": time.time(), "probes": {k: probe(u) for k, u in PROBES.items()}, "mem_gib": mem, "load1": os.getloadavg()[0],
            "disk_free_gib": shutil.disk_usage("/").free / 2**30, "cpu_idle": int(cpu[3]), "cpu_total": sum(map(int, cpu))}


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))]


def summarise(samples):
    out = {"samples": len(samples), "probes": {}}
    for k in PROBES:
        lat = [s["probes"][k][1] for s in samples]
        out["probes"][k] = {"p50_ms": round(statistics.median(lat) * 1000, 1), "p95_ms": round(pct(lat, 0.95) * 1000, 1),
                            "failures": sum(not s["probes"][k][0] for s in samples)}
    for k in ("mem_gib", "load1", "disk_free_gib"):
        v = [s[k] for s in samples]
        out[k] = {"min": round(min(v), 2), "median": round(statistics.median(v), 2), "max": round(max(v), 2)}
    busy = 1 - (samples[-1]["cpu_idle"] - samples[0]["cpu_idle"]) / max(1, samples[-1]["cpu_total"] - samples[0]["cpu_total"])
    out["cpu_busy_pct"] = round(100 * busy, 1)
    return out


def breaches(recent, baseline):
    found = []
    last = recent[-1]
    for k, b in baseline["probes"].items():
        limit = max(LATENCY_FACTOR * b["p95_ms"], b["p95_ms"] + LATENCY_FLOOR_S * 1000) / 1000
        if len(recent) >= 3 and all(not s["probes"][k][0] for s in recent[-2:]):
            found.append(f"{k} not answering")
        elif len(recent) >= 5 and statistics.median(s["probes"][k][1] for s in recent[-5:]) > limit:
            found.append(f"{k} latency over {limit * 1000:.0f} ms")
    if last["mem_gib"] < MIN_MEM_GIB:
        found.append(f"available memory {last['mem_gib']:.1f} GiB")
    if len(recent) >= 6 and statistics.median(s["load1"] for s in recent[-6:]) > MAX_LOAD:
        found.append(f"load {last['load1']:.1f}")
    if last["disk_free_gib"] < MIN_DISK_GIB:
        found.append(f"disk free {last['disk_free_gib']:.0f} GiB")
    return found


def quiet_now():
    lt = time.localtime()
    now = lt.tm_hour * 60 + lt.tm_min
    return any(a * 60 + b <= now < c * 60 + d for a, b, c, d in QUIET)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--seconds", type=int, default=300)
    s.add_argument("--out", required=True)
    w = sub.add_parser("watch")
    w.add_argument("--baseline", required=True)
    w.add_argument("--stop-file", required=True)
    w.add_argument("--done-file", required=True)
    w.add_argument("--out", required=True)
    a = ap.parse_args()
    samples = []
    if a.cmd == "sample":
        end = time.monotonic() + a.seconds
        while time.monotonic() < end:
            samples.append(sample())
            time.sleep(5)
        json.dump(summarise(samples), open(a.out, "w"), indent=1)
        return 0
    baseline = json.load(open(a.baseline))
    while not os.path.exists(a.done_file):
        samples.append(sample())
        found = breaches(samples[-12:], baseline) or (["brief window"] if quiet_now() else [])
        if found:
            open(a.stop_file, "w").write("; ".join(found) + "\n")
            break
        time.sleep(5)
    json.dump(summarise(samples), open(a.out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
