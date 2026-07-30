# Runtime Render Validation Report — command-centre

**Executed:** 2026-07-06T07:42:48.052Z
**Browser:** 149.0.7827.55
**Scenarios:** 7

## Summary

- Total accessibility violations across all scenarios: **26**
- Scenarios with a visual regression (diff from baseline): **0**
- Scenarios with no baseline yet (first run): **0**

## Scenario: captains-chair

- Screenshot: `reports/pilot-run-screenshots/command-centre-captains-chair.png`

### Accessibility
- **[serious] color-contrast** — Elements must meet minimum color contrast ratio thresholds (1 node(s))
  - `.chair-clear`: Fix any of the following:   Element has insufficient color contrast of 3.03 (foreground color: #278a44, background color: #ccd8ec, font size: 9.8pt (13px), font weight: normal). Expected contrast ratio of 4.5:1
- **[moderate] landmark-one-main** — Document should have one main landmark (1 node(s))
  - `html`: Fix all of the following:   Document does not have a main landmark
- **[moderate] page-has-heading-one** — Page should contain a level-one heading (1 node(s))
  - `html`: Fix all of the following:   Page must have a level-one heading
- **[moderate] region** — All page content should be contained by landmarks (11 node(s))
  - `.header`: Fix any of the following:   Some page content is not contained by landmarks
  - `.status-item:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.status-item:nth-child(2)`: Fix any of the following:   Some page content is not contained by landmarks
  - `#last-update`: Fix any of the following:   Some page content is not contained by landmarks
  - `.notif-drawer-title`: Fix any of the following:   Some page content is not contained by landmarks
  - `#notif-list`: Fix any of the following:   Some page content is not contained by landmarks
  - `.global-search-icon`: Fix any of the following:   Some page content is not contained by landmarks
  - `#global-search-input`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-chair`: Fix any of the following:   Some page content is not contained by landmarks
  - `.control-bar > div:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.auto-refresh-toggle`: Fix any of the following:   Some page content is not contained by landmarks

### Visual Regression
Matches baseline exactly.

### CSS Variable Resolution
- `--sf-status-ok`: `#278A44`
- `--sf-status-warn`: `#9C5D10`
- `--sf-status-crit`: `#C43030`
- `--sf-status-ok-text`: `#1B5E20`
- `--sf-status-warn-text`: `#7A4610`
- `--sf-status-crit-text`: `#7A1616`
- `--sf-accent`: `#0C5A82`
- `--sf-border-subtle`: `#5a7d94`

## Scenario: command-console

- Screenshot: `reports/pilot-run-screenshots/command-centre-command-console.png`

### Accessibility
- **[serious] color-contrast** — Elements must meet minimum color contrast ratio thresholds (3 node(s))
  - `#cmd-escalations > .chair-clear`: Fix any of the following:   Element has insufficient color contrast of 3.03 (foreground color: #278a44, background color: #ccd8ec, font size: 9.8pt (13px), font weight: normal). Expected contrast ratio of 4.5:1
  - `#cmd-blockers > .chair-clear`: Fix any of the following:   Element has insufficient color contrast of 3.03 (foreground color: #278a44, background color: #ccd8ec, font size: 9.8pt (13px), font weight: normal). Expected contrast ratio of 4.5:1
  - `#cmd-approvals > .chair-clear`: Fix any of the following:   Element has insufficient color contrast of 3.03 (foreground color: #278a44, background color: #ccd8ec, font size: 9.8pt (13px), font weight: normal). Expected contrast ratio of 4.5:1
- **[moderate] landmark-one-main** — Document should have one main landmark (1 node(s))
  - `html`: Fix all of the following:   Document does not have a main landmark
- **[moderate] page-has-heading-one** — Page should contain a level-one heading (1 node(s))
  - `html`: Fix all of the following:   Page must have a level-one heading
- **[moderate] region** — All page content should be contained by landmarks (15 node(s))
  - `.header`: Fix any of the following:   Some page content is not contained by landmarks
  - `.status-item:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.status-item:nth-child(2)`: Fix any of the following:   Some page content is not contained by landmarks
  - `#last-update`: Fix any of the following:   Some page content is not contained by landmarks
  - `.notif-drawer-title`: Fix any of the following:   Some page content is not contained by landmarks
  - `#notif-list`: Fix any of the following:   Some page content is not contained by landmarks
  - `.global-search-icon`: Fix any of the following:   Some page content is not contained by landmarks
  - `#global-search-input`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-command > .dashboard-grid`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-command > .intel-card`: Fix any of the following:   Some page content is not contained by landmarks
  - `#cmd-mission-search`: Fix any of the following:   Some page content is not contained by landmarks
  - `#cmd-status-filter`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-command > .dept-links`: Fix any of the following:   Some page content is not contained by landmarks
  - `.control-bar > div:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.auto-refresh-toggle`: Fix any of the following:   Some page content is not contained by landmarks
- **[critical] select-name** — Select element must have an accessible name (1 node(s))
  - `#cmd-status-filter`: Fix any of the following:   Element does not have an implicit (wrapped) <label>   Element does not have an explicit <label>   aria-label attribute does not exist or is empty   aria-labelledby attribute does not exist, references elements that do not exist or references elements that are empty   Element has no title attribute   Element's default semantics were not overridden with role="none" or role="presentation"

### Visual Regression
Matches baseline exactly.

### CSS Variable Resolution
- `--sf-status-ok`: `#278A44`
- `--sf-status-warn`: `#9C5D10`
- `--sf-status-crit`: `#C43030`
- `--sf-status-ok-text`: `#1B5E20`
- `--sf-status-warn-text`: `#7A4610`
- `--sf-status-crit-text`: `#7A1616`
- `--sf-accent`: `#0C5A82`
- `--sf-border-subtle`: `#5a7d94`

## Scenario: sickbay

- Screenshot: `reports/pilot-run-screenshots/command-centre-sickbay.png`

### Accessibility
- **[moderate] landmark-one-main** — Document should have one main landmark (1 node(s))
  - `html`: Fix all of the following:   Document does not have a main landmark
- **[moderate] page-has-heading-one** — Page should contain a level-one heading (1 node(s))
  - `html`: Fix all of the following:   Page must have a level-one heading
- **[moderate] region** — All page content should be contained by landmarks (16 node(s))
  - `.header`: Fix any of the following:   Some page content is not contained by landmarks
  - `.status-item:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.status-item:nth-child(2)`: Fix any of the following:   Some page content is not contained by landmarks
  - `#last-update`: Fix any of the following:   Some page content is not contained by landmarks
  - `.notif-drawer-title`: Fix any of the following:   Some page content is not contained by landmarks
  - `#notif-list`: Fix any of the following:   Some page content is not contained by landmarks
  - `.global-search-icon`: Fix any of the following:   Some page content is not contained by landmarks
  - `#global-search-input`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-sickbay > .dashboard-grid`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-sickbay > .intel-grid > .intel-card:nth-child(1) > .intel-card-title`: Fix any of the following:   Some page content is not contained by landmarks
  - `#pulse-entry-form > div:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `#pulse-entry-form > div:nth-child(2)`: Fix any of the following:   Some page content is not contained by landmarks
  - `#pulse-notes`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-sickbay > .intel-grid > .intel-card:nth-child(2)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.control-bar > div:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.auto-refresh-toggle`: Fix any of the following:   Some page content is not contained by landmarks
- **[critical] select-name** — Select element must have an accessible name (4 node(s))
  - `#pulse-type`: Fix any of the following:   Element does not have an implicit (wrapped) <label>   Element does not have an explicit <label>   aria-label attribute does not exist or is empty   aria-labelledby attribute does not exist, references elements that do not exist or references elements that are empty   Element has no title attribute   Element's default semantics were not overridden with role="none" or role="presentation"
  - `#pulse-energy`: Fix any of the following:   Element does not have an implicit (wrapped) <label>   Element does not have an explicit <label>   aria-label attribute does not exist or is empty   aria-labelledby attribute does not exist, references elements that do not exist or references elements that are empty   Element has no title attribute   Element's default semantics were not overridden with role="none" or role="presentation"
  - `#pulse-mood`: Fix any of the following:   Element does not have an implicit (wrapped) <label>   Element does not have an explicit <label>   aria-label attribute does not exist or is empty   aria-labelledby attribute does not exist, references elements that do not exist or references elements that are empty   Element has no title attribute   Element's default semantics were not overridden with role="none" or role="presentation"
  - `#pulse-readiness`: Fix any of the following:   Element does not have an implicit (wrapped) <label>   Element does not have an explicit <label>   aria-label attribute does not exist or is empty   aria-labelledby attribute does not exist, references elements that do not exist or references elements that are empty   Element has no title attribute   Element's default semantics were not overridden with role="none" or role="presentation"

### Visual Regression
Matches baseline exactly.

### CSS Variable Resolution
- `--sf-status-ok`: `#278A44`
- `--sf-status-warn`: `#9C5D10`
- `--sf-status-crit`: `#C43030`
- `--sf-status-ok-text`: `#1B5E20`
- `--sf-status-warn-text`: `#7A4610`
- `--sf-status-crit-text`: `#7A1616`
- `--sf-accent`: `#0C5A82`
- `--sf-border-subtle`: `#5a7d94`

## Scenario: astrometrics

- Screenshot: `reports/pilot-run-screenshots/command-centre-astrometrics.png`

### Accessibility
- **[moderate] landmark-one-main** — Document should have one main landmark (1 node(s))
  - `html`: Fix all of the following:   Document does not have a main landmark
- **[moderate] page-has-heading-one** — Page should contain a level-one heading (1 node(s))
  - `html`: Fix all of the following:   Page must have a level-one heading
- **[moderate] region** — All page content should be contained by landmarks (15 node(s))
  - `.header`: Fix any of the following:   Some page content is not contained by landmarks
  - `.status-item:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.status-item:nth-child(2)`: Fix any of the following:   Some page content is not contained by landmarks
  - `#last-update`: Fix any of the following:   Some page content is not contained by landmarks
  - `.notif-drawer-title`: Fix any of the following:   Some page content is not contained by landmarks
  - `#notif-list`: Fix any of the following:   Some page content is not contained by landmarks
  - `.global-search-icon`: Fix any of the following:   Some page content is not contained by landmarks
  - `#global-search-input`: Fix any of the following:   Some page content is not contained by landmarks
  - `.intel-card:nth-child(1) > .intel-card-title > span`: Fix any of the following:   Some page content is not contained by landmarks
  - `#astro-or-brief`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-astrometrics > .intel-grid > .intel-card:nth-child(2)`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-astrometrics > .intel-grid > .intel-card:nth-child(3)`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-astrometrics > .intel-grid > .intel-card:nth-child(4)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.control-bar > div:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.auto-refresh-toggle`: Fix any of the following:   Some page content is not contained by landmarks

### Visual Regression
Matches baseline exactly.

### CSS Variable Resolution
- `--sf-status-ok`: `#278A44`
- `--sf-status-warn`: `#9C5D10`
- `--sf-status-crit`: `#C43030`
- `--sf-status-ok-text`: `#1B5E20`
- `--sf-status-warn-text`: `#7A4610`
- `--sf-status-crit-text`: `#7A1616`
- `--sf-accent`: `#0C5A82`
- `--sf-border-subtle`: `#5a7d94`

## Scenario: starfleet-records

- Screenshot: `reports/pilot-run-screenshots/command-centre-starfleet-records.png`

### Accessibility
- **[serious] color-contrast** — Elements must meet minimum color contrast ratio thresholds (1 node(s))
  - `#records-captures > .chair-clear`: Fix any of the following:   Element has insufficient color contrast of 3.03 (foreground color: #278a44, background color: #ccd8ec, font size: 9.8pt (13px), font weight: normal). Expected contrast ratio of 4.5:1
- **[moderate] landmark-one-main** — Document should have one main landmark (1 node(s))
  - `html`: Fix all of the following:   Document does not have a main landmark
- **[moderate] page-has-heading-one** — Page should contain a level-one heading (1 node(s))
  - `html`: Fix all of the following:   Page must have a level-one heading
- **[moderate] region** — All page content should be contained by landmarks (16 node(s))
  - `.header`: Fix any of the following:   Some page content is not contained by landmarks
  - `.status-item:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.status-item:nth-child(2)`: Fix any of the following:   Some page content is not contained by landmarks
  - `#last-update`: Fix any of the following:   Some page content is not contained by landmarks
  - `.notif-drawer-title`: Fix any of the following:   Some page content is not contained by landmarks
  - `#notif-list`: Fix any of the following:   Some page content is not contained by landmarks
  - `.global-search-icon`: Fix any of the following:   Some page content is not contained by landmarks
  - `#global-search-input`: Fix any of the following:   Some page content is not contained by landmarks
  - `#records-summary-panel > div:nth-child(1) > div`: Fix any of the following:   Some page content is not contained by landmarks
  - `#records-summary-text`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-records > .intel-grid`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-records > .intel-card:nth-child(3)`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-records > .intel-card:nth-child(4) > .intel-card-title`: Fix any of the following:   Some page content is not contained by landmarks
  - `#records-timeline`: Fix any of the following:   Some page content is not contained by landmarks
  - `.control-bar > div:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.auto-refresh-toggle`: Fix any of the following:   Some page content is not contained by landmarks

### Visual Regression
Matches baseline exactly.

### CSS Variable Resolution
- `--sf-status-ok`: `#278A44`
- `--sf-status-warn`: `#9C5D10`
- `--sf-status-crit`: `#C43030`
- `--sf-status-ok-text`: `#1B5E20`
- `--sf-status-warn-text`: `#7A4610`
- `--sf-status-crit-text`: `#7A1616`
- `--sf-accent`: `#0C5A82`
- `--sf-border-subtle`: `#5a7d94`

## Scenario: engineering

- Screenshot: `reports/pilot-run-screenshots/command-centre-engineering.png`

### Accessibility
- **[moderate] landmark-one-main** — Document should have one main landmark (1 node(s))
  - `html`: Fix all of the following:   Document does not have a main landmark
- **[moderate] page-has-heading-one** — Page should contain a level-one heading (1 node(s))
  - `html`: Fix all of the following:   Page must have a level-one heading
- **[moderate] region** — All page content should be contained by landmarks (11 node(s))
  - `.header`: Fix any of the following:   Some page content is not contained by landmarks
  - `.status-item:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.status-item:nth-child(2)`: Fix any of the following:   Some page content is not contained by landmarks
  - `#last-update`: Fix any of the following:   Some page content is not contained by landmarks
  - `.notif-drawer-title`: Fix any of the following:   Some page content is not contained by landmarks
  - `#notif-list`: Fix any of the following:   Some page content is not contained by landmarks
  - `.global-search-icon`: Fix any of the following:   Some page content is not contained by landmarks
  - `#global-search-input`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-engineering`: Fix any of the following:   Some page content is not contained by landmarks
  - `.control-bar > div:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.auto-refresh-toggle`: Fix any of the following:   Some page content is not contained by landmarks

### Visual Regression
Matches baseline exactly.

### CSS Variable Resolution
- `--sf-status-ok`: `#278A44`
- `--sf-status-warn`: `#9C5D10`
- `--sf-status-crit`: `#C43030`
- `--sf-status-ok-text`: `#1B5E20`
- `--sf-status-warn-text`: `#7A4610`
- `--sf-status-crit-text`: `#7A1616`
- `--sf-accent`: `#0C5A82`
- `--sf-border-subtle`: `#5a7d94`

## Scenario: advisors

- Screenshot: `reports/pilot-run-screenshots/command-centre-advisors.png`

### Accessibility
- **[moderate] landmark-one-main** — Document should have one main landmark (1 node(s))
  - `html`: Fix all of the following:   Document does not have a main landmark
- **[moderate] page-has-heading-one** — Page should contain a level-one heading (1 node(s))
  - `html`: Fix all of the following:   Page must have a level-one heading
- **[moderate] region** — All page content should be contained by landmarks (14 node(s))
  - `.header`: Fix any of the following:   Some page content is not contained by landmarks
  - `.status-item:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.status-item:nth-child(2)`: Fix any of the following:   Some page content is not contained by landmarks
  - `#last-update`: Fix any of the following:   Some page content is not contained by landmarks
  - `.notif-drawer-title`: Fix any of the following:   Some page content is not contained by landmarks
  - `#notif-list`: Fix any of the following:   Some page content is not contained by landmarks
  - `.global-search-icon`: Fix any of the following:   Some page content is not contained by landmarks
  - `#global-search-input`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-advisors > .dashboard-grid > .widget-container:nth-child(1) > .intel-card:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `#tab-advisors > .dashboard-grid > .widget-container:nth-child(1) > .intel-card:nth-child(2) > .intel-card-title`: Fix any of the following:   Some page content is not contained by landmarks
  - `#advisor-question`: Fix any of the following:   Some page content is not contained by landmarks
  - `#advisor-response-card`: Fix any of the following:   Some page content is not contained by landmarks
  - `.control-bar > div:nth-child(1)`: Fix any of the following:   Some page content is not contained by landmarks
  - `.auto-refresh-toggle`: Fix any of the following:   Some page content is not contained by landmarks

### Visual Regression
Matches baseline exactly.

### CSS Variable Resolution
- `--sf-status-ok`: `#278A44`
- `--sf-status-warn`: `#9C5D10`
- `--sf-status-crit`: `#C43030`
- `--sf-status-ok-text`: `#1B5E20`
- `--sf-status-warn-text`: `#7A4610`
- `--sf-status-crit-text`: `#7A1616`
- `--sf-accent`: `#0C5A82`
- `--sf-border-subtle`: `#5a7d94`
