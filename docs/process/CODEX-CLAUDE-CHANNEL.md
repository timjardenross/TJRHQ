# Codex and Claude review channel

A standing pull request used as a message thread between the two engineering agents (Claude implements, Codex reviews independently) and the product owner. The thread is the PR's comments. This file is the protocol. **This PR is never merged for its content; it stays open as the channel, or is closed when the owner retires it.**

## Roles

- **Claude** builds changes on `claude/*` branches and opens draft pull requests. Claude never reviews or approves its own work.
- **Codex** performs the independent G7 review of an exact commit. Codex does not edit, push to, rebase or merge Claude's branches.
- **Product owner** decides all merges. Neither agent merges without the owner's explicit instruction.

## How a message is addressed

Start a comment with one of these headers, so the other side (and the owner) can scan the thread.

| Header | From | Meaning |
|---|---|---|
| `CLAUDE → CODEX: REVIEW REQUEST` | Claude | Please review an exact commit. |
| `CODEX → CLAUDE: VERDICT` | Codex | Result for an exact commit. |
| `CLAUDE → CODEX: REMEDIATION` | Claude | Fix pushed for your findings; please re-verify. |
| `CODEX → CLAUDE: QUESTION` / `CLAUDE → CODEX: QUESTION` | either | A question that blocks work. |
| `ACK` | either | Message read, no action needed. |
| `OWNER:` | product owner | A decision or instruction for either agent. |

## Review request (Claude posts)

```
CLAUDE → CODEX: REVIEW REQUEST
- Repository / PR: <owner/repo>#<number>
- Reviewed SHA (full 40 characters): <sha>
- Base SHA: <sha>
- Scope: <files or behaviour>
- Asks: <what to check>
- Evidence so far (labelled): <command, result, label>
- Not verified: <what was not run>
```

Post the same request on the pull request being reviewed as well, so that PR carries its own record. This thread lists it so it is not lost.

## Verdict (Codex posts)

```
CODEX → CLAUDE: VERDICT
- Reviewed SHA: <full sha> (confirm it is still the head, before and after reviewing)
- Verdict: PASS | PASS WITH CONDITIONS | HOLD | NOT REVIEWABLE
- Findings: <ID, severity P1/P2/P3 or S1-S4, file:line, behaviour, impact, reproduction, recommended fix>
- Validation: <what was run; what was not>
- Evidence labels: SOURCE VERIFIED / EXECUTION VERIFIED / NATIVE VERIFIED / NOT VERIFIED
```

A verdict applies only to the SHA it names. If the head moves, the delta needs a new request.

## Rules both sides keep

1. **Exact SHAs, always.** No "latest".
2. **Evidence labels.** No claim stronger than its evidence. Quote the other agent's evidence as "reported by …" until reproduced.
3. **Findings are closed only by Codex re-verification** at the fix SHA. A commit alone never closes a finding.
4. **Do not soften or dispute a finding in the code.** Reply in the thread; the owner decides disagreements.
5. **No secrets, tokens, personal data or private-repository details in this thread.** This repository is public. Private-repository work is coordinated on its own pull requests.
6. **Never merge from this thread.** Only the owner says "merge".
7. **Update the live queue** (pinned first comment) when a request is opened or closed.

## Where reviews happen

- **TJRHQ (public):** on each pull request, with a pointer here.
- **TJR-Life-iOS (private):** on that repository's own pull requests; the private repository's own rules apply and nothing from it is copied here.
