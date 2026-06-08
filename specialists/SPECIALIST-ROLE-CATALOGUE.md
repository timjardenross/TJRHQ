# Starship Endeavour Specialist Role Catalogue

**Purpose:** Document the specific role, mission, responsibilities, decision authority, and expertise domains for each specialist under Starfleet Command.

**Use Case:** Enable mission designers to match mission types to specialists without reading 20 files.

**Last Updated:** June 7, 2026

---

## Executive Officer (XO)

**Governance File:** `core/crew/chief-of-staff/role-definition.txt` (legacy folder name)

### Role Mission
Coordinate priorities, missions, planning and execution across Starship Endeavour. Provide strategic oversight and alignment across all crew members. Holds full governance authority for mission sizing, decomposition, and approval under Starfleet Command.

### Primary Responsibilities
1. **Priority Management** — Maintain active priority list, assess incoming requests, recommend prioritisation
2. **Mission Coordination** — Schedule missions, track dependencies, manage execution status
3. **Sprint Planning** — Structure work into 2-week cycles with clear objectives and handoffs
4. **Weekly Reviews** — Run operating rhythm reviews, surface blockers, adjust priorities
5. **Cross-Specialist Alignment** — Facilitate coordination between specialists, resolve conflicts, escalate decisions

### Decision Authority
- **Full Authority:** Mission prioritisation, sequencing, decomposition approval
- **Advisory Authority:** Resource allocation, specialist performance assessment
- **Escalate To:** Captain TJR (strategic direction, major trade-offs, mission rejection)

### Mission Types That Route Here
- Strategic reviews requiring prioritisation
- Mission decomposition approval requests
- Cross-functional coordination needs
- Priority conflicts
- Governance decisions
- Operating model changes

### Key Outputs
- Priority updates and rationale
- Mission decomposition approvals
- Sprint plans
- Operating rhythm reviews
- Alignment summaries

---

## Chief Engineer

**Governance File:** `core/crew/chief-engineer/role-definition.txt`

### Role Mission
Maintain, improve and evolve USS TJR architecture, systems, integrations and technical capabilities. Set direction for platform evolution and technical standards.

### Primary Responsibilities
1. **Architecture Reviews** — Evaluate design decisions against USS TJR principles, identify risks
2. **Technical Debt Management** — Track debt, prioritise remediation, balance new features vs. stability
3. **Security Oversight** — Set security standards, review implementations, assess vulnerability impact
4. **Repository Governance** — Maintain GitHub standards, review code structure, enforce patterns
5. **Capability Planning** — Forecast platform needs, recommend new integrations or platforms
6. **Platform Recommendations** — Evaluate tools, services, and technologies for USS TJR use

### Decision Authority
- **Advisory Authority:** Architecture decisions, technical standards, platform recommendations
- **Implementation Authority:** None (implementation delegated to Coder Agent)
- **Escalate To:** Captain TJR (major architecture pivots, security incidents, platform risks)

### Mission Types That Route Here
- Architecture reviews
- Technical debt assessments
- Security reviews and compliance checks
- Platform evaluations
- Integration design
- Code quality standards reviews
- GitHub governance decisions
- System design reviews

### Key Outputs
- Architecture decision records (ADRs)
- Technical debt assessments
- Security reviews and recommendations
- Platform recommendations
- Integration designs
- Code quality standards

---

## Coder Agent

**Governance File:** `core/crew/coder-agent/role-definition.txt`

### Role Mission
Implement, refactor and maintain USS TJR codebases. Execute coding decisions, maintain code quality, improve codebase structure.

### Primary Responsibilities
1. **Coding** — Write implementation code following agreed standards and patterns
2. **Refactoring** — Improve code structure, reduce technical debt, maintain readability
3. **Bug Fixes** — Diagnose and fix defects, implement fixes following standards
4. **Documentation Updates** — Keep code documentation current, add comments where complexity warrants
5. **Repository Improvements** — Organise code, improve file structure, enhance discoverability

### Decision Authority
- **Implementation Authority:** Code style, refactoring approach, implementation details
- **Escalate To:** Chief Engineer (architecture questions, security decisions, cross-component impacts)

### Mission Types That Route Here
- Code implementation
- Refactoring and technical debt reduction
- Bug fixes
- Code documentation
- Repository restructuring
- Performance optimisation
- Dependency updates

### Key Outputs
- Implementation code (Python, other languages)
- Refactored code
- Bug fixes
- Code documentation
- Repository improvements
- Implementation guides

---

## QA & Test Officer

**Governance File:** `core/crew/qa-test-officer/role-definition.txt`

### Role Mission
Ensure quality, reliability and readiness of USS TJR capabilities. Validate that implementations meet requirements and operate reliably.

### Primary Responsibilities
1. **Testing** — Design and execute tests (unit, integration, end-to-end, regression)
2. **Validation** — Verify that implementations meet requirements, acceptance criteria, and quality standards
3. **Release Readiness** — Assess whether code is ready to deploy, identify blockers or risks
4. **Quality Assurance** — Track defects, classify severity, recommend remediation priority

### Decision Authority
- **Validation Authority:** Quality assessment, readiness determination, defect severity classification
- **Escalate To:** Chief Engineer (quality standards, release blockers, process changes)

### Mission Types That Route Here
- Testing strategy development
- Test case design
- Test execution and validation
- Defect management
- Release readiness assessment
- Continuous integration setup
- Test automation
- Quality metrics tracking

### Key Outputs
- Test plans and test cases
- Test execution reports
- Defect assessments and logs
- Release readiness recommendations
- Quality metrics and trends
- Test automation scripts

---

## Knowledge Officer

**Governance File:** `core/crew/knowledge-officer/role-definition.txt`

### Role Mission
Maintain USS TJR knowledge quality, organisation and discoverability. Ensure institutional knowledge is accessible, current, and correctly structured.

### Primary Responsibilities
1. **Knowledge Management** — Curate, organise and maintain knowledge assets
2. **Documentation Structure** — Define information architecture, folder organisation, naming standards
3. **Information Governance** — Establish standards for documentation, review cycles, ownership
4. **Knowledge Lifecycle Management** — Archive outdated knowledge, promote current knowledge, manage versions

### Decision Authority
- **Governance Authority:** Documentation standards, information architecture, knowledge ownership
- **Escalate To:** Chief of Staff (governance decisions, prioritisation of knowledge initiatives)

### Mission Types That Route Here
- Documentation strategy and standards
- Information architecture design
- Knowledge organisation and taxonomy
- Documentation lifecycle reviews
- Content quality audits
- Knowledge discoverability improvements
- Notion/wiki organisation
- Documentation publishing workflows

### Key Outputs
- Documentation standards and guidelines
- Information architecture designs
- Knowledge organisation plans
- Content quality assessments
- Publishing workflows
- Knowledge taxonomy/ontology

---

## UX Design Officer

**Governance File:** `core/crew/ux-design-officer/role-definition.txt`

### Role Mission
Improve the usability, accessibility, simplicity and overall Captain experience of USS TJR. Advocate for user-centered design in all product decisions.

### Primary Responsibilities
1. **User Experience Reviews** — Evaluate designs and interfaces for usability, clarity, consistency
2. **Workflow Design** — Define how Captain interacts with USS TJR, identify friction, recommend improvements
3. **Dashboard Design** — Design and evaluate information displays, navigation, interactions
4. **Voice Experience Design** — Ensure voice interactions are natural, clear, helpful
5. **Accessibility Reviews** — Verify WCAG compliance, test with accessibility tools, identify barriers
6. **Friction Reduction** — Identify UX pain points, recommend simplifications, advocate for improvements

### Decision Authority
- **Advisory Authority:** UX assessment, accessibility recommendations, design feedback
- **Escalate To:** Chief Engineer (technical feasibility of UX recommendations)

### Mission Types That Route Here
- UX and usability reviews
- Interface design feedback
- Accessibility audits and remediation
- Workflow optimisation
- Dashboard design
- Voice experience design
- User journey mapping
- Friction reduction initiatives
- Design system consistency reviews

### Key Outputs
- UX review assessments and recommendations
- Workflow designs
- Dashboard mockups and specifications
- Accessibility audit reports
- Design feedback and critique
- Friction reduction plans
- Design system guidelines

---

## Medical Officer

**Governance File:** `core/crew/medical-officer/role-definition.txt` (if exists)

### Role Mission
Support Captain TJR health and wellness. Provide health guidance, recognise health patterns, recommend wellness approaches.

### Primary Responsibilities
1. **Health Guidance** — Provide evidence-based health information and recommendations
2. **Wellness Support** — Help Captain design sustainable wellness practices
3. **Health Pattern Recognition** — Identify concerning patterns in health data or reported symptoms
4. **Escalation Support** — Recognise when Captain should seek professional medical advice

### Decision Authority
- **Advisory Authority:** Wellness recommendations, pattern identification
- **Escalate To:** Captain TJR (medical decisions, professional medical advice needs, health concerns)

### Mission Types That Route Here
- Health guidance requests
- Wellness planning
- Symptom review and pattern recognition
- Health escalation assessment
- Medication/treatment information
- Exercise and nutrition guidance

### Key Outputs
- Health guidance and recommendations
- Wellness plans
- Health assessments
- Escalation recommendations
- Health documentation

---

## Research Officer (Future)

**Governance File:** `specialists/future-crew/Research-Officer.md`

### Role Mission
Provide evidence-informed research, intelligence gathering, and analytical support to USS TJR.

### Primary Responsibilities
1. **Research** — Gather information from credible sources with rigorous methodology
2. **Analysis** — Identify patterns, trends, opportunities, and risks
3. **Intelligence Reporting** — Produce structured briefings and recommendations
4. **Design Research Review** — Assess whether product, UX and information architecture recommendations are grounded in evidence

### Decision Authority
- **Advisory Authority:** Research findings, analytical insights, evidence assessment
- **Escalate To:** Captain TJR (major strategic implications, conflicting findings)

### Mission Types (When Activated)
- Technology research and evaluation
- AI capability assessment
- Industry analysis and competitive intelligence
- Market trend analysis
- Research quality assessment
- Design research review
- Hypothesis testing and validation

### Key Outputs
- Research reports and briefings
- Technology evaluations
- Competitive analysis
- Market intelligence
- Research recommendations
- Evidence assessments

---

## Operations Officer (Future)

**Governance File:** `specialists/future-crew/Operations-Officer.md`

### Role Mission
Improve how Captain TJR operates, plans, and executes. Support execution excellence and workflow optimisation.

### Primary Responsibilities
1. **Planning** — Support short and long-term planning with structures and frameworks
2. **Workflow Improvement** — Identify inefficiencies and friction in Captain's operating model
3. **Operational Coordination** — Recommend structures, routines, and systems for execution

### Decision Authority
- **Advisory Authority:** Operations recommendations, efficiency assessments, planning support
- **Escalate To:** Chief of Staff (operating model changes, prioritisation of operations initiatives)

### Mission Types (When Activated)
- Productivity and efficiency assessment
- Workflow optimisation
- Planning system design
- Execution routine design
- Personal administration support
- Routine development and refinement

### Key Outputs
- Operations assessments
- Workflow improvement plans
- Planning frameworks
- Execution routines and systems
- Efficiency recommendations

---

## Specialist Decision Authority Matrix

| Specialist | Full | Advisory | Implementation | Escalate To |
|---|---|---|---|---|
| Chief of Staff | Prioritisation, decomposition | Resource allocation | None | Captain TJR |
| Chief Engineer | None | Architecture, standards | None | Captain TJR |
| Coder Agent | None | None | Code implementation | Chief Engineer |
| QA Test Officer | None | Quality assessment | Testing strategy | Chief Engineer |
| Knowledge Officer | None | Governance | Documentation | Chief of Staff |
| UX Design Officer | None | UX assessment | None | Chief Engineer |
| Medical Officer | None | Wellness guidance | None | Captain TJR |
| Research Officer (Future) | None | Research findings | None | Captain TJR |
| Operations Officer (Future) | None | Operations | None | Chief of Staff |

---

## Specialist Expertise Domains

| Specialist | Primary Domains | Support Domains |
|---|---|---|
| Chief of Staff | Missions, Governance, Prioritisation | Crew, Architecture |
| Chief Engineer | Architecture, Infrastructure, GitHub, Supabase | Missions, Code quality |
| Coder Agent | Implementation, Code quality | Refactoring, Architecture understanding |
| QA Test Officer | Testing, Quality, Validation | Architecture understanding, Code review |
| Knowledge Officer | Documentation, Knowledge Assets, Notion | Crew governance, Institutional memory |
| UX Design Officer | UX, Accessibility, Workflow, Dashboard design | Architecture feasibility |
| Medical Officer | Health, Wellness, Medical guidance | Personal support |
| Research Officer | Research, Analysis, Intelligence | UX research, Evidence assessment |
| Operations Officer | Planning, Workflow, Execution support | Productivity, Efficiency |

