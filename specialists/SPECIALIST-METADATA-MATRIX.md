# USS TJR Specialist Metadata Matrix

**Purpose:** Provide structured metadata for all specialists enabling rapid lookup, filtering, and decision-making.

**Use Case:** Support automated specialist selection, compatibility assessment, and mission routing algorithms.

**Last Updated:** June 7, 2026

---

## Active Core Crew Metadata

| Field | Chief of Staff | Chief Engineer | Coder Agent | QA Test Officer | Knowledge Officer | UX Design Officer | Medical Officer |
|-------|---|---|---|---|---|---|---|
| **Registry ID** | USS-TJR-002 | USS-TJR-003 | USS-TJR-004 | USS-TJR-005 | USS-TJR-006 | USS-TJR-009 | USS-TJR-008 |
| **Status** | Active | Active | Active | Active | Active | Active | Active |
| **Department** | Operations | Engineering | Engineering | Engineering | Operations | Experience | Health |
| **Reports To** | Captain TJR | Captain TJR | Chief Engineer | Chief Engineer | Chief of Staff | Captain TJR | Captain TJR |
| **Authority Level** | Full | Advisory | Implementation | Advisory | Governance | Advisory | Advisory |
| **Decision Authority** | Prioritisation, decomposition | Architecture | Implementation | Quality | Knowledge governance | UX assessment | Wellness guidance |
| **Escalation Recipient** | Captain TJR | Captain TJR | Chief Engineer | Chief Engineer | Chief of Staff | Chief Engineer | Captain TJR |
| **Primary Domains** | Missions, Governance, Prioritisation | Architecture, Infrastructure | Code implementation | Testing, Quality | Documentation, Knowledge | UX, Accessibility, Design | Health, Wellness |
| **Support Domains** | Crew, Architecture | Missions, Code quality | Refactoring | Architecture | Crew, Missions | Architecture feasibility | Personal support |
| **Runtime File** | `specialists/core-crew/Chief-of-Staff.md` | `specialists/core-crew/Chief-Engineer.md` | `specialists/core-crew/Coder-Agent.md` | `specialists/core-crew/QA-Test-Officer.md` | `specialists/core-crew/Knowledge-Officer.md` | `specialists/core-crew/UX-Design-Officer.md` | `specialists/core-crew/Medical-Officer.md` |
| **Knowledge Pack** | Chief-of-Staff-Knowledge.md | Chief-Engineer-Knowledge.md | Coder-Agent-Knowledge.md | QA-Test-Officer-Knowledge.md | Knowledge-Officer-Knowledge.md | UX-Design-Officer-Knowledge.md | Medical-Officer-Knowledge.md |
| **Governance Folder** | `core/crew/chief-of-staff/` | `core/crew/chief-engineer/` | `core/crew/coder-agent/` | `core/crew/qa-test-officer/` | `core/crew/knowledge-officer/` | `core/crew/ux-design-officer/` | `core/crew/medical-officer/` |
| **Operational Prompt** | Yes | Yes | Yes | Yes | Yes | Yes | Likely |
| **Activation Plan** | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| **Framework Count** | 5+ | 10+ | 4+ | 6+ | 3+ | 11+ | 6+ |

---

## Future Crew Metadata

| Field | Research Officer | Operations Officer | UX Officer | Knowledge Architect | Product Designer |
|-------|---|---|---|---|---|
| **Registry ID** | USS-TJR-006 | USS-TJR-007 | TBD | TBD | TBD |
| **Status** | Planned | Planned | Planned | Planned | Planned |
| **Department** | Intelligence | Operations | Experience | Operations | Experience |
| **Reports To** | Captain TJR | Captain TJR | TBD | TBD | TBD |
| **Authority Level** | Advisory | Advisory | Advisory | Advisory | Advisory |
| **Decision Authority** | Research findings, analysis | Operations, planning | UX assessment | Knowledge governance | Design decisions |
| **Escalation Recipient** | Captain TJR | Chief of Staff | Chief Engineer | Chief of Staff | TBD |
| **Primary Domains** | Research, Analysis, Intelligence | Planning, Operations, Workflow | UX, Design | Knowledge, Information Architecture | Product Design, UX |
| **Support Domains** | UX research, Evidence | Prioritisation, Crew | Architecture, UX standards | Crew, Documentation | Product Strategy, UX |
| **Runtime File** | `specialists/future-crew/Research-Officer.md` | `specialists/future-crew/Operations-Officer.md` | `specialists/future-crew/UX-Officer.md` | `specialists/future-crew/Knowledge-Architect.md` | `specialists/future-crew/Product-Designer.md` |
| **Knowledge Pack** | Research-Officer-Knowledge.md | Operations-Officer-Knowledge.md (TBD) | TBD | TBD | TBD |
| **Governance Folder** | Not yet | Not yet | Not yet | Not yet | Not yet |
| **Operational Prompt** | Not yet | Not yet | Not yet | Not yet | Not yet |
| **Activation Plan** | Yes | Yes | Likely | Likely | Likely |
| **Framework Count** | 3+ | 4+ | TBD | TBD | TBD |
| **Maturity Level** | 2 (Defined) | 2 (Defined) | TBD | TBD | TBD |

---

## Specialist Retrieval Domains

Specialists can be retrieved by these domain keywords:

| Specialist | Domain Keywords | Retrieval Allowed Types |
|---|---|---|
| Chief of Staff | Missions, Governance, Prioritisation, Crew | Mission, Crew, Architecture |
| Chief Engineer | Architecture, Infrastructure, GitHub, Supabase, Code quality | Architecture, ADR, Mission |
| Coder Agent | Code, Implementation, Refactoring, Bug fixes | Mission, Code, Implementation |
| QA Test Officer | Testing, Quality, Validation, Release | Mission, Quality, Validation |
| Knowledge Officer | Documentation, Knowledge Assets, Notion, Institutional Memory | Crew, Mission, Architecture |
| UX Design Officer | User Experience, Accessibility, Workflows, Dashboards, Design | Architecture, Mission, Design |
| Medical Officer | Health, Wellness, Medical guidance | Health, Wellness, Medical |
| Research Officer (Future) | Research, Analysis, Intelligence, Technology, AI, Industry | Research, Intelligence, Analysis |
| Operations Officer (Future) | Planning, Workflow, Execution, Productivity, Operations | Operations, Planning, Workflow |

---

## Specialist Expertise Taxonomy

### Operations & Governance
- **Primary:** Chief of Staff
- **Secondary:** Knowledge Officer, Operations Officer (future)
- **Domains:** Priority management, mission coordination, sprint planning, governance, institutional memory
- **Key Frameworks:** Mission governance, decomposition patterns, commissioning framework

### Engineering & Architecture
- **Primary:** Chief Engineer
- **Secondary:** Coder Agent, QA Test Officer
- **Domains:** Architecture design, code implementation, testing, technical debt, security, infrastructure
- **Key Frameworks:** Architecture reviews, technical debt, security standards, testing strategy

### User Experience & Design
- **Primary:** UX Design Officer
- **Secondary:** UX Officer (future), Product Designer (future)
- **Domains:** User experience, accessibility, workflow design, dashboard design, friction reduction
- **Key Frameworks:** Accessibility standards, user journey mapping, design system

### Health & Wellness
- **Primary:** Medical Officer
- **Domains:** Health guidance, wellness support, symptom review, escalation assessment
- **Key Frameworks:** Wellness coaching, health escalation, recovery support

### Research & Intelligence
- **Primary:** Research Officer (future)
- **Domains:** Research methodology, evidence gathering, competitive analysis, trend analysis
- **Key Frameworks:** Intelligence briefing, research methodology, source evaluation

### Knowledge & Documentation
- **Primary:** Knowledge Officer
- **Secondary:** Knowledge Architect (future)
- **Domains:** Documentation, information architecture, knowledge governance, institutional memory
- **Key Frameworks:** Knowledge governance, documentation lifecycle, information architecture

---

## Specialist Collaboration Patterns

### Sequential Workflow
**Chief of Staff → Specialist(s) → Captain TJR**

1. Chief of Staff receives request, routes to appropriate specialist
2. Specialist provides assessment, recommendation, or deliverable
3. If escalation needed: Chief of Staff routes to Captain TJR for decision
4. If advisory only: Captain TJR uses specialist input to make decision

### Parallel Specialist Collaboration
**Multiple specialists working on related missions:**

- Chief Engineer + Coder Agent + QA Test Officer (engineering work)
- Chief of Staff + Knowledge Officer + Specialists (governance decisions)
- UX Design Officer + Chief Engineer + Coder Agent (new features)

### Cross-Domain Escalation
**When specialist domain knowledge spans multiple specialists:**

- UX issue with architecture implications → UX Design Officer + Chief Engineer
- Governance decision with operational impact → Chief of Staff + Knowledge Officer + Operations Officer (future)
- Research findings with architecture implications → Research Officer (future) + Chief Engineer

---

## Specialist Maturity & Readiness

| Specialist | Status | Maturity | Operational | Governance | Runtime | Knowledge |
|---|---|---|---|---|---|---|
| Chief of Staff | Active | 3 | Yes | Complete | Active | Complete |
| Chief Engineer | Active | 3 | Yes | Complete | Active | Complete |
| Coder Agent | Active | 3 | Yes | Complete | Active | Complete |
| QA Test Officer | Active | 3 | Yes | Complete | Active | Complete |
| Knowledge Officer | Active | 3 | Yes | Complete | Active | Complete |
| UX Design Officer | Active | 3 | Yes | Complete | Active | Complete |
| Medical Officer | Active | 3 | Yes | Partial | Active | Complete |
| Research Officer | Future | 2 | No | Defined | Available | Complete |
| Operations Officer | Future | 2 | No | Defined | Available | Partial |
| UX Officer | Future | TBD | No | TBD | Available | TBD |
| Knowledge Architect | Future | TBD | No | TBD | Available | TBD |
| Product Designer | Future | TBD | No | TBD | Available | TBD |

**Maturity Levels:**
- **Level 1:** Concept (no documentation)
- **Level 2:** Defined (charter and knowledge pack defined, ready for commissioning)
- **Level 3:** Operational (full governance, operational prompts, runtime-ready)

---

## File Dependencies

**To activate a new specialist, these files must exist:**

1. ✅ **Runtime Charter** — `specialists/[core-crew or future-crew]/[Specialist-Name].md`
2. ✅ **Knowledge Pack** — `specialists/knowledge-packs/[Specialist-Name]-Knowledge.md`
3. ⭕ **Governance Folder** — `core/crew/[specialist-folder]/` (needed for operational readiness)
4. ⭕ **Role Definition** — `core/crew/[specialist-folder]/role-definition.txt`
5. ⭕ **Operational Prompt** — `core/crew/[specialist-folder]/operational-prompt.txt`
6. ✅ **Activation Plan** — `specialists/activation-plans/[Specialist-Name]-Activation.md`
7. ✅ **Registry Entry** — `core/crew/registry/specialist-registry.md`

**Legend:**
- ✅ = Available for all planned specialists (can be completed immediately)
- ⭕ = Requires governance framework build (deferred to activation project)

---

## Specialist Attribute Summary

### By Authority Level
| Authority Level | Specialists |
|---|---|
| **Full Authority** | Chief of Staff |
| **Advisory Authority** | Chief Engineer, QA Test Officer, Knowledge Officer, UX Design Officer, Medical Officer, Research Officer (future), Operations Officer (future) |
| **Implementation Authority** | Coder Agent |

### By Domain Ownership
| Domain | Owner(s) |
|---|---|
| **Missions** | Chief of Staff |
| **Governance** | Chief of Staff, Knowledge Officer |
| **Architecture** | Chief Engineer, Specialists (support) |
| **Implementation** | Coder Agent, Chief Engineer (advisory) |
| **Quality** | QA Test Officer |
| **UX/Design** | UX Design Officer, UX Officer (future), Product Designer (future) |
| **Knowledge** | Knowledge Officer, Knowledge Architect (future) |
| **Health** | Medical Officer |
| **Research** | Research Officer (future) |
| **Operations** | Operations Officer (future) |

### By Department
| Department | Specialists |
|---|---|
| **Operations** | Chief of Staff, Knowledge Officer, Operations Officer (future) |
| **Engineering** | Chief Engineer, Coder Agent, QA Test Officer |
| **Experience** | UX Design Officer, UX Officer (future), Product Designer (future) |
| **Health** | Medical Officer |
| **Intelligence** | Research Officer (future) |

### By Escalation Recipient
| Recipient | Escalation From |
|---|---|
| **Captain TJR** | Chief of Staff, Chief Engineer, Medical Officer, Research Officer (future) |
| **Chief of Staff** | Knowledge Officer, Operations Officer (future) |
| **Chief Engineer** | Coder Agent, QA Test Officer, UX Design Officer |

---

## Discovery Completeness Checklist

✅ All 7 active core crew specialists inventoried  
✅ All 5 future crew specialists documented  
✅ All governance folders mapped  
✅ All runtime charters located  
✅ All knowledge packs identified  
✅ All 50+ frameworks discovered  
✅ All activation plans found  
✅ All registry files cross-referenced  
✅ All metadata extracted and structured  
✅ All decision authorities documented  
✅ All domain ownership mapped  
✅ All escalation paths identified  
✅ All collaboration patterns identified  

