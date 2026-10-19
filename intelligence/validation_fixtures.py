"""Verbatim snapshots of real `intelligence_events` rows for the Operational
Intelligence Validation Suite (intelligence/validation_suite.py).

Why this file exists (2026-10-20): the suite used to look its "real" cases up
live in `intelligence_events` by title. A 90-day retention prune (DB-size
plan, 2026-10-11) deleted the rows behind four cases (Fortinet credential
exposure, Splunk/Oracle CVEs, Copilot availability, nbn junk) and the suite
fell from 8/8 to 4/8 with no pipeline fault. Any live-row lookup ages out the
same way, so these cases now replay a frozen copy of the real text through
classify()/rank() instead, exactly like the BOM and AWS synthetic cases.

Every entry is the unedited raw_title / raw_summary / canonical_url /
published_at of a row that existed in `intelligence_events` on 2026-10-20.
Nothing here is written or reworded by hand. Source metadata (priority,
weight, category) is not stored on event rows, so the suite supplies fixed
harness values for it; classification here is driven by the text.
"""

from __future__ import annotations

REAL_ROW_SNAPSHOTS: dict[str, dict[str, str | None]] = {'slack_outage': {'raw_title': 'Incident: Trouble with Slack - General Slack functionality issues',
                  'raw_summary': 'This issue is now resolved for all users.Current status and '
                                 'recent actions taken: We deployed a series of configuration '
                                 'adjustments and infrastructure fixes to restore services. '
                                 'Messaging, Workflows, Apps, and Connections were progressively '
                                 'restored over the last several hours. Some users continued to '
                                 'experience permissions-related issues, including inability to '
                                 'manage channels and Canvas edits not saving, as a result of '
                                 'residual stale cache data. Cache deployment activities completed '
                                 'at 14:13 UTC on May 28, 2026, fully resolving the '
                                 'issue.&nbsp;Scope: This issue affected Slack users '
                                 'globally.Previous impact to end users: Slack users experienced '
                                 'difficulties accessing Slack features, including Messaging, '
                                 'Workflows, Apps, Integrations, APIs, Canvas, and Connections, '
                                 'beginning at 22:21 UTC on May 27, 2026. Following an '
                                 'infrastructure change, a cascading scheduling failure caused '
                                 'widespread service impact across all regions and clients. Slack '
                                 'services largely returned to normal operationa',
                  'canonical_url': 'https://slack-status.com/2026-05/46d9d5d41fbedd9f',
                  'published_at': '2026-05-27T13:00:58+00:00'},
 'github_copilot_incident': {'raw_title': 'GitHub Status: Incident with Copilot AI Model Providers '
                                          '(resolved)',
                             'raw_summary': '[Impact: critical] Affected: Copilot AI Model '
                                            'Providers. This incident has been resolved. Thank you '
                                            'for your patience and understanding as we addressed '
                                            'this issue. A detailed root cause analysis will be '
                                            'shared as soon as it is available.',
                             'canonical_url': 'https://www.githubstatus.com/incidents/tx9qn4khd664',
                             'published_at': '2026-08-27T10:04:52.529+00:00'},
 'fortinet_fortimail_cve': {'raw_title': 'CVE-2026-104286: Fortinet FortiMail Path Traversal '
                                         'Vulnerability',
                            'raw_summary': 'Fortinet FortiMail contains a path traversal and an '
                                           'improper neutralization of NULL byte or NULL character '
                                           'vulnerability that may allow an unauthenticated '
                                           'attacker to write arbitrary files on the underlying '
                                           'system via crafted HTTP or HTTPS requests.',
                            'canonical_url': 'https://nvd.nist.gov/vuln/detail/CVE-2026-104286',
                            'published_at': '2026-10-01T00:00:00+00:00'},
 'nvd_cve_a': {'raw_title': 'CVE-2026-108785',
               'raw_summary': 'A flaw has been found in macrozheng mall up to 1.0.3. This issue '
                              'affects the function JwtTokenUtil.refreshHeadToken of the file '
                              '/admin/refreshToken of the component JwtAuthenticationTokenFilter. '
                              'This manipulation of the argument token causes session expiration. '
                              'The attack may be initiated remotely. The exploit has been '
                              'published and may be used. Patch name: '
                              '9bfc2fd2c4aaa4ac519e9152e65d673a5380de1a. To fix this issue, it is '
                              'recommended to deploy a patch.',
               'canonical_url': 'https://nvd.nist.gov/vuln/detail/CVE-2026-108785',
               'published_at': '2026-10-12T02:16:56.573+00:00'},
 'nvd_cve_b': {'raw_title': 'CVE-2026-108784',
               'raw_summary': 'A vulnerability was detected in macrozheng mall up to 1.0.3. This '
                              'vulnerability affects the function AlipayServiceImpl.pay of the '
                              'file com/macro/mall/portal/service/impl/AlipayServiceImpl.java of '
                              'the component Payment Endpoint. The manipulation of the argument '
                              'total_amount results in business logic errors. The attack can be '
                              'launched remotely. The exploit is now public and may be used. The '
                              'patch is identified as dcaa93b3150352e5044708d7211b5bed0af4509f. A '
                              'patch should be applied to remediate this issue.',
               'canonical_url': 'https://nvd.nist.gov/vuln/detail/CVE-2026-108784',
               'published_at': '2026-10-12T02:16:56.39+00:00'}}
