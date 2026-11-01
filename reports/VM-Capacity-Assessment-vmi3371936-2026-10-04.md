# VM Capacity Assessment: vmi3371936

Date: 2026-10-04
Scope requested: last 90 days of utilisation
Scope achieved: about 9.6 days (since last boot) plus 7 hours of `sar` plus point-in-time snapshots

**Limitation:** the VM has no 90-day monitoring history, so a true 90-day assessment is not possible. Every figure below is labelled by the window it covers. Facts and assumptions are kept separate.

## 1. Executive summary

- **Verdict: keep the VM as-is. Do not resize.** Confidence is medium-high for the next 30 to 60 days and low for any 90-day claim.
- Average CPU since boot is about 10% busy, with no steal and iowait at 0.26%. Memory has about 15 GiB available of 23 GiB. Disk is 31% used and inodes 3%.
- No OOM kills or I/O errors appear in the kernel journal for the 9 days it covers.
- The real risk is blindness, not capacity. `sysstat` holds only 7 hours of data, the journal covers one boot, and no metrics stack is installed. Fix this first, then re-run this assessment after 30 days of data.
- Business view: the VM is not close to a ceiling, and nothing here justifies a cost action. The disk is the only oversized resource, and shrinking an ext4 root volume is risky for a small saving.

## 2. Current VM profile

| Item | Value | Basis |
|---|---|---|
| Hostname | vmi3371936 | Fact |
| Provider / region | Not determined. The "vmi" hostname pattern suggests Contabo, but that is an assumption. Cloud metadata endpoints did not respond. | Gap |
| Hypervisor | KVM (QEMU i440FX). Instance type name unknown. | Fact |
| Compute | 8 vCPU, AMD EPYC, 1 thread per core | Fact |
| Memory | 23 GiB (24,032 MiB) | Fact |
| Swap | 8 GiB swapfile | Fact |
| OS | Ubuntu 24.04.4 LTS, kernel 6.8.0-139 | Fact |
| Disk | One 400 GB virtual disk (`sda`): ext4 root 388 GB plus 105 MB EFI partition | Fact |
| Uptime | Up since 2026-09-24 20:09 (9d 14h) | Fact |
| Workloads | About 37 running services: Starship/HQ stack (model-router, XO Telegram bot, intelligence scheduler, Phoenix tracing, LCARS portal, Chatterbox TTS). Docker: Infisical (with Postgres and Redis), Uptime Kuma, changedetection.io. | Fact |

Largest memory consumers (RSS):

| Process | RSS |
|---|---|
| Chatterbox TTS | about 4.0 GB |
| Node `dist/main.mjs` | 0.5 GB |
| Intelligence scheduler | 0.5 GB |
| Phoenix | 0.47 GB |
| XO bot | 0.43 GB |

## 3. Utilisation findings

| Metric | Window | Result | Basis |
|---|---|---|---|
| CPU average | Since boot (9.6d, `/proc/stat`) | About 10% busy, 0.26% iowait, 0 steal | Fact |
| CPU, recent hours | 7h (`sar`) | 10.9% user, 5.0% sys, 83.8% idle | Fact |
| Load average | 7h | Mean 2.4 on 8 vCPU (0.3 per core); peak 4.3 observed during assessment | Fact |
| CPU pressure (PSI) | Snapshot | `some` avg300 about 2%, `full` 0 | Fact |
| Memory | 7h average | About 6.4 GiB used, 16.2 GiB available; commit 41% of RAM+swap | Fact |
| Memory, now | Snapshot | 7.8 GiB used, 15 GiB available | Fact |
| Swap | Snapshot | 175 MiB of 8 GiB used; si/so near 0 | Fact |
| Memory pressure (PSI) | Snapshot | `some` 0, `full` 0 | Fact |
| Disk I/O | 7h | `sda` about 18 tps, 5.8 ms await, 2.8% util | Fact |
| IO pressure (PSI) | Snapshot | Brief blips (avg60 `some` 3.4%, `full` 2.3%) | Fact |
| Network | 7h | eth0 about 520 kB/s in, 3 kB/s out | Fact |
| Disk space | Snapshot | 119 GB used, 270 GB free (31%) | Fact |
| Inodes | Snapshot | 3% used (1.19M of 51.6M) | Fact |
| OOM / I/O errors | Journal, 9d | 0 matches | Fact |
| Restarts | Last 90d (`last -x`) | 7 boots: 23 Aug (two, 5 min apart), 4 Sep, 6 Sep (two, 1 min apart), 18 Sep, 24 Sep. Causes not recorded. | Fact |
| Peaks, sustained periods, recurring spikes | 90d | Cannot be assessed | Gap |

### Disk breakdown (119 GB used)

| Path | Size | Note |
|---|---|---|
| `/usr` | 49 GB | 43 GB of it in `/usr/share`, unusually large (not investigated) |
| `/opt` | 29 GB | 26 GB is `/opt/starship-endeavour` |
| `/root` | 15 GB | Includes 4.9 GB cache, 3.5 GB Ollama staging, 2.1 GB Ollama backup |
| `/var` | 12 GB | `/var/lib` 11 GB |
| `/home` | 5.7 GB | Almost all `jarvis-user` |

Docker: images 9.9 GB (3.2 GB reclaimable), volumes 243 MB, build cache empty. Docker is not a growth risk.

## 4. Headroom assessment

| Resource | Normal ops | Peak | Growth (3 to 6 months) | Confidence |
|---|---|---|---|---|
| CPU | Ample (about 85% idle) | Probably ample, but peaks are unmeasured | Fine unless heavy inference or batch jobs are added | Medium |
| Memory | Ample (about 15 GiB free) | Unmeasured; a second TTS or model process could add 4 GB or more | Fine for about 2x the current footprint | Medium |
| Disk space | Ample | Logs and images are the likely growth | Growth rate unknown, so runway cannot be stated | Low |
| Disk I/O | Ample | Unmeasured | Fine | Medium |
| Network | Trivial | Unmeasured | Fine | Medium |

## 5. Risks and bottlenecks

| # | Risk | Likelihood | Impact | Basis |
|---|---|---|---|---|
| 1 | Blind operation: 7h of `sysstat`, journal covers one boot, no Prometheus or Netdata. A capacity incident could not be diagnosed after the fact. | Certain | High | Fact |
| 2 | Unexplained reboots: seven boots in 90 days with no recorded cause, including two pairs a few minutes apart (23 Aug, 6 Sep). Could be provider maintenance, kernel updates or crashes. | Medium | Medium to high | Fact (cause is a gap) |
| 3 | Single-VM concentration: secrets (Infisical), bots, portal and tracing share one KVM host with no redundancy. | Certain | High | Fact |
| 4 | Concurrent bursts: many 5 to 30 minute timers plus interactive sessions overlap on one host. | Low to medium | Low to medium | Assumption |
| 5 | Memory step-change: the 4 GB resident TTS process and the sustained-CPU Node service are plausible drivers if growth appears. | Low | Medium | Assumption |
| 6 | Disk creep from logs and images on a 388 GB volume. | Low | Low | Assumption |

## 6. Recommendations

| # | Action | Priority | Confidence |
|---|---|---|---|
| R1 | Keep the VM as-is. No resize, no instance-family change. | Decision | Medium-high (30 to 60 days) |
| R2 | Fix observability this week: set `HISTORY=90` in `/etc/sysstat/sysstat`; find out why `sa*` files only start at 11:04 today; confirm `sysstat-collect.timer` runs every 1 to 5 minutes; make the journal persistent (`Storage=persistent`, `SystemMaxUse=1G`); optionally add node_exporter or Netdata. | High, low effort | High |
| R3 | Record the cause of each reboot: check provider maintenance notices and `apt` and `unattended-upgrades` logs for the reboot dates. | High | Medium |
| R4 | Alert instead of upsizing. Alert on memory available under 20%, sustained swap in/out, load per core above 1.0 for 15 minutes, disk above 75% or growing more than 1 GB/day, iowait above 10%. | Medium | High |
| R5 | Check the Node service: about 1,719 CPU-minutes in 9 days for a service that should be mostly idle. Confirm that is expected. | Medium | Medium |
| R6 | Do not shrink the disk. 270 GB free is cheap relative to migration risk. Revisit only if the provider bills per GB. | Low | Medium |
| R7 | Optional cleanup of about 5.6 GB of Ollama staging and backup directories, 3.2 GB of reclaimable Docker images and 4.9 GB `/root/.cache`. Investigate the 43 GB in `/usr/share`. | Low | Medium |
| R8 | Re-run this assessment after 30 days of data. If any peak is above 70% CPU or 80% memory, consider scaling up. If average CPU stays near 10%, consider a cost review of a smaller plan. | Follow-up | n/a |

Not recommended now: vertical resize, horizontal scale-out, instance family change.

## 7. Data gaps and follow-up checks

| Gap | Why it matters | How to close it |
|---|---|---|
| 90-day CPU, memory, disk and network history | Peaks, sustained periods, recurring spikes | R2 plus 30 more days |
| Cloud provider, plan, region and price | Cost and rightsizing options | Provider panel or invoice |
| Provider-side CPU, steal and network graphs | May provide some history now | Provider dashboard |
| Reboot causes | Reliability | `/var/log/apt/history.log`, `unattended-upgrades` log, provider tickets |
| Disk growth rate | Runway | Log `df` weekly |
| Application latency or SLOs (portal, bots, model-router) | User-facing view of headroom | Phoenix tracing; Uptime Kuma heartbeat history (not read) |
| Backup and maintenance windows | Strain periods | Not found on the box; confirm whether backups exist |
| Orphaned Coolify volumes (`coolify-db`, `coolify-redis`, from 19 Jul) | Possible wasted space or stale state | Confirm whether still in use |

## Method

Data was collected on 2026-10-04 with `hostnamectl`, `lscpu`, `free`, `df`, `lsblk`, `/proc/stat`, `/proc/pressure/*`, `sar` (7h available), `iostat`, `vmstat`, `journalctl`, `last -x`, `docker system df` and `du`. No changes were made to the VM.
