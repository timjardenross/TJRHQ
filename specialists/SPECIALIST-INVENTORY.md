# Starship Endeavour Specialist Inventory

**Mission:** Provide a complete, discoverable inventory of all Starship Endeavour specialists across core, active, and future crew.

**Primary Purpose:** Enable rapid specialist identification and routing for new Starfleet Command missions.

**Last Updated:** June 7, 2026

---

## Core Crew (Active & Commissioned)

Active specialists with full governance, operational prompts, and approved deliverables in `core/crew/`.

### 1. Executive Officer (XO)
- **Registry ID:** SFE-002
- **Department:** Operations Division
- **Status:** Active, Commissioned
- **Reports To:** Captain TJR
- **Mission:** Coordinate priorities, missions, planning and execution across Starship Endeavour
- **Core Responsibilities:** Priority management, mission coordination, sprint planning, weekly reviews, cross-specialist alignment, governance authority
- **Governance Folder:** `core/crew/chief-of-staff/` (legacy folder name, title updated)
- **Runtime File:** `specialists/core-crew/Chief-of-Staff.md` (legacy file name, title updated)
- **Knowledge Pack:** `specialists/knowledge-packs/Chief-of-Staff-Knowledge.md`
- **Decision Authority:** Full
- **Domain Ownership:** Missions, Prioritisation, Governance, Operating Model

### 2. Chief Engineer
- **Registry ID:** SFE-003
- **Department:** Engineering Division
- **Status:** Active, Commissioned
- **Reports To:** Captain TJR
- **Mission:** Maintain, improve and evolve Starship Endeavour architecture, systems, integrations and technical capabilities
- **Core Responsibilities:** Architecture reviews, technical debt management, security oversight, repository governance, capability planning, platform recommendations
- **Governance Folder:** `core/crew/chief-engineer/`
- **Runtime File:** `specialists/core-crew/Chief-Engineer.md`
- **Knowledge Pack:** `specialists/knowledge-packs/Chief-Engineer-Knowledge.md`
- **Decision Authority:** Advisory
- **Domain Ownership:** Architecture, Infrastructure, Supabase, GitHub, Integrations

### 3. Coder Agent
- **Registry ID:** USS-TJR-004
- **Department:** Engineering Division
- **Status:** Active, Commissioned
- **Reports To:** Chief Engineer
- **Mission:** Implement, refactor and maintain USS TJR codebases
- **Core Responsibilities:** Coding, refactoring, bug fixes, documentation updates, repository improvements
- **Governance Folder:** `core/crew/coder-agent/`
- **Runtime File:** `specialists/core-crew/Coder-Agent.md`
- **Knowledge Pack:** `specialists/knowledge-packs/Coder-Agent-Knowledge.md`
- **Decision Authority:** Implementation only
- **Domain Ownership:** Code implementation and maintenance

### 4. QA & Test Officer
- **Registry ID:** USS-TJR-005
- **Department:** Engineering Division
- **Status:** Active, Commissioned
- **Reports To:** Chief Engineer
- **Mission:** Ensure quality, reliability and readiness of USS TJR capabilities
- **Core Responsibilities:** Testing, validation, release readiness, quality assurance
- **Governance Folder:** `core/crew/qa-test-officer/`
- **Runtime File:** `specialists/core-crew/QA-Test-Officer.md`
- **Knowledge Pack:** `specialists/knowledge-packs/QA-Test-Officer-Knowledge.md`
- **Decision Authority:** Quality assessment and validation
- **Domain Ownership:** Code quality, testing, review standards

### 5. Knowledge Officer
- **Registry ID:** USS-TJR-006
- **Department:** Operations Division
- **Status:** Active, Commissioned
- **Reports To:** Chief of Staff
- **Mission:** Maintain USS TJR knowledge quality, organisation and discoverability
- **Core Responsibilities:** Knowledge management, documentation structure, information governance, knowledge lifecycle management
- **Governance Folder:** `core/crew/knowledge-officer/`
- **Runtime File:** `specialists/core-crew/Knowledge-Officer.md`
- **Knowledge Pack:** `specialists/knowledge-packs/Knowledge-Officer-Knowledge.md`
- **Decision Authority:** Knowledge governance
- **Domain Ownership:** Knowledge assets, documentation, Notion, institutional memory

### 6. UX Design Officer
- **Registry ID:** USS-TJR-009
- **Department:** Experience Division
- **Status:** Active, Commissioned
- **Reports To:** Captain TJR
- **Mission:** Improve the usability, accessibility, simplicity and overall Captain experience of USS TJR
- **Core Responsibilities:** User experience reviews, workflow design, dashboard design, voice experience design, accessibility reviews, friction reduction
- **Governance Folder:** `core/crew/ux-design-officer/`
- **Runtime File:** `specialists/core-crew/UX-Design-Officer.md`
- **Knowledge Pack:** `specialists/knowledge-packs/UX-Design-Officer-Knowledge.md`
- **Decision Authority:** Advisory only
- **Domain Ownership:** User experience, accessibility, workflow design, dashboard design

### 7. Medical Officer
- **Registry ID:** USS-TJR-008
- **Department:** Health Division
- **Status:** Active, Commissioned (Core Crew)
- **Reports To:** Captain TJR
- **Mission:** Support Captain TJR health and wellness
- **Governance Folder:** `core/crew/medical-officer/`
- **Runtime File:** `specialists/core-crew/Medical-Officer.md`
- **Knowledge Pack:** `specialists/knowledge-packs/Medical-Officer-Knowledge.md`
- **Decision Authority:** Advisory
- **Domain Ownership:** Health, wellness, medical guidance

---

## Planned/Future Crew (Not Yet Commissioned)

Future specialists with defined charters and knowledge packs but no core governance folder or runtime activation.

### 8. Research Officer
- **Registry ID:** USS-TJR-006
- **Department:** Intelligence Division
- **Status:** Planned (Future)
- **Maturity Level:** 2 (Defined)
- **Operational Readiness:** Defined
- **Mission:** Provide evidence-informed research, intelligence gathering, and analytical support to USS TJR
- **Core Responsibilities:** Research, analysis, intelligence reporting, design research review
- **Runtime File:** `specialists/future-crew/Research-Officer.md`
- **Knowledge Pack:** `specialists/knowledge-packs/Research-Officer-Knowledge.md`
- **Decision Authority:** Advisory only
- **Domain Ownership (Future):** Technology, AI, operational resilience, industry intelligence, market trends, user needs

### 9. Operations Officer
- **Registry ID:** USS-TJR-007
- **Department:** Operations Division
- **Status:** Planned (Future)
- **Maturity Level:** 2 (Defined)
- **Operational Readiness:** Defined
- **Mission:** Improve how Captain TJR operates, plans, and executes
- **Core Responsibilities:** Planning, workflow improvement, operational coordination
- **Runtime File:** `specialists/future-crew/Operations-Officer.md`
- **Decision Authority:** Advisory only
- **Domain Ownership (Future):** Productivity, planning, life administration, workflow design

### 10. UX Officer (Future Expansion)
- **Registry ID:** (Future)
- **Department:** Experience Division
- **Status:** Planned (Future)
- **Mission:** (Defined in future-crew/)
- **Runtime File:** `specialists/future-crew/UX-Officer.md`
- **Status Note:** Potential expansion of UX Design Officer role

### 11. Knowledge Architect
- **Registry ID:** (Future)
- **Department:** Operations Division
- **Status:** Planned (Future)
- **Mission:** (Defined in future-crew/)
- **Runtime File:** `specialists/future-crew/Knowledge-Architect.md`
- **Status Note:** Knowledge governance expansion role

### 12. Product Designer
- **Registry ID:** (Future)
- **Department:** Experience Division
- **Status:** Planned (Future)
- **Mission:** (Defined in future-crew/)
- **Runtime File:** `specialists/future-crew/Product-Designer.md`
- **Status Note:** Product-focused design role

---

## Specialist Categorization by Domain

### Operations Domain
- Chief of Staff (Owner)
- Knowledge Officer (Owner)
- Operations Officer (Future)

### Engineering Domain
- Chief Engineer (Owner)
- Coder Agent (Implementation)
- QA & Test Officer (Validation)

### Experience Domain
- UX Design Officer (Owner)
- UX Officer (Future expansion)

### Health Domain
- Medical Officer (Owner)

### Intelligence Domain
- Research Officer (Future Owner)

### Architecture Domain
- Chief Engineer (Primary)
- All specialists (Support)

---

## Quick Reference: Specialist Routing

| Need | Contact | Backup |
|------|---------|--------|
| Mission coordination, priorities, governance | Chief of Staff | Captain TJR |
| Architecture, infrastructure, GitHub, Supabase | Chief Engineer | Captain TJR |
| Code implementation, refactoring, maintenance | Coder Agent | Chief Engineer |
| Testing, validation, quality assurance | QA Test Officer | Chief Engineer |
| Knowledge, documentation, Notion, information architecture | Knowledge Officer | Chief of Staff |
| UX, accessibility, workflow, dashboard design | UX Design Officer | Chief Engineer (technical) |
| Health, wellness, medical guidance | Medical Officer | Captain TJR |
| Research, analysis, intelligence (when active) | Research Officer | Captain TJR |
| Operations, planning, workflow optimization (when active) | Operations Officer | Chief of Staff |

---

## Summary Statistics

- **Total Specialists Defined:** 12
- **Active/Commissioned:** 7
- **Planned/Future:** 5
- **Core Governance Folders:** 7
- **Knowledge Packs Available:** 8+
- **Departments:** Operations, Engineering, Experience, Health, Intelligence (future)
- **Last Governance Update:** June 2026

---

## Discovery Completeness

✅ All `specialists/core-crew/*.md` files discovered  
✅ All `specialists/future-crew/*.md` files discovered  
✅ All `core/crew/*/` governance folders mapped  
✅ All knowledge packs located and inventoried  
✅ Registry mappings verified against canonical sources  
✅ Status alignment confirmed (active vs. future)

