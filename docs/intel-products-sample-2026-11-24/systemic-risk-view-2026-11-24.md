# Cross-sector and systemic provider view, generated 2026-11-24

Source: sample export read 2026-11-24 via read-only SELECT (not the full corpus; see docs/INTEL-PRODUCTS-2026-11-24.md limitations). Window: 2026-08-26 to 2026-11-24. Offline, read-only, default OFF, not wired into any service. Taxonomy and tagger: PR #706 (`provider_involvement`), text only, own-feed tagging off.

Labels: [OBSERVED FACT] counted/read from stored rows | [PLAUSIBLE RELATIONSHIP] consistent with the data, mechanism not shown | [UNVERIFIED HYPOTHESIS] needs outside evidence. Coincident trends are never treated as causation; no organisation is asserted to depend on any provider without evidence.

## Evidence base

- [OBSERVED FACT] 523 items in window; tags: DIRECTLY_INVOLVED 135, MENTIONED 383, UNCERTAIN 5.
- [OBSERVED FACT] Items with a populated `organisation` field: 0 of 523.
- [OBSERVED FACT] AFFECTED tags: 0; SUPPLYING tags: 0.
- [OBSERVED FACT] AU critical-infrastructure cut (geography AU, sector in energy/transport/financial_services/technology, event type in technology_outage/third_party_disruption/energy_disruption/transport_disruption/cyber): 100 items; tags DIRECTLY_INVOLVED 57, MENTIONED 42, UNCERTAIN 2; AFFECTED 0, SUPPLYING 0.

## Shared-provider concentration

**INSUFFICIENT EVIDENCE. No concentration score is produced.** Required: at least 3 distinct organisations, each with item-level AFFECTED or SUPPLYING evidence naming the same provider, across at least 2 independent events, plus a public source for each organisation-specific link. Found: 0 AFFECTED and 0 SUPPLYING tags in the window, 0 items with an organisation value, and 0 AFFECTED/SUPPLYING tags among the 100 AU critical-infrastructure items.

Telstra and Optus recurrence in this corpus is repeated news about single-provider outages. It is not shared-provider concentration.

## Provider-involvement links across 2+ sectors or 3+ organisations (window 14 days)

Rule: the same provider is DIRECTLY_INVOLVED in distinct reports (collapsed by headline, event type not 'other') whose sector labels include at least 2 different sectors (cross_sector/general are not sectors), or that name at least 3 different organisations, all within 14 days. [PLAUSIBLE RELATIONSHIP] Sector labels are assigned by the platform classifier to each report. A span across sector labels shows where the provider is being reported, not that those sectors depend on it, and several reports can describe one event.

Organisation rule (3+ named organisations): 0 links, because `organisation` is populated on 0 items. Insufficient evidence for any organisation-based link.

### Link 1: openai, 2026-11-02 to 2026-11-13

- [OBSERVED FACT] Evidence span: 2026-11-02T18:35:29+00:00 to 2026-11-13T17:56:25+00:00 (3 distinct reports).
- [OBSERVED FACT] Sector labels: financial_services, technology; organisations named: none.
- [PLAUSIBLE RELATIONSHIP] Reported involvement in more than one sector label within the window; not a dependency claim.

| Event id | Published | Sector label | Geography | Source | Title | Evidence span (clause the tag rests on) |
|---|---|---|---|---|---|---|
| `a8075703-ed7e-4a29-b844-9451491bc803` | 2026-11-02 | financial_services | GLOBAL | Bloomberg | Anthropic IPO Explained: S-1 Filing, Nasdaq Listing and Key Risks | In late 2020, a group of senior OpenAI employees unhappy with what they saw as the compan... |
| `35d41ea7-7b91-45fe-8c32-c2ee06af4a2d` | 2026-11-10 | financial_services | GLOBAL | Bloomberg | Anthropic IPO Explained: Nasdaq Listing and Key Risks | In late 2020, a group of senior OpenAI employees unhappy with what they saw as the compan... |
| `23d05bc4-70ac-404b-9430-a6d15f60df2b` | 2026-11-13 | technology | GLOBAL | Inc. Magazine — Leadership | The Microsoft Outage Also Hit ChatGPT and Claude. But There’s an Easy Workaround | OpenAI and Anthropic reported disruptions to the connections that let ChatGPT and Claude... |

### Link 2: telstra, 2026-10-22 to 2026-11-13

- [OBSERVED FACT] Evidence span: 2026-10-22T22:46:09+00:00 to 2026-11-13T18:56:09+00:00 (10 distinct reports).
- [OBSERVED FACT] Sector labels: emergency_management, financial_services, technology; organisations named: none.
- [PLAUSIBLE RELATIONSHIP] Reported involvement in more than one sector label within the window; not a dependency claim.

| Event id | Published | Sector label | Geography | Source | Title | Evidence span (clause the tag rests on) |
|---|---|---|---|---|---|---|
| `6c60727f-7f16-48be-9105-3f2e0c9621ba` | 2026-10-22 | technology | AU | ARN - Australian IT Channel | Telstra enterprise experiences ordering and fulfilment issues | Telstra enterprise experiences ordering and fulfilment issues |
| `d7cd797e-c12a-4fed-81d8-faeef8d6fa9f` | 2026-10-31 | technology | AU | Google News - Telstra | Telstra's problems in Australia continue with Amazon Web Services outage - Mash... | Telstra's problems in Australia continue with Amazon Web Services outage - Mashable |
| `4df0bd3c-aa9a-4dac-952e-af4879395d1f` | 2026-11-04 | technology | AU | Google News - Telstra | What Does Telstra Group Limited (ASX:TLS), an S&P/ASX 50 Member, Make of Its Fu... | What Does Telstra Group Limited (ASX:TLS), an S&P/ASX 50 Member, Make of Its Further $1 B... |
| `09ac7ab3-5679-4a93-aa36-8bd95340801b` | 2026-11-04 | emergency_management | AU | Google News - Telstra | Telstra glitch bombards customers with mystery calls - The West Australian | Telstra glitch bombards customers with mystery calls - The West Australian |
| `6f8cbc2a-bf65-4919-8234-3de7193744f5` | 2026-11-04 | emergency_management | AU | Google News - Telstra | Has Telstra been hacked? Technical issue bombards customers with mystery calls... | Has Telstra been hacked? Technical issue bombards customers with mystery calls - The West... |
| `83c30141-48b4-4fec-b640-f9d12633365a` | 2026-11-04 | financial_services | AU | Google News - Telstra | Telstra Customers Flooded With Missed Call Notifications After MessageBank Faul... | Telstra Customers Flooded With Missed Call Notifications After MessageBank Fault - Tech B... |
| `2f7e6dac-9e82-43b8-a482-91882f2143b0` | 2026-11-05 | technology | AU | Google News - Telstra | UPDATE: Telstra admits glitch as Griffith customers hit by network problems - R... | UPDATE: Telstra admits glitch as Griffith customers hit by network problems - Region Rive... |
| `005e774d-ea0a-4935-9e5f-b002804a03c7` | 2026-11-07 | technology | AU | Google News - Telstra | Telstra users face 60-hour outage during Yornup upgrade - Manjimup Bridgetown T... | Telstra users face 60-hour outage during Yornup upgrade - Manjimup Bridgetown Times |
| `130ca8a1-a486-49cc-bded-a267f9a2306c` | 2026-11-12 | technology | AU | Google News - Telstra | Telstra links Stockton mobile outage to attempted copper cable theft - newy.com... | Telstra links Stockton mobile outage to attempted copper cable theft - newy.com.au |
| `1beab7d3-10de-4747-ad71-d7e9b43d2db2` | 2026-11-13 | technology | AU | Google News - Telstra | Telstra Outage -Barnaby Joyce Raises Question Of China Involvement - Sydney Tim... | Telstra Outage -Barnaby Joyce Raises Question Of China Involvement - Sydney Times |

### Link 3: openai, 2026-09-22 to 2026-10-06

- [OBSERVED FACT] Evidence span: 2026-09-22T01:44:17+00:00 to 2026-10-06T00:53:48+00:00 (18 distinct reports).
- [OBSERVED FACT] Sector labels: cyber_security, financial_services, transport; organisations named: none.
- [PLAUSIBLE RELATIONSHIP] Reported involvement in more than one sector label within the window; not a dependency claim.

| Event id | Published | Sector label | Geography | Source | Title | Evidence span (clause the tag rests on) |
|---|---|---|---|---|---|---|
| `1982d026-6eb8-4cf4-b09b-7d3a102794d5` | 2026-09-22 | financial_services | GLOBAL | BBC News | Canadian province sues OpenAI over Tumbler Ridge school shooting | British Columbia has accused the company of failing to report the shooter's troubling int... |
| `66d9673b-cb99-46d8-8753-12a331cdd4f6` | 2026-09-23 | cyber_security | AU | Guardian Australia | Anthony Albanese says OpenAI agent hacked Medicare and he expressed ‘extreme co... | Anthony Albanese says OpenAI agent hacked Medicare and he expressed ‘extreme concern’ to... |
| `75d57e4b-dcce-4f98-8dd1-2c62e28fbdcb` | 2026-09-23 | cyber_security | AU | Financial Times | OpenAI agent hacked an Australian health service website | OpenAI agent hacked an Australian health service website |
| `3de04cce-3565-4688-8d13-8aa795bd1fa6` | 2026-09-23 | cyber_security | AU | BBC News | OpenAI agent 'infiltrated' Australian government website, PM says | Albanese said he expressed "concern" to OpenAI founder Sam Altman, after authorities were... |
| `80d534a9-fd2f-4d95-9e18-375409ec6036` | 2026-09-24 | cyber_security | AU | ABC News | How OpenAI agents tried to thwart cybersecurity amid Medicare hack | How OpenAI agents tried to thwart cybersecurity amid Medicare hack |
| `2b146c43-c109-4601-9ce3-d6c4c4af3ec0` | 2026-09-24 | cyber_security | AU | Google News - Origin Energy | FACTBOX-OpenAI data breach latest in long list of hacks in Australia - devdisco... | FACTBOX-OpenAI data breach latest in long list of hacks in Australia - devdiscourse.com |
| `b55e0d7a-d970-4ff9-9ed5-fd6fa5e0ff3a` | 2026-09-24 | cyber_security | AU | Google News - Origin Energy | OpenAI data breach latest in long list of hacks in Australia - marketscreener.c... | OpenAI data breach latest in long list of hacks in Australia - marketscreener.com |
| `3ec22c2c-7ade-4d47-99ec-4959761eaedd` | 2026-09-24 | cyber_security | AU | ARN - Australian IT Channel | OpenAI govt breach puts fresh focus on ANAO AI warnings | OpenAI govt breach puts fresh focus on ANAO AI warnings |
| `055c8001-e28c-4f5e-b10e-04d7f690d418` | 2026-09-24 | cyber_security | AU | ABC News | Australia vows AI guardrails after unprecedented OpenAI breach | OpenAI's delayed reporting of an autonomous agent breaching a government website has stre... |
| `dc3b7206-5298-43ce-bcdb-f325b07993cd` | 2026-09-24 | cyber_security | AU | Financial Times | OpenAI breach of Australian government linked to wider AI hacking campaign | OpenAI breach of Australian government linked to wider AI hacking campaign |
| `266e79ef-823a-4e27-9f70-f550df813d37` | 2026-09-25 | cyber_security | AU | Guardian Australia | Rogue AI hacks government system in world first – podcast | OpenAI became aware of the hack in August, but only informed the government in September. |
| `10b2bdaa-40a3-49f6-a930-4c1bba57fce7` | 2026-09-25 | cyber_security | AU | ABC News | 'Ethical' hacker doubts Open AI will face charges over Medicare hack | As questions linger around whether OpenAI will face legal consequences for its Medicare h... |
| `376daff1-c151-4f74-91af-ca87606b2674` | 2026-09-26 | transport | AU | Guardian Australia | Australia news live: Marles said OpenAI CEO didn’t tell him about hack at meeti... | Australia news live: Marles said OpenAI CEO didn’t tell him about hack at meeting; flight... |
| `923fa69a-43c4-4e87-af3d-e6416229ddbf` | 2026-09-27 | cyber_security | AU | ABC News | OpenAI breach proves need for more data centres, major parties say | OpenAI breach proves need for more data centres, major parties say |
| `027a96bb-00ca-44c9-b971-e352c030acfe` | 2026-09-27 | cyber_security | AU | Guardian Australia | Australia is run on legacy systems that AI agents can easily exploit, former UN... | Federal cabinet will discuss the OpenAI breach on Monday as the AI giant pauses testing o... |
| `8a1f099c-a368-4af2-8728-aabed1ed0b0c` | 2026-09-28 | cyber_security | AU | ABC News | OpenAI's delayed warning drives tougher approach to rogue AI | Australia is looking to impose a dual notification requirement under tougher new standard... |
| `dcdc9f1c-307a-433a-b03a-cd60996af9e1` | 2026-09-29 | cyber_security | AU | ABC News | OpenAI apologises for Medicare breach, shelves next gen ChatGPT | OpenAI apologises for Medicare breach, shelves next gen ChatGPT |
| `f0ce864b-690b-494d-b942-8dec24a980e3` | 2026-10-06 | cyber_security | AU | Guardian Australia | OpenAI to reiterate apology to Australia over Medicare hack as inquiry told art... | OpenAI to reiterate apology to Australia over Medicare hack as inquiry told artists risk... |

## Limits

- Reported involvement, not dependency: every tag carries `dependency_proven = False`.
- The tagger is deterministic and conservative; PR #706 measured about 77% strict class precision and did not measure recall. Many involvements are filed as MENTIONED or UNCERTAIN and so never reach this view.
- Collapse by headline does not merge different headlines about one outage, so sector spans can be inflated.
- The export is a sample, with a heavy Telstra news share and no organisation values.
- [UNVERIFIED HYPOTHESIS] Whether any sector would be affected by a provider failure is not inferred.
