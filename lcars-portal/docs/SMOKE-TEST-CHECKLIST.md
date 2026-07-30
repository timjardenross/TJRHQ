# Smoke Test Checklist — LCARS Web Portal Phase 1

Manual verification before sign-off / demo. Run from `lcars-portal/`.

## 0. Setup

```bash
cd lcars-portal
npm install
npm run build      # must finish with no type/lint errors
npm run start      # serves on http://localhost:3100
```

- [ ] `npm install` completes without errors.
- [ ] `npm run build` completes; output lists 8 page routes + `/`.
- [ ] Server starts and is reachable at `http://localhost:3100`.

## 1. Navigation & routing

- [ ] Visiting `/` redirects to `/captains-chair`.
- [ ] All 8 nav items load (HTTP 200): Captain's Chair, Missions, Engineering,
      Number One, XO Brief, Medical / Wellness, Operations, Knowledge Base.
- [ ] The nav highlights the **active** page (correct department colour).
- [ ] Browser back/forward navigates between pages correctly.
- [ ] An unknown route (e.g. `/warp`) shows the 404 page (not a crash).

Quick automated check:

```bash
for p in captains-chair missions engineering number-one xo-brief medical operations knowledge-base; do
  printf "/%s -> " "$p"; curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:3100/$p";
done
```

## 2. Component rendering

- [ ] **LCARSHeader** shows ship name, registry (NCC-170230), stardate and condition.
- [ ] **LCARSNav** rail renders all 8 entries with glyphs.
- [ ] **LCARSPanel** title rails are colour-accented per department.
- [ ] **StatusBadge** pills render with correct tone (blocked = red, etc.).
- [ ] **MissionCard** shows mission ID, priority, status and owner (Missions page).
- [ ] **DepartmentCard** shows lead, status and metrics (Captain's Chair grid).
- [ ] **AlertPanel** shows severity-coded alerts (Captain's Chair / Operations).

## 3. Per-page content

- [ ] **Captain's Chair** — daily brief, posture tiles, priorities, dept grid, alerts.
- [ ] **Missions** — summary stats, priority counts, active mission cards.
- [ ] **Engineering** — department cards + system readouts.
- [ ] **Number One** — crew roster cards + assigned work.
- [ ] **XO Brief** — intelligence summary, themes, section panels.
- [ ] **Medical / Wellness** — wellness metric tiles + recovery guidance.
- [ ] **Operations** — integration status list (Dashy/Slack/Commander/Context/Supabase) + alerts.
- [ ] **Knowledge Base** — category chips + article cards.

## 4. Department colours

- [ ] Command Gold, Engineering Orange, Operations Red, Medical Blue,
      Science Purple, Status Green each appear and are visually distinct.

## 5. Responsiveness

- [ ] Layout is usable at desktop width (nav as left rail).
- [ ] Layout is usable at mobile width (nav wraps to top, panels stack).

## 6. Non-regression

- [ ] `git status` shows changes only under `lcars-portal/`.
- [ ] No existing service config (Dashy/Slack/backend) was modified.
- [ ] Port 3100 does not collide with running services (8000 / 5050 / 3001).

---

**Result:** ____ / passed  ·  Tester: __________  ·  Date: __________
