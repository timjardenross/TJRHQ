# Captain Profile

_Real Captain profile content exists at `knowledge/memory/captain_profile.txt`; this
file mirrors it at the path `platform-runtime/prompt_loader.py`'s
`load_memory_context()` expects, so the loader finds real content instead of degrading
to placeholder text. Treat `knowledge/memory/captain_profile.txt` as the source of
truth if the two ever diverge — this file is a faithful copy, not an independent
record, and should be re-synced from there rather than edited independently.
`prompt_loader.py` has zero live callers repo-wide as of 2026-09-15; see
`specialists/RUNTIME-STATUS.md`. Classification carried over from the source file:
"Captain & XO Use."_

Unlike the other five `memory/*.md` files this loader expects
(`Crew-Context.md`, `Active-Priorities.md`, `Decision-Register.md`,
`Active-Missions.md`, `Health-Summary.md`), which have no real equivalent anywhere
else in the repo and stay as honest "not yet populated" stubs, this file's content was
never missing — it existed at a different path/filename the loader doesn't know about.

---

## Identity

- Preferred name: TJR
- Location: Melbourne, Australia
- Professional identity: operational resilience and business continuity practitioner;
  15+ years across telecommunications and banking; experience spanning operational
  resilience, business continuity, crisis management, service delivery, risk and
  organisational resilience; practitioner/subject-matter-expert rather than
  traditional people leader or project manager; MBA qualified; progressing
  professional resilience credentials; building capability across AI, automation and
  agentic systems.
- Personal venture: **TJR Mind & Body** — human resilience, capacity management,
  burnout, chronic pain, neurodivergence, life transitions, holistic wellness
  coaching.
- Operating identity: systems thinker; capacity-first; evidence-informed; strong
  preference for practical implementation over theory; comfortable challenging
  established processes where they no longer serve their purpose; values autonomy,
  clarity, usefulness and continuous improvement.

## Core Objectives

**Current priorities:** build TJR HQ into a trusted personal intelligence and
execution system; reduce cognitive load and unnecessary manual administration;
improve sustainable management of personal capacity; create stronger boundaries
between work, recovery and personal life; continue career development in operational
resilience and adjacent customer/service leadership roles; develop TJR Mind & Body
into a credible independent practice; expand practical use of AI and automation across
professional and personal workflows.

**Career direction:** operational resilience leadership and specialist roles; business
continuity and crisis management; service delivery; customer success management;
B2B/B2C customer experience; human resilience and organisational capacity; AI-enabled
operational improvement.

**Decision principles:** protect sustainable capacity before maximising utilisation;
prefer systems that reduce ongoing cognitive effort; automate repetitive work where it
genuinely improves outcomes; maintain human judgement for consequential decisions;
seek root causes rather than repeatedly treating symptoms; favour simple, durable
systems over unnecessary complexity; design around real human behaviour rather than
idealised behaviour; preserve optionality where uncertainty is high.

## Health Profile

- Lives with chronic spinal pain and a history of multiple spinal procedures;
  experiences variable physical and cognitive capacity.
- Neurodivergent profile includes ADHD/autistic traits and associated sensory and
  executive-function considerations.
- Noise, overstimulation, uncertainty and sustained workload can materially affect
  available capacity. Sleep quality and physical pain can significantly influence
  daily functioning. Recovery needs vary rather than following a fixed daily pattern.
- **Capacity model** ("Capacity is dynamic, not fixed"): key signals are physical pain,
  energy, sleep, cognitive load, executive function, sensory stimulation, emotional
  regulation, social demand, and recovery requirement.
- **Preferred response to declining capacity:** recognise it early; reduce
  non-essential demand; prioritise the smallest useful next action; protect recovery
  time; avoid unnecessary context switching; use structure and external systems rather
  than relying on memory; escalate health concerns to appropriate professionals rather
  than attempting autonomous diagnosis.
- **Human resilience model stages:** Recognise, Regulate, Rebuild, Redesign.

This section is directly relevant to Medical Officer, Recovery Officer, Recovery
Coach, Wellness Advisor, and XO/capacity-gating logic — see
`registry/Division-Registry.md` for the Health/Medical-Wellness specialists that would
draw on it.

## Communication Preferences

**Default style:** direct, clear, practical, conversational, evidence-informed,
strategically forward-looking, constructively challenging when appropriate.

**Interaction preferences:** lead with the answer or recommended next action; avoid
unnecessary preamble; break complex work into bounded steps; keep immediate action
lists short; clearly distinguish facts, assumptions and recommendations; explain
reasoning when it materially improves the decision; challenge weak assumptions rather
than simply agreeing; prefer executive summaries followed by deeper detail when
required; maintain continuity with previous decisions and work; avoid repeatedly
asking for information already known to the system.

**ADHD-friendly mode:** minimise cognitive overhead; make the next action obvious;
prefer structured choices over open-ended questions; surface priorities rather than
large undifferentiated lists; preserve state so interrupted work can be resumed
easily; convert large objectives into manageable execution units.

**Tone:** preferred — calm, intelligent, human, candid, supportive without being
patronising. Avoid — excessive reassurance, corporate filler, artificial enthusiasm,
unnecessary jargon, overly long explanations when a short answer is sufficient.

## Starship Endeavour Vision

**Mission:** "Create a trusted personal intelligence, resilience and execution system
that helps TJR understand what matters, protect capacity, make better decisions and
turn intent into action."

**Concept:** Starship Endeavour is the operating metaphor for TJR HQ. TJR is the
Captain. The system acts as the XO and supporting ship systems: maintaining
situational awareness, surfacing relevant intelligence, coordinating specialised
capabilities and helping the Captain execute without removing human authority.

**Captain (TJR) authority:** mission, priorities, values, consequential decisions,
final judgement.

**XO role:** AI orchestration and executive support — maintain context, reduce
cognitive load, surface priorities, challenge assumptions, coordinate specialist
capabilities, identify emerging risks and opportunities, turn decisions into
executable next actions, maintain continuity across missions and workstreams.

**North star:** "TJR HQ should know enough about the Captain, the mission and the
current environment to surface the right thing at the right time — without requiring
TJR to continuously manage the system."

See `knowledge/memory/captain_profile.txt` for the complete source, including the full
`operating_principles`, `desired_capabilities`, and `success_state` lists, which are
condensed here for length.

## Related Files

- `knowledge/memory/captain_profile.txt` — source of truth for this file
- `memory/Health-Summary.md` — separate, currently-unpopulated stub for day-to-day
  health tracking (distinct from the static health profile above)
- `memory/Active-Priorities.md`, `memory/Active-Missions.md`,
  `memory/Decision-Register.md`, `memory/Crew-Context.md` — remain genuinely
  unpopulated; no real equivalent exists elsewhere in the repo for these
