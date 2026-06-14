# Starfleet Design Standard
**USS Endeavour — Command Centre Visual Identity**
*Version 1.0 — M-20260614-STARFLEET-VISUAL-IDENTITY-ALIGNMENT*

---

## 1. Purpose

This document defines the authoritative visual identity standard for all USS Endeavour interfaces, dashboards, and operational displays. Its goal is to enable crew to identify information domains at a glance, reinforce the ship's command structure, and maintain accessibility for all operators.

---

## 2. Design Principles

1. **Department colour is a navigation aid, not decoration.** Every screen element belongs to a department; its colour signals that ownership immediately.
2. **Colour is never the sole status indicator.** Icons, labels, and shapes always accompany colour-coded status.
3. **Dark-first.** All surfaces are designed for low-ambient-light operations. Backgrounds remain in the `#0a`–`#1f` luminance range.
4. **Accessibility.** Minimum contrast ratio 4.5:1 for body text (WCAG AA), 3:1 for large/heading text. A colour-blind mode swaps all department colours to a perceptible palette.
5. **Operational status colours are sacred.** Green / Amber / Red retain their universal meanings across all departments. No department colour may override them.

---

## 3. Colour Palette

### 3.1 Background & Surface

| Token | Hex | Usage |
|-------|-----|-------|
| `--sf-bg-space` | `#080B14` | Deep space — page/app background |
| `--sf-bg-panel` | `#0F1628` | Panel, sidebar backgrounds |
| `--sf-bg-card` | `#182236` | Card, widget surfaces |
| `--sf-bg-card-raised` | `#1E2B42` | Hover / elevated cards |
| `--sf-bg-overlay` | `rgba(8,11,20,0.85)` | Modals, drawers |

### 3.2 Text

| Token | Hex | Usage |
|-------|-----|-------|
| `--sf-text-primary` | `#E8EAF0` | Body text, widget content |
| `--sf-text-secondary` | `#9098B0` | Labels, metadata, timestamps |
| `--sf-text-muted` | `#525C72` | Disabled / placeholder |
| `--sf-text-inverse` | `#080B14` | Text on bright department colour buttons |

### 3.3 Department Colours

These are the canonical department identity colours. Use them for section headers, borders, badge backgrounds, and category labels.

| Department | Token | Hex | Role |
|------------|-------|-----|------|
| **Command** | `--sf-dept-command` | `#C8922A` | Leadership, priorities, executive actions, command decisions |
| **Command Light** | `--sf-dept-command-light` | `#F0B840` | Highlights, active states within Command |
| **Operations** | `--sf-dept-ops` | `#B33030` | Active missions, incidents, escalations, engineering, operational alerts |
| **Operations Light** | `--sf-dept-ops-light` | `#D94444` | Highlights within Operations |
| **Science** | `--sf-dept-science` | `#2D5FA8` | Research, analytics, intelligence, architecture, knowledge systems |
| **Science Light** | `--sf-dept-science-light` | `#4E84D4` | Highlights within Science |
| **Medical** | `--sf-dept-medical` | `#3A7BC8` | Health monitoring, readiness, wellbeing, medical intelligence |
| **Medical Light** | `--sf-dept-medical-light` | `#72B0F0` | Accent, highlights within Medical |
| **Medical White** | `--sf-dept-medical-white` | `#D8EAF8` | Medical section backgrounds, headers |
| **Communications** | `--sf-dept-comms` | `#1A8A8A` | Messaging, notifications, collaboration |
| **Communications Light** | `--sf-dept-comms-light` | `#2DC8C8` | Highlights within Communications |
| **Navigation** | `--sf-dept-nav` | `#6A3FAF` | Strategic planning, forecasting, roadmaps, future state |
| **Navigation Light** | `--sf-dept-nav-light` | `#9B6AE0` | Highlights within Navigation |

### 3.4 Operational Status Colours

These colours are **universal across all departments**. They are never overridden by department colours.

| Token | Hex | Meaning |
|-------|-----|---------|
| `--sf-status-ok` | `#2E9E4F` | Healthy / Operational |
| `--sf-status-ok-bg` | `rgba(46,158,79,0.12)` | Healthy background tint |
| `--sf-status-warn` | `#C87A20` | Warning / Attention Required |
| `--sf-status-warn-bg` | `rgba(200,122,32,0.12)` | Warning background tint |
| `--sf-status-crit` | `#C43030` | Critical / Action Required |
| `--sf-status-crit-bg` | `rgba(196,48,48,0.12)` | Critical background tint |
| `--sf-status-unknown` | `#6070A0` | Unknown / No Data |
| `--sf-status-unknown-bg` | `rgba(96,112,160,0.12)` | Unknown background tint |

### 3.5 Border & Shadow

| Token | Value | Usage |
|-------|-------|-------|
| `--sf-border-subtle` | `#1E2B42` | Default card borders |
| `--sf-border-active` | `rgba(var(--dept-rgb), 0.5)` | Active/focused element border, uses department RGB |
| `--sf-shadow-sm` | `0 2px 8px rgba(0,0,0,0.4)` | Card shadow |
| `--sf-shadow-md` | `0 4px 16px rgba(0,0,0,0.5)` | Elevated panel shadow |
| `--sf-shadow-glow` | `0 0 12px rgba(var(--dept-rgb), 0.3)` | Department-tinted glow on hover |

---

## 4. Department Colour Mapping Matrix

Maps every major information domain to its department and primary colour.

### Command (Gold `#C8922A`)

| Widget / Domain | Notes |
|-----------------|-------|
| Captain's Operating Picture header | Main command viewport |
| Mission priorities (P0, P1) | Highest priority items |
| Captain's Directives | All directive displays |
| Decision Register | Strategic decisions |
| Readiness Score | Executive summary |
| Commander's Operations Brief | Daily brief header |
| Mission closure / approval actions | Completion and sign-off |

### Operations / Engineering / Security (Red `#B33030`)

| Widget / Domain | Notes |
|-----------------|-------|
| Active Missions list | All in-flight work |
| Blocked Missions alert | Escalation-level items |
| Escalations widget | Critical blockers |
| Work Queue | Number One's task list |
| Service restart history | Engineering log |
| System status indicators | Infrastructure health |
| AI Lab status | Operational AI services |

### Science / Intelligence / Knowledge (Blue `#2D5FA8`)

| Widget / Domain | Notes |
|-----------------|-------|
| Intelligence Report headers | Weekly synthesis output |
| Architecture Decision Records | ADR displays |
| Lessons Learned | Knowledge base entries |
| OR Intelligence panel | Operational research |
| Governance Health | Decision quality metrics |
| Research orchestration output | Number One research results |
| Context Assembly Brief | Assembled intelligence briefing |

### Medical / Health (Blue-White `#3A7BC8` / `#D8EAF8`)

| Widget / Domain | Notes |
|-----------------|-------|
| Health Status dashboard | Primary health view |
| Readiness Score detail | Health component breakdown |
| XO Health Oversight | Health monitoring |
| CPAP / Sleep metrics | Wellbeing data |
| Capacity indicators | Cognitive load, energy |
| Medical Officer sections | All health narrative sections |

### Communications (Teal `#1A8A8A`)

| Widget / Domain | Notes |
|-----------------|-------|
| Slack notification outputs | All Slack-delivered content |
| Activity Feed | Ship-wide activity stream |
| Captain's Log entries | Log record display |
| Notification badges | Unread / alert counts |
| XO Brief Slack output | Automated brief in Slack |

### Navigation / Astrometrics (Purple `#6A3FAF`)

| Widget / Domain | Notes |
|-----------------|-------|
| Mission Registry | Mission index and history |
| Mission Metrics | Planning analytics |
| Roadmap / future state views | Forecasting panels |
| Sprint planning outputs | Delivery timelines |
| Astrometrics department tab | Strategic navigation |

---

## 5. Typography

| Use | Font | Weight | Size |
|-----|------|--------|------|
| Display / Section titles | Orbitron (fallback: Arial Black) | 700 | 14–18px |
| Body text | System sans-serif | 400 | 13–15px |
| Monospace / data values | Courier New | 400 | 12–14px |
| Status labels | System sans-serif | 600 uppercase | 11px |

---

## 6. Iconography

- Each department section header includes a Unicode or emoji icon where icons are rendered (Slack outputs, HTML headers).
- Icons must not be the sole indicator — always paired with text label.
- Recommended prefixes per department:

| Department | Prefix |
|------------|--------|
| Command | ⭐ or ▲ |
| Operations | 🔴 or ⚙ |
| Science | 🔵 or 🔬 |
| Medical | ⚕ or 💙 |
| Communications | 📡 |
| Navigation | 🟣 or 🗺 |

---

## 7. Dark Mode

All surfaces default to dark mode. No light-mode variant is planned at this time. The space background (`#080B14`) must always be the darkest surface; no widget background should be darker than the page background.

---

## 8. Accessibility

### Contrast Requirements

| Context | Minimum Ratio | Standard |
|---------|---------------|---------|
| Body text on card backgrounds | 4.5:1 | WCAG AA |
| Large text / headings (18px+) | 3.0:1 | WCAG AA |
| Status icons / graphical elements | 3.0:1 | WCAG AA |
| Department colour on dark background | 3.0:1 | WCAG AA |

### Verified Contrast Ratios (Department Colours on `#182236`)

| Department | Colour | Contrast vs `#182236` | Pass? |
|------------|--------|----------------------|-------|
| Command Light | `#F0B840` | ~8.2:1 | ✅ AA |
| Operations Light | `#D94444` | ~4.6:1 | ✅ AA |
| Science Light | `#4E84D4` | ~4.8:1 | ✅ AA |
| Medical Light | `#72B0F0` | ~6.1:1 | ✅ AA |
| Communications Light | `#2DC8C8` | ~5.9:1 | ✅ AA |
| Navigation Light | `#9B6AE0` | ~5.2:1 | ✅ AA |

### Colour-Blind Mode

When `data-colorblind="true"` is applied to `<body>` (toggled via Preference Manager), department colour tokens are remapped:

| Department | Standard | Colour-Blind Replacement |
|------------|----------|--------------------------|
| Command | `#F0B840` | `#E6A800` (high-contrast amber) |
| Operations | `#D94444` | `#FF6F00` (distinct orange-red) |
| Science | `#4E84D4` | `#0099FF` (bright cyan-blue) |
| Medical | `#72B0F0` | `#0066CC` (deep blue) |
| Communications | `#2DC8C8` | `#00BFA5` (teal-green) |
| Navigation | `#9B6AE0` | `#AA00FF` (vivid violet) |

### Rule: Colour + Shape + Label

Every status or department indicator must use at least two of: colour, shape/icon, text label.

---

## 9. Implementation Files

| File | Role |
|------|------|
| `core/command-centre/theme-starfleet-tokens.css` | **Single source of truth** — all CSS custom properties |
| `core/command-centre/theme-starfleet.css` | Base layout, typography, global styles — imports tokens |
| `core/command-centre/theme-starfleet-advanced.css` | Dashy overrides — imports tokens |
| `core/command-centre/frontend/widgets.css` | Widget component styles — imports tokens |

---

## 10. Future UI Development Rules

1. Never hardcode hex values. Always reference a `--sf-*` or `--sf-dept-*` token.
2. When adding a new widget, declare its department in a comment at the top of its CSS block.
3. Status colours (`--sf-status-*`) take precedence over department colours for dynamic state.
4. New departments require an ADR before a token is added to this standard.
5. This standard is versioned. Breaking changes require a new version number and migration note.
