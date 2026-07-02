# Claude Science / AI for Science 资助申请（润色终稿）

- 申请入口:https://docs.google.com/forms/d/e/1FAIpQLSfwDGfVg2lHJ0cc0oF_ilEnjvr_r4_paYi7VLlr5cLNXASdvA/viewform
- 截止:2026-07-15 | 结果:2026-07-31 | 使用期:2026-09-01 → 12-01
- 用法:每段先给【英文,直接贴表单】,再给【中文,给你看懂】。`【★待你填】` = 只有你知道的信息。

---

## 0. 只有你能填的三样

- `【★待你填】` 机构:挂靠的**大学 / 非营利研究机构**名称。
- `【★待你填】` 团队成员姓名、职称、单位邮箱。
- `【★待你填】` 团队背景一句话(谁懂生信 / 谁懂 AI 工程)。

---

## 1. Project Title(项目名称)

**英文(贴表单):**
> Auditable Auto-Bioinformatics: a guardrailed closed loop that turns a natural-language research question into reproducible, claim-bounded computational evidence.

**中文:** 可审计的自动生信——把一句自然语言科研问题,变成可复现、结论有边界的计算证据。

---

## 2. Project Summary(项目简介 · 最重要)

**英文(贴表单):**
> We are building an auto-bioinformatics system that turns a plain-language research question — e.g. *"Which genes are differentially expressed in tissue X between conditions A and B?"* — into a fully auditable pipeline: question normalization, sub-question decomposition, evidence planning, dataset discovery with a feasibility gate, dataset locking, method selection, workflow compilation, execution, four-layer quality control (execution / data / statistics / biology), evidence extraction, cross-result synthesis, an audit of every conclusion against the original question, and finally a report plus a byte-for-byte reproducible bundle.
>
> Our success criterion is not that "the AI produced an answer," but that every step is recorded, every result traces to its data, method, parameters and run log, every conclusion is evidence-backed with no over-claiming, and any third party can re-run the exported bundle to bit-identical results. Crucially, when data is insufficient, a method inapplicable, or a result unstable, the system halts in an explicit, honest terminal state rather than forcing an answer.
>
> A deterministic, fully offline end-to-end loop is already built and tested — an immutable event-sourced state machine, four-layer QC gates, a real numpy-based differential-expression method, claim-ceiling guardrails, hard mock-data isolation, and reproduction bundles with SHA-256 lineage. The credits we request fund the next stage: replacing the offline deterministic planner with Claude as the reasoning layer (question parsing, evidence planning, method adaptation, synthesis) while keeping every fact, retrieval, statistic and check in tools, and connecting our reserved production ports to run on genuine public datasets.

**中文:** 完整讲系统在干嘛,并强调三件评审最爱看的:①每步可追溯 ②结论不越级 ③数据不够诚实停下。末段说明"钱花在哪":把离线规划器换成 Claude 当推理大脑,事实和执行仍归工具,接真实公开数据集。

---

## 3. Scientific Merit & Impact(科学价值与影响)

**英文(贴表单):**
> Most "AI for science" tooling is optimized to produce plausible answers — and the reproducibility and over-claiming crises in computational biology stem from exactly that. Our contribution is an architecture in which scientific validity is enforced structurally rather than left to the model's discretion:
> - **Monotonic evidence chain** — nothing becomes formal evidence without passing QC; the path QC → EvidenceItem → Claim → original-question audit has no shortcut.
> - **Claim ceiling** — an RNA differential-expression result is capped at *association* and never auto-escalated to protein, secretion, or causation; escalation is blocked at both claim synthesis and audit.
> - **Conservative failure** — insufficient data or an inapplicable method yields a legal terminal state (INSUFFICIENT_DATA / METHOD_NOT_APPLICABLE), never a fabricated result.
> - **No fabrication** — no invented accessions; verified datasets may not originate from mock or placeholder sources; an offline clean re-run of the bundle must be bitwise-identical.
>
> The impact is to make routine but error-prone analyses — starting with bulk RNA-seq differential expression — reproducible and honestly bounded *by default*, and to offer a reusable pattern for trustworthy autonomous science that generalizes well beyond our first method.

**中文:** 讲清与别的"AI 做科研"的根本差别:别人拼答得像模像样,我们拼可信、可复现、不吹牛,且靠架构强制。四条红线抄自你的设计红线。影响力落点:让最常见也最易错的分析默认就可复现、结论有边界。

---

## 4. How Claude Science Will Be Used(技术可行性 · 钱怎么花)

**英文(贴表单):**
> Our system is hexagonal (ports & adapters): the domain core — state machine, evidence gating, reproduction — is model-agnostic, and the LLM sits strictly outside it as a reasoning port. Because of this, adopting Claude Science's curated life-sciences skills and 60+ database connectors is a drop-in replacement for our current offline adapter, with no change to the domain core. Credits fund the reasoning and orchestration layer:
> 1. **Question resolution & decomposition** — Claude parses the natural-language question into a schema-bound research spec and sub-questions.
> 2. **Evidence & method planning** — Claude proposes the required data, literature and registered methods, subject to a data-feasibility gate (data decides what is possible).
> 3. **Cross-result synthesis** — Claude synthesizes QC-passed EvidenceItems into Claims under the claim-ceiling guardrail.
> 4. **Reviewer pass** — a Claude reviewer agent cross-checks citations and calculations, mirroring Claude Science's built-in reviewer.
>
> Every dataset ID, file existence, statistic, version and checksum stays tool-computed and is never asserted by the model. All usage is API-driven autonomous runs on standard public models — a direct fit for the credits' API-only terms.

**中文:** 给技术评审看"可行、即插即用"。核心卖点:LLM 早就放在可替换的端口后面,接 Claude Science 不用重写。列 Claude 负责的 4 件推理活,并强调事实和数字永远由工具算——正好对上 API-only、标准模型的要求。

---

## 5. Team & Institution(团队与机构)

**英文(贴表单):**
> `【★待你填】` Institution / non-profit affiliation.
> `【★待你填】` Team members, roles and short bios — who brings the computational-biology domain expertise, and who brings the AI-systems and software-engineering experience.
>
> The system already exists as a tested, version-controlled codebase — hexagonal architecture, an event-sourced core, 43 offline-deterministic tests, and CI — demonstrating our ability to ship rigorous, reproducible scientific software rather than a prototype.

**中文:** 机构与成员只有你能填。末句我替你把"已有带测试、带 CI、架构干净的真实代码库"写进去——证明团队靠谱最硬的证据。

---

## 6. Requested Credits & Usage Plan(申请额度与计划)

**英文(贴表单):**
> We request up to $30,000 in Claude Science credits over the September 1 – December 1, 2026 period:
> - **Phase A (Sept)** — wire Claude behind the existing reasoning port; validate the end-to-end loop on 2–3 public bulk RNA-seq datasets.
> - **Phase B (Oct)** — add Claude Science connectors for real dataset discovery and literature evidence; enable the reviewer agent.
> - **Phase C (Nov)** — scale to multiple concurrent autonomous runs; report reproducibility (bitwise-identical rate) and over-claim-block rate as headline metrics.

**中文:** 申请满额 $30,000,三个月三步走,每步都有拿得出手的结果;把"可复现率""越级拦截率"定为核心指标——评审偏爱可量化成果。

---

## 7. Biosecurity / Responsible Use(生物安全 · 别小看)

**英文(贴表单):**
> This is a defensive, reproducibility-focused project. It analyzes gene-expression *association* from public datasets; it does not design pathogens, sequences, or wet-lab protocols. Safety is built into the architecture: the claim ceiling prevents escalation beyond the evidence, mock and fabricated data are hard-isolated from verified evidence, and conservative failure states prevent forced or misleading conclusions. This aligns directly with Anthropic's responsible-use requirements.

**中文:** 生物安全审查这栏很多人乱填被刷。说清:纯防御、只分析公开数据,不碰病原体/序列设计/湿实验;而"不越级、不造假、宁可停下"本身就是安全设计,正对他们的政策。

---

## 提交前检查
1. `【★待你填】` 三处机构/团队信息填完
2. 英文段直接复制进表单;中文只给你看,别贴
3. 7月15号前提交
