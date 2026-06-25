---
turn: 0062
from: CC
to: CEO
type: PROPOSAL
ref: governance-tiered-merge-autonomy
status: OPEN
date: 2026-06-25
---

# PROPOSAL — Tiered, time-gated merge autonomy (amends G1)

## Why now
- WP-01 CI gate is merged (turn 0060); `enable-standard-merge.sh` is the planned next infra step.
- Operational reality today: base `rebuild/auto-bioinfo-core` has **no branch protection**; merges happen via a broad token authenticated as the CEO account. PRs #1–#6 all merged this way. The CEO is **not** in practice an interactive gate, and `enable-standard-merge.sh` sets `required_approving_review_count: 0` (CI-green only) — so neither the current nor the planned mode requires a human tap.
- This is (a) looser than ideal on security — any holder of the token can merge into base — and (b) has no explicit agreed policy for *which* changes, if any, must pause for a human. This proposal fixes both.

## Proposed amendment to G1
Replace the single "CC cannot self-merge / merge = CEO" rule with a **risk-tiered** policy. CC still never decides its *own* merge unilaterally; merge authority is delegated by this ratified policy to (CI + independent review), with a human retained only for the RED tier.

**GREEN** — docs (`*.md`, `docs/**`), CI/workflow config (`.github/**`, `ci/**`), formatting-only diffs.
→ Auto-merge once dual-AI review (CC implements, Codex reviews) passes and CI is green. Any hour. No human.

**YELLOW** — ordinary product code / tests / package metadata not in RED.
→ Daytime (08:00–24:00 local): auto-merge on dual-AI + CI green; CEO gets a plain-language notice and may veto/revert (non-blocking).
→ Overnight (00:00–08:00 local): a **third, independent, adversarial AI reviewer** — distinct role/prompt from the CC implementer and from Codex, instructed to default to "hold" when uncertain — must also approve before auto-merge. This compensates for the absent human.

**RED** — always pauses for explicit human authorization, **any hour**, never AI-only:
- secrets / tokens / credentials
- real patient / genomic / PII data, or code that reads it
- money / billing / paid external services
- dependency / supply-chain changes (new or bumped third-party packages, lockfile changes), SBOM
- Docker / infrastructure / deploy
- branch-protection or security rulesets
- destructive or irreversible ops (history rewrite, force-push, data / branch deletion)

For RED, the human approval is presented as a **plain-language brief** (what it does, what it touches, why it is RED, reviewer consensus) so a non-technical CEO authorizes informedly — the tap is *authorization / accountability*, not code review.

## Guardrails
- The 3rd overnight reviewer must be **independent** of the implementer (separation of duties); never the same agent instance that wrote the diff.
- Tier classification is itself reviewed: if any reviewer believes a PR is mis-tiered (e.g. a "YELLOW" that actually touches a RED path), it escalates to the stricter tier.
- Nothing here lets CC merge on its sole judgment; GREEN/YELLOW merges require CI + ≥2 (day) / ≥3 (night) independent approvals.
- `enable-standard-merge.sh` (branch protection + required CI + auto-merge) is the enabling mechanism and runs **after** ratification; the broad token is then narrowed per OPS-00.

## Sequencing after ratification
1. Run `enable-standard-merge.sh` → branch protection on base, required CI, repo auto-merge on.
2. Implement the tier classifier + RED hold + overnight 3rd-reviewer in `~/cc-auto`.
3. Narrow Codex's broad token to a repo-scoped fine-grained PAT / GitHub App (OPS-00).

## Governance
This **amends constitution G1** and requires **CEO ratification** (with Codex concurrence). It is a PROPOSAL only — until ratified, the current process is unchanged. It does **not** block the active WP-01d work order (turn 0061).

## 给 CEO 的大白话(请你拍板)
现在情况:合并其实一直是自动的,不靠你点 —— 今晚 6 个 PR 都自动合了。我提议把"要不要叫人"按风险分三档:
- 🟢 **绿**(文档/配置):自动合,永不找你。
- 🟡 **黄**(普通代码):白天自动合 + 给你发条大白话通知(想拦可拦);**半夜多叫一个 AI 把关**再合。
- 🔴 **红**(密钥/真实数据/钱/依赖/Docker/分支规则/删除):**任何时候都停下等你点一下** —— 给你一句人话说清"为什么找你",你点的是"同意担责",不是看代码。

这样:**白天黑夜全自动跑,只有真正危险的稀有操作才叫你**,同时把现在"没保护、宽 token 随便合"的安全洞一起堵上。

请回:**APPROVE(同意)/ MODIFY(改哪档)/ REJECT(不要)**,并确认 🔴 红档清单要不要加东西。
