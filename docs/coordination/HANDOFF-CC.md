# HANDOFF-CC — CC 完整接手文档（单文件全量交接）

> 给**下一个接手的 CC**。读完本文件 + `BOARD.md` + `log/` 最新几条 turn + 本机 `~/.cc-keepalive/worklog.md`，即可全盘接手，无需追溯聊天历史。
> 写于 2026-06-25，最新 turn = **0030**。本文件不含任何 token/私钥/密钥。

---

## 0. 一句话现状
这是**朋友的「自动生信系统核心闭环」项目**（不是 KAMIA 自己的项目）。CC（你）是项目主管，负责全部代码/测试/PR。当前 **R0-01-REMEDIATION 8/8 闸门全部完成、真实 PR #1 已建并修完一轮 review（head `c2d5556`，111 tests OK），正等 CEO 复审/合并**。一个 OS crontab 自主 loop 每 5 分钟（今晚 24 点后回 20 分钟）唤醒一次 headless CC，自动推进/回应、只在重大事项经握手过问 CEO。

## 1. 项目与五角色
- **仓库**：`https://github.com/TOTO-git-q/rebuild_bioinform_analysis`（owner = `TOTO-git-q`）。
- **本机稳定克隆**：`/home/kamiafytl/rebuild-coordination`（loop 与人工都用它；不在会话 scratchpad，跨会话存活）。
- **角色**：
  1. **股东 / CC 持有者 = KAMIA**：只启动项目，之后不参与日常决策；提供 CC 运行环境（这台机器）。
  2. **CEO = 朋友**：唯一最终决策者（产品范围/验收/合并/发布）。
  3. **GPT Pro**：CEO 的顾问，建议须经 CEO 确认才算数。
  4. **Codex**：CC↔CEO 的**唯一传话桥梁**（在朋友侧运行），只读取/整理/转达/记录，**不决策、不写产品代码**。
  5. **CC（你）**：全部代码/测试/文档/PR；**不自合并**；规定边界内自主，只有真 blocker 才升级。

## 2. 协调握手系统（消息总线）
- **总线 = GitHub `coordination` 分支**，目录 `docs/coordination/`。总线上只有两个自动写者：**CC 与 Codex**；CEO/GPT 坐在 Codex 身后。
- **消息 = append-only turn 文件**：`log/NNNN-<from>-to-<to>-<type>-<ref>.md`，四位递增、只追加不改写。头部 YAML：`turn/from/to/type/ref/status/date`。type ∈ WORK_ORDER/REPORT/QUESTION/ANSWER/ACK/BLOCKER/DECISION/PROPOSAL/RATIFY。
- **关键文件**：`README.md`(总览) `PROTOCOL.md`(机制) `BOARD.md`(实时状态板，**每次先读**) `CONSTITUTION.md`(治理真值源 v1.0) `CODEX-KEEPALIVE.md` `CC-KEEPALIVE.md` `OPS-00-REPORT.md` 本文件。
- **真值源铁律**：只有 coordination 分支上的文件算数；**未落成 turn 的口头指令对 CC 无效**。

## 3. 治理现状（截至 turn 0030）
| 项 | 值 |
|---|---|
| governance_status | RATIFIED |
| constitution_version | 1.0（`CONSTITUTION.md`，12 条不变量 + G1–G6 + 强制停审点） |
| execution_gate | **R0-01_REVIEW_FIX_ONLY_BY_CEO_OVERRIDE** |
| OPS-00 | **CEO_OVERRIDE_ACTIVE_UNVERIFIED**（**不是** verified PASS） |
| R0-01 | CHANGES_REQUESTED（PR #1 review 中） |
| R0-02 | FORBIDDEN（被 R0-01 阻塞） |

## 4. 安全整改史 OPS-00（为什么是 active-by-override 而非 PASS）
CC 最初搭了个高权限定时 cron 自启完整 CC。CEO/GPT 连续三轮抬高安全要求：
- **turn 0006 OPS-00**：停高权限 cron（OPS-00.1，已做）+ 隔离环境。
- **turn 0011**：加 **Git broker**（固定动词中介，只推 wo 分支/建改 PR，拒绝 merge/force/删/改 workflow/ruleset/secret）+ 凭据隔离（poller/沙箱不碰 token）+ 13 项负向测试 + 收窄 token。
- **turn 0014**：长期凭据改 **GitHub App** + 三分支 ruleset + coordination append-only 校验 + 在场测试。
- **turn 0016 CEO override**：CEO **书面**把门降了，宣布握手即刻激活，状态记为 `CEO_OVERRIDE_ACTIVE_UNVERIFIED`，授权 `AUTOMATED_GITHUB_WRITE=ENABLED_BY_CEO_OVERRIDE`、`execution_gate=R0-01_REVIEW_FIX_ONLY`。

**已建并自测的安全件**（`~/.cc-keepalive/`，附录 A 全文）：bwrap 沙箱（selftest PASS）、轻量轮询器（7/7）、Git broker（授权矩阵 16 项）、密钥隔离（poller 无 token、沙箱读不到 secret）、轮换/吊销、并发/重启去重、append-only 校验器（5/5）。
**要转成 verified PASS 仍需 owner 做**：① GitHub App（仅本仓库，Metadata R/Contents RW/PR RW，其余 No access，私钥带外注入）② 三分支 ruleset（main/auto-bioinfo-core/coordination：要 PR、挡 force push、禁删、不许 bypass）③ 在场负向测试。详见 `OPS-00-REPORT.md` 与 turn 0012/0013/0015。

## 5. 自主 loop 基础设施（本机 host 侧）
- **触发**：OS `crontab`（`crontab -l`）→ `/home/kamiafytl/.cc-keepalive/loop-tick.sh`。
  - 当前 **每 5 分钟**（`*/5`）；**2026-06-26 00:00 自动恢复 20 分钟**（`7,27,47`）——由 `revert-interval.sh` 改回并自删该 cron 行（KAMIA 临时要求）。常态是 20 分钟。
- **每个 tick**：单实例 `flock`（`loop.lock`）→ 急停开关检查（`DISABLED` 文件存在即退出）→ `git fetch` → 启动一次 headless `claude -p`（host 侧，`--dangerously-skip-permissions`，active-by-override 下）做**「一步」**：①优先回应新的 to:CC OPEN turn；②否则推进 R0-01-REMEDIATION 下一小步（写代码+测试+commit+push wo 分支）；③8 闸门全绿则建/修 PR；④无活则结束。
- **诚实/纪律**：日常小步只记 `worklog.md` 不刷屏 turn；只有**重大决策/阶段完成/真 blocker**才写 turn 过问 CEO；不自合并、不动 main/base、不开 R0-02、不公开发布；来源不明/冲突宪法即 BLOCKER。
- **可观测/可控**：进度 `~/.cc-keepalive/worklog.md`；tick 起止 `~/.cc-keepalive/loop.log`；**急停** `touch ~/.cc-keepalive/DISABLED`；**彻底停** 删 crontab 里 loop-tick 行。
- **局限**：loop 是独立后台进程，**只能写 GitHub 总线，无法往任何聊天窗口发消息**；要桌面提醒需另接（未接）。host 关机/WSL 休眠期间 loop 暂停，总线消息不丢，开机自动续。

## 6. 当前任务状态（R0-01-REMEDIATION，核心）
**工作分支**：`rebuild/wo-r0-01-truthful-mode`（base = `rebuild/auto-bioinfo-core`）。
**8 个闸门全部完成**（按 turn 0007/0014 复审的 8 阻断 + 9 绕过测试）：
1. 唯一 authoritative eligibility gate（`provenance.authoritative_release`，inspect/report/bundle/CLI 统一走它，缓存布尔降为展示）— commit 845c133
2. decision integrity（`verify_decision_integrity`/`decision_is_authoritatively_eligible`）— f50be1a
3. ProjectPolicy 完整性（`verify_project_policy_integrity`，policy+state 同篡改也检出）— 7db3e97
4. formal export 门（`export --formal` 不合格非零退出且无产物）— 88f8b0e
5. REAL 锁定门（`validate_real_mode_lock`，verification≥checksum、拒 recorded-replay、四要素 manifest）— 501b6a1
6. legacy 行为（一次性 DEMO 迁移 vs 具名 MIGRATION_REQUIRED，不裸抛 PipelineError）— 4ce4159
7. validate_provenance 结构化核验（source_class×retrieval_mode×verification 矩阵）— 59a9443
8. bundle README 随实际 source_class 生成文案 — 783548e
**真实 PR #1**：已建（GitHub REST API，无 gh CLI），base `rebuild/auto-bioinfo-core` ← head `rebuild/wo-r0-01-truthful-mode`，OPEN 未合并。
**一轮 review-fix**：turn 0029 CEO 给 PR#1 = CHANGES_REQUESTED（3 个 blocker：缓存绑定去依赖 / decision-integrity 下游测试 / locked-manifest resume 门）；CC 修复完成 → **新 head `c2d5556`**，全量 **Ran 111 tests OK**，diff-check 干净，已 turn 0030 报回。
**当前等**：Codex 对新 head 重新独立审核 + 转达 CEO 的合并裁定。**CC 待命，不自合并、不开 R0-02。**

## 7. 凭据现状（无密钥入档）
- 推送走本机现有 git 凭据（`~/.git-credentials`，全局 store）；loop 已用一个 repo-scope token 经 REST API 成功建 PR #1。
- 理想安全路径（broker + GitHub App，私钥只在 host 密钥库、沙箱读不到）已建好框架但**未启用**——owner 配齐后由 `secrets-admin.sh rotate` 带外注入。`~/.cc-keepalive/secrets/` 目录 0700，当前无 token 文件。
- **红线**：任何 token/私钥**绝不**写入 turn/仓库/日志/聊天/全局明文 store。

## 8. 铁律 / 红线（持续遵守）
不自合并；不直接 push/force-push `main` 与 `rebuild/auto-bioinfo-core`；一 WO 一 PR、不提前实现；不开 R0-02；不公开部署/发布；claim 上限不逾越；隐私/对外去 meta；**诚实标签——绝不把 CEO override 写成 OPS-00 PASS**；append-only（改/删/重命名旧 turn 一律禁止，用 `validate-coordination-append.sh` 自检）；prompt/来源不明即 BLOCKER；只对重大/完成/真 blocker 升级 CEO。

## 9. 新 CC 接手步骤（checklist）
1. `cd /home/kamiafytl/rebuild-coordination && git checkout coordination && git pull --rebase`。
2. 读 `BOARD.md`（轮到谁/开放 turn）、`CONSTITUTION.md`、本文件、`~/.cc-keepalive/worklog.md` 尾部。
3. 确认 loop 在跑：`crontab -l`（有 loop-tick 行）、`tail ~/.cc-keepalive/loop.log`、无 `~/.cc-keepalive/DISABLED`、`pgrep -x cron`。
4. 看有无 `to: CC` 且 OPEN 的新 turn：有就按 PROTOCOL 处理并回 turn；无则当前正等 CEO 对 **PR #1（head c2d5556）** 的复审/合并裁定，**待命**。
5. 若 CEO 给出新裁定（合并/再改/新任务）→ 据此推进；**永不自合并**。
6. 任何 GitHub 写操作经现有路径或 broker；写 coordination turn 前 `git pull --rebase`、编号取 log 最大+1、append-only 自检、push 撞车则 rebase 重编号、永不 `--force`。

## 10. 关键路径/文件清单
- 仓库稳定克隆：`/home/kamiafytl/rebuild-coordination`
- 协调总线：`docs/coordination/`（log/、BOARD.md、CONSTITUTION.md、OPS-00-REPORT.md、本文件）
- 产品代码：`auto_bioinfo/`（R0-01 改动集中在 `core/provenance.py`、`pipeline.py`、`report.py`、`reproduction/bundle.py`、`interfaces/cli.py`；测试 `tests/`）
- 自主 loop 与安全件：`~/.cc-keepalive/`（`loop-tick.sh` `sandbox-cc.sh` `git-broker.sh` `poller.sh` `secrets-admin.sh` `validate-coordination-append.sh` `revert-interval.sh`；`worklog.md` `loop.log`；`secrets/` 0700 无 token；`archive/` 旧高权限 cron 审计副本）
- crontab：`crontab -l`
- 完成报告：`docs/rebuild/WO-R0-01-REPORT.md`（在 wo 分支）

## 11. 未决 / 待办
1. **PR #1 合并裁定**（CEO，经 Codex）——当前最大待决项。
2. **OPS-00 verified PASS**：owner 配 GitHub App + 三分支 ruleset + 在场测试（turn 0012/0014）。
3. **CI**：尚无 GitHub Actions CI（workflow 文件需 owner/workflow 权限）；CEO 复审要求"真实 PR + CI"，CI 这一环待 owner。
4. R0-02：R0-01 合并后才可提。

---
**附录 A：自主 loop 与安全脚本全文**（供异机重建；如在同机，直接用 `~/.cc-keepalive/` 下的）见本文件末尾代码块。

## 附录 A — 脚本全文（截至 2026-06-25，来自 host `~/.cc-keepalive/`）

> crontab 当前内容：
```cron
*/5 * * * * /home/kamiafytl/.cc-keepalive/loop-tick.sh
0 0 26 6 * /home/kamiafytl/.cc-keepalive/revert-interval.sh
```

### `~/.cc-keepalive/loop-tick.sh`
```bash
#!/usr/bin/env bash
# CC 自主 loop tick — OS crontab 调（每 ~20min）。CEO override turn 0016 授权的 active-by-override 自动化。
# 单实例锁；扫 coordination 保活；有活就启一次 headless claude 做"一步"；不自合并；
# 只对重大事项/完成/真阻塞经握手过问 CEO；`touch ~/.cc-keepalive/DISABLED` 可急停。
set -uo pipefail
export PATH=/home/kamiafytl/local/node/bin:/usr/local/bin:/usr/bin:/bin
DIR=/home/kamiafytl/.cc-keepalive
REPO=/home/kamiafytl/rebuild-coordination
LOG="$DIR/loop.log"; LOCK="$DIR/loop.lock"; KILL="$DIR/DISABLED"
log(){ echo "$(date -Iseconds) $*" >> "$LOG"; }

[ -f "$LOG" ] && [ "$(stat -c%s "$LOG" 2>/dev/null||echo 0)" -gt 2000000 ] && mv -f "$LOG" "$LOG.1"
[ -e "$KILL" ] && { log "[killswitch] DISABLED 存在 → 急停"; exit 0; }
exec 9>"$LOCK"; flock -n 9 || { log "[skip] 上一 tick 仍在运行"; exit 0; }

log "=== tick 开始 ==="
cd "$REPO" 2>/dev/null || { log "[err] repo 不可达 $REPO"; exit 1; }
git fetch origin --quiet 2>>"$LOG" || log "[warn] fetch 失败"

read -r -d '' PROMPT <<'EOF'
[CC 自主 loop·自动触发] 你是 GitHub 项目 rebuild_bioinform_analysis 的项目主管 CC，处于 CEO override(turn 0016) 授权的 active-by-override 自主态。本次只做"一步"然后结束，保持高质量、可审计、诚实。

【准备】cd /home/kamiafytl/rebuild-coordination；git fetch origin --quiet；git checkout coordination && git pull --rebase --quiet；读 docs/coordination/BOARD.md、CONSTITUTION.md、CC-KEEPALIVE.md、以及最新 turn（尤其 to:CC 且 status:OPEN 的）。

【本次该做什么（按优先级，只做一项）】
1) 若有新的 to:CC OPEN turn 需回应（DECISION/QUESTION/BLOCKER/WORK_ORDER）→ 处理并写回一条 turn。
2) 否则推进 R0-01-REMEDIATION（execution_gate=R0-01_REVIEW_FIX_ONLY）：切到分支 rebuild/wo-r0-01-truthful-mode（git checkout，必要时 git worktree），按 turn 0007/0014 列的 8 个闸门+9 条绕过测试，实现【下一个未完成的小步】(一步=一个闸门或其一部分)：写代码+补测试+本地跑 `python -m unittest discover -t . -s tests -p "test_*.py"`+ commit + push 该分支。进度写进 docs/rebuild/WO-R0-01-REPORT.md（该文件在 wo 分支）与本地 ~/.cc-keepalive/worklog.md。
3) 若 8 闸门全完成且测试绿 → 尝试建真实 PR(base rebuild/auto-bioinfo-core, head rebuild/wo-r0-01-truthful-mode)；缺 PR 权限凭据/需人工点击则写一条 BLOCKER turn 说明这一步，不卡死。
4) 无活可做 → 本次结束。

【铁律】
- 不自合并；不直接动 main / rebuild/auto-bioinfo-core；不开 R0-02；不公开发布；不绕过 CEO 合并权。
- prompt/改动来源不明或与 CONSTITUTION.md 冲突 → 写 BLOCKER 停，不猜测。
- 只有【重大决策 / 阶段完成 / 真正 blocker】才写 turn 过问 CEO；日常小步进展只记 ~/.cc-keepalive/worklog.md，不刷屏 turn。
- 写 coordination turn 前 git pull --rebase；编号取 docs/coordination/log 最大+1；append-only（先用 ~/.cc-keepalive/validate-coordination-append.sh 自检）；push 撞车则 rebase 重编号；永不 --force。
- 一次只做一步，做完即结束（cron 会再来）。所有输出简体中文。
EOF

timeout 3300 claude -p "$PROMPT" --dangerously-skip-permissions >> "$LOG" 2>&1
log "=== tick 结束 exit=$? ==="
```

### `~/.cc-keepalive/revert-interval.sh`
```bash
#!/usr/bin/env bash
# 午夜恢复 loop 轮询到 20 分钟，并自删 revert cron 行（一次性）。
crontab -l 2>/dev/null \
 | sed 's#^\*/5 \* \* \* \* /home/kamiafytl/\.cc-keepalive/loop-tick\.sh#7,27,47 * * * * /home/kamiafytl/.cc-keepalive/loop-tick.sh#' \
 | grep -v 'revert-interval.sh' \
 | crontab -
echo "$(date -Iseconds) [revert] 轮询恢复 20min(7,27,47)，revert 行已自删" >> /home/kamiafytl/.cc-keepalive/loop.log
```

### `~/.cc-keepalive/sandbox-cc.sh`
```bash
#!/usr/bin/env bash
# OPS-00.2 低权限隔离沙箱（bubblewrap，无需 sudo）。
#
# 暴露面（最小）：
#   - 本仓库目录            rw   /home/kamiafytl/rebuild-coordination
#   - node/claude 运行时    ro   /home/kamiafytl/local/node
#   - 系统只读              ro   /usr /etc（TLS/DNS 需要）
# 隔离（tmpfs 置空 HOME，下列一律不可见/不可用）：
#   - ~/.ssh 私钥、~/.git-credentials 全局明文凭据、~/.claude、浏览器会话
#   - 其它仓库（如 ~/kamia-ai）、无关环境变量与 secrets
#   - 无 sudo、无 docker socket、放弃所有 capability、新会话
#
# 用法：
#   sandbox-cc.sh --selftest        运行隔离边界负向测试（OPS-00.2 证据）
#   sandbox-cc.sh -- <cmd...>       在沙箱内执行命令（真实 CC 启动用）
set -uo pipefail

REPO="${CC_REPO:-/home/kamiafytl/rebuild-coordination}"
NODE_DIR=/home/kamiafytl/local/node
HOME_DIR=/home/kamiafytl

bwrap_base=(
  bwrap
  --ro-bind /usr /usr
  --symlink usr/bin /bin
  --symlink usr/lib /lib
  --symlink usr/lib64 /lib64
  --symlink usr/sbin /sbin
  --ro-bind /etc /etc
  --proc /proc
  --dev /dev
  --tmpfs /tmp
  --tmpfs "$HOME_DIR"
  --ro-bind "$NODE_DIR" "$NODE_DIR"
  --bind "$REPO" "$REPO"
  --setenv HOME "$HOME_DIR"
  --setenv PATH "$NODE_DIR/bin:/usr/bin:/bin"
  --chdir "$REPO"
  --unshare-all
  --share-net
  --cap-drop ALL
  --die-with-parent
  --new-session
)

if [ "${1:-}" = "--selftest" ]; then
  exec "${bwrap_base[@]}" -- /bin/bash -c '
    fail=0
    echo "whoami        : $(whoami)  uid=$(id -u)"
    echo "[chk] ~/.ssh                : $(ls -d ~/.ssh 2>/dev/null && { echo 可见-BAD; } || echo 不可见-OK)"
    [ -e ~/.ssh ] && fail=1
    echo "[chk] ~/.git-credentials    : $([ -e ~/.git-credentials ] && echo 可见-BAD || echo 不可见-OK)"
    [ -e ~/.git-credentials ] && fail=1
    echo "[chk] ~/.claude             : $([ -e ~/.claude ] && echo 可见-BAD || echo 不可见-OK)"
    [ -e ~/.claude ] && fail=1
    echo "[chk] 其它仓库 ~/kamia-ai   : $([ -e /home/kamiafytl/kamia-ai ] && echo 可见-BAD || echo 不可见-OK)"
    [ -e /home/kamiafytl/kamia-ai ] && fail=1
    echo "[chk] sudo 二进制            : $(command -v sudo >/dev/null 2>&1 && echo 存在 || echo 无-OK)"
    echo "[chk] sudo -n true 提权      : $(sudo -n true 2>/dev/null && echo 成功-BAD || echo 失败-OK)"
    sudo -n true 2>/dev/null && fail=1
    echo "[chk] docker socket         : $([ -S /var/run/docker.sock ] && echo 可见-BAD || echo 无-OK)"
    [ -S /var/run/docker.sock ] && fail=1
    echo "[chk] 本仓库可写             : $(touch '"$REPO"'/.sbx_w 2>/dev/null && { rm -f '"$REPO"'/.sbx_w; echo 可写-OK; } || echo 不可写-BAD)"
    echo "[chk] /usr 只读             : $(touch /usr/.sbx_w 2>/dev/null && { rm -f /usr/.sbx_w; echo 可写-BAD; } || echo 只读-OK)"
    echo "----"
    [ "$fail" = 0 ] && echo "SELFTEST: PASS（所有禁止项均不可达）" || echo "SELFTEST: FAIL"
    exit $fail
  '
fi

# 真实执行模式：在沙箱内运行传入命令。
# 注意：本基线 profile 故意不挂 ~/.claude 与 git 凭据；真实 CC 启动需在 OPS-00.3
# 拿到仓库级 fine-grained token 后，由 poller 以 --setenv 注入作用域内凭据 +
# 选择性 ro-bind claude 鉴权文件（仅该文件，不含 ssh/git-credentials/浏览器）。
exec "${bwrap_base[@]}" -- "$@"
```

### `~/.cc-keepalive/git-broker.sh`
```bash
#!/usr/bin/env bash
# OPS-00 Git Broker（host 侧）——唯一允许持有 write 凭据的组件。
#
# 固定动词中介（不接受任意 git 参数）。只允许：
#   push-work-branch <rebuild/wo-*>        普通 push 授权 work 分支（绝不 --force）
#   pr-create <head> <base>                建授权 PR（head=wo-*，base=rebuild/auto-bioinfo-core）
#   pr-update <head> <base>                更新授权 PR
# 一律永久拒绝（broker 不具备此能力）：
#   merge / force-push / delete-branch / modify-base / workflow / ruleset / secret / 其它
#
# poller 与 CC/bwrap 沙箱都【不持有、读不到】凭据；所有写操作只能经本 broker。
# token 经 GIT_ASKPASS 注入，绝不进 argv/URL/日志（避免 ps 泄露）。
set -uo pipefail
umask 077

SECRET_DIR="${CC_SECRET_DIR:-/home/kamiafytl/.cc-keepalive/secrets}"
TOKEN_FILE="$SECRET_DIR/gh_token"
ASKPASS="$SECRET_DIR/askpass.sh"
REPO_SLUG="${CC_REPO_SLUG:-TOTO-git-q/rebuild_bioinform_analysis}"
ALLOWED_BASE="rebuild/auto-bioinfo-core"
WORKBRANCH_RE='^rebuild/wo-[A-Za-z0-9._/-]+$'
PROTECTED='main rebuild/auto-bioinfo-core coordination'
WORKREPO="${CC_REPO:-/home/kamiafytl/rebuild-coordination}"

deny(){ echo "BROKER_DENY: $*" >&2; exit 3; }
is_protected(){ local b; for b in $PROTECTED; do [ "$1" = "$b" ] && return 0; done; return 1; }
CHECK=0; [ "${BROKER_CHECK:-0}" = "1" ] && CHECK=1   # 只判定 ALLOW/DENY，不执行、不碰 token

action="${1:-}"; shift 2>/dev/null || true
case "$action" in
  push-work-branch)
    br="${1:-}"
    [[ "$br" =~ $WORKBRANCH_RE ]] || deny "分支非授权 work branch: '$br'"
    is_protected "$br" && deny "拒绝推保护分支: $br"
    [ "$CHECK" = 1 ] && { echo "ALLOW push-work-branch $br"; exit 0; }
    [ -s "$TOKEN_FILE" ] || { echo "NO_CREDENTIAL: 凭据未配置（待 owner），无法 push $br"; exit 4; }
    GIT_ASKPASS="$ASKPASS" GIT_TERMINAL_PROMPT=0 \
      git -C "$WORKREPO" push "https://x-access-token@github.com/${REPO_SLUG}.git" \
      "refs/heads/${br}:refs/heads/${br}"   # 普通 push：无 --force、无 +refspec
    exit $?
    ;;
  pr-create|pr-update)
    head="${1:-}"; base="${2:-$ALLOWED_BASE}"
    [[ "$head" =~ $WORKBRANCH_RE ]] || deny "PR head 非授权 work branch: '$head'"
    [ "$base" = "$ALLOWED_BASE" ] || deny "PR base 只能是 $ALLOWED_BASE，收到: '$base'"
    [ "$CHECK" = 1 ] && { echo "ALLOW $action $head -> $base"; exit 0; }
    [ -s "$TOKEN_FILE" ] || { echo "NO_CREDENTIAL: 凭据未配置（待 owner）"; exit 4; }
    tok="$(cat "$TOKEN_FILE")"
    api="https://api.github.com/repos/${REPO_SLUG}/pulls"
    if [ "$action" = "pr-create" ]; then
      curl -fsS -X POST "$api" -H "Authorization: Bearer ${tok}" \
        -H "Accept: application/vnd.github+json" \
        -d "{\"head\":\"${head}\",\"base\":\"${base}\",\"title\":\"R0-01 truthful mode (auto)\"}" >/dev/null
      rc=$?
    else rc=0; fi
    tok=""; exit $rc
    ;;
  merge|force-push|delete-branch|modify-base|workflow|ruleset|secret)
    deny "动作被永久禁止：$action（broker 无此能力）"
    ;;
  *)
    deny "未知/未授权动作：'$action'"
    ;;
esac
```

### `~/.cc-keepalive/secrets-admin.sh`
```bash
#!/usr/bin/env bash
# OPS-00 凭据存储管理（轮换/吊销/状态）。
# 凭据只供 host 侧 Git broker 使用；CC/bwrap 沙箱不挂载本目录、读不到。
# 绝不把 token 打印到日志/聊天/turn/仓库/shell history。
set -uo pipefail
umask 077

SECRET_DIR="${CC_SECRET_DIR:-/home/kamiafytl/.cc-keepalive/secrets}"
TOKEN_FILE="$SECRET_DIR/gh_token"
ASKPASS="$SECRET_DIR/askpass.sh"

ensure_perms(){
  mkdir -p "$SECRET_DIR"
  chmod 700 "$(dirname "$SECRET_DIR")" 2>/dev/null || true
  chmod 700 "$SECRET_DIR"
  cat > "$ASKPASS" <<'EOF'
#!/bin/sh
# git 调用此脚本取密码（token）；用户名走 x-access-token。token 不进 argv。
cat "$(dirname "$0")/gh_token"
EOF
  chmod 700 "$ASKPASS"
  [ -f "$TOKEN_FILE" ] && chmod 600 "$TOKEN_FILE"
}

case "${1:-status}" in
  init)
    ensure_perms
    echo "secret 目录已就绪（0700）；askpass 已建（0700）。token 文件待 owner 注入到："
    echo "  $TOKEN_FILE   （注入后 chmod 600；本脚本 rotate 会自动设权）"
    ;;
  rotate)
    # 从 stdin 读新 token（不走 argv，避免 ps/history 泄露）：
    #   printf '%s' "<token>" | secrets-admin.sh rotate
    ensure_perms
    new="$(cat)"; [ -n "$new" ] || { echo "未从 stdin 读到 token"; exit 1; }
    umask 077; printf '%s' "$new" > "$TOKEN_FILE"; chmod 600 "$TOKEN_FILE"; new=""
    echo "token 已轮换并设权 0600（未回显内容）。broker 下次调用即用新值。"
    ;;
  revoke)
    if [ -f "$TOKEN_FILE" ]; then shred -u "$TOKEN_FILE" 2>/dev/null || rm -f "$TOKEN_FILE"; fi
    echo "本地 token 文件已删除。请 owner 在 GitHub 上同步吊销该凭据/GitHub App 授权。"
    ;;
  status)
    ensure_perms
    echo "secret 目录: $SECRET_DIR  权限=$(stat -c '%a' "$SECRET_DIR" 2>/dev/null)"
    echo "askpass    : $([ -f "$ASKPASS" ] && stat -c '%a' "$ASKPASS" || echo 缺)"
    echo "token 文件 : $([ -s "$TOKEN_FILE" ] && echo "存在 权限=$(stat -c '%a' "$TOKEN_FILE")（内容不回显）" || echo "未配置（待 owner）")"
    ;;
  *) echo "用法: secrets-admin.sh {init|rotate|revoke|status}"; exit 1;;
esac
```

### `~/.cc-keepalive/validate-coordination-append.sh`
```bash
#!/usr/bin/env bash
# OPS-00（裁定0014 §3）coordination append-only 校验器。
# 比较 <base-ref> 与 <head-ref> 对 docs/coordination/log/ 的改动，确保 append-only：
#   - 不修改/删除/重命名任何已存在 turn 文件；
#   - 新增 turn 编号严格大于 base 当前最大编号（单调递增）。
# 0=合法 append；非0=拒绝（broker 推 coordination 前调用，违规则拒推）。
set -uo pipefail
REPO="${CC_REPO:-/home/kamiafytl/rebuild-coordination}"
BASE="${1:-origin/coordination}"
HEAD="${2:-HEAD}"
P="docs/coordination/log/"
cd "$REPO" || { echo "REPO 不可达"; exit 2; }

maxbase=$(git ls-tree -r --name-only "$BASE" -- "$P" 2>/dev/null | grep -oE '[0-9]{4}' | sort -n | tail -1)
maxbase=${maxbase:-0000}
v=0
while IFS=$'\t' read -r st path rest; do
  case "$path" in "$P"*) ;; *) continue;; esac
  case "$st" in
    A) n=$(echo "$path" | grep -oE '[0-9]{4}' | head -1)
       { [ -n "$n" ] && [ "$((10#$n))" -gt "$((10#$maxbase))" ]; } || { echo "REJECT 新增编号非单调: $path (base max=$maxbase)"; v=$((v+1)); } ;;
    M) echo "REJECT 修改已存在 turn: $path"; v=$((v+1));;
    D) echo "REJECT 删除已存在 turn: $path"; v=$((v+1));;
    R*) echo "REJECT 重命名已存在 turn: $path -> ${rest:-?}"; v=$((v+1));;
    *) echo "REJECT 未知改动 $st: $path"; v=$((v+1));;
  esac
done < <(git diff --name-status -M "$BASE" "$HEAD")
[ "$v" -eq 0 ] && { echo "APPEND_ONLY_OK (base max=$maxbase)"; exit 0; } || { echo "APPEND_ONLY_VIOLATION x$v"; exit 1; }
```

### `~/.cc-keepalive/poller.sh`
```bash
#!/usr/bin/env bash
# OPS-00.4/5/6 轻量轮询器：确定性、不启模型。
# 仅当检测到一个【有效且未消费】的 to:CC WORK_ORDER 时，才在隔离沙箱内启动一次 CC；
# 否则立即退出。含单实例锁、超时、日志轮转、kill switch、来源校验、消费记账、防注入。
#
# 默认操作一个【专用 poller 克隆】，绝不碰人工工作克隆，避免 reset 误伤。
# 测试用 CC_REPO 指向 fixture，CC_LAUNCH_CMD 指向 stub。
set -uo pipefail
shopt -s nullglob

DIR=/home/kamiafytl/.cc-keepalive
REPO="${CC_REPO:-$DIR/poller-clone}"
LOG="${CC_LOG:-$DIR/poller.log}"
LEDGER="${CC_LEDGER:-$DIR/consumed.txt}"
LOCK="${CC_LOCK:-$DIR/poller.lock}"
KILL="${CC_KILL:-$DIR/DISABLED}"
ALLOWED_SENDERS="${CC_ALLOWED_SENDERS:-CODEX}"
LAUNCH_TIMEOUT="${CC_LAUNCH_TIMEOUT:-3600}"
LOG_MAX_BYTES="${CC_LOG_MAX_BYTES:-1048576}"

log(){ echo "$(date -Iseconds) $*" >> "$LOG"; }

# --- 日志轮转 ---
if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG" 2>/dev/null || echo 0)" -gt "$LOG_MAX_BYTES" ]; then
  mv -f "$LOG" "$LOG.1"
fi

# --- kill switch ---
if [ -e "$KILL" ]; then log "[killswitch] $KILL 存在 → 禁用，立即退出"; exit 0; fi

# --- 单实例锁 ---
exec 9>"$LOCK"
if ! flock -n 9; then log "[skip] 上一轮询器仍在运行"; exit 0; fi

touch "$LEDGER"
if [ "${CC_SKIP_GIT:-0}" = "1" ]; then
  # 测试旁路：直接读 fixture 文件，不做 git 拉取（离线确定性）
  cd "$REPO" || { log "[err] 仓库不可达 $REPO"; exit 1; }
else
  [ -d "$REPO/.git" ] || { log "[err] poller 克隆不存在: $REPO（需先 setup）"; exit 1; }
  cd "$REPO" || { log "[err] 仓库不可达 $REPO"; exit 1; }
  # 专用克隆，可安全 hard reset 保持确定性视图
  git fetch origin coordination --quiet 2>>"$LOG" || { log "[err] fetch 失败"; exit 1; }
  git checkout -q coordination 2>>"$LOG" || git checkout -q -b coordination origin/coordination 2>>"$LOG"
  git reset --hard origin/coordination --quiet 2>>"$LOG"
fi

BOARD="$REPO/docs/coordination/BOARD.md"
LOGDIR="$REPO/docs/coordination/log"
[ -f "$BOARD" ] || { log "[err] 无 BOARD"; exit 1; }

# --- OPS-00.5：以 BOARD「开放 turn」区块为准的开放 id（不只看文件 status）---
board_open_ids="$(awk -F'|' '
  /^## 开放 turn/{f=1; next}
  /^## /{f=0}
  f { gsub(/[[:space:]]/,"",$2); if ($2 ~ /^[0-9]{4}$/) print $2 }
' "$BOARD")"

field(){ grep -E "^$1:" "$2" | head -1 | sed -E "s/^$1:[[:space:]]*//"; }
report_exists_for(){ # 是否已有 CC 对该 ref 的 REPORT turn（OPS-00.5 防重跑）
  for r in "$LOGDIR"/*cc-to-codex*report*.md; do
    [ -f "$r" ] || continue
    [ "$(field ref "$r")" = "$1" ] && return 0
  done
  return 1
}

candidate=""
for f in "$LOGDIR"/*.md; do
  t_turn="$(field turn "$f")"; t_from="$(field from "$f")"; t_to="$(field to "$f")"
  t_type="$(field type "$f")"; t_ref="$(field ref "$f")"; t_status="$(field status "$f")"
  # OPS-00.6 校验链：
  [ -n "$t_turn" ] && [ -n "$t_from" ] && [ -n "$t_to" ] && [ -n "$t_type" ] && [ -n "$t_ref" ] || { continue; }   # schema 齐全
  echo " $ALLOWED_SENDERS " | grep -q " $t_from " || { log "[reject] 发件人不在允许名单: $f from=$t_from"; continue; }  # 来源允许名单
  [ "$t_to" = "CC" ] || continue                                       # 明确 to:CC
  [ "$t_type" = "WORK_ORDER" ] || continue                             # 仅 WORK_ORDER 触发启动
  [ "$t_status" = "OPEN" ] || continue
  echo "$board_open_ids" | grep -qw "$t_turn" || { continue; }         # 必须在 BOARD 开放列表
  grep -qx "$t_turn $t_ref" "$LEDGER" && { continue; }                 # ledger 未消费
  report_exists_for "$t_ref" && { continue; }                          # 无已存在 REPORT
  candidate="$t_turn|$t_ref|$f"; break
done

if [ -z "$candidate" ]; then
  log "[no-task] 无有效未消费 to:CC WORK_ORDER → 不启动 CC，退出"
  exit 0
fi

IFS='|' read -r c_turn c_ref c_file <<< "$candidate"
# OPS-00.5：先记账再启动（崩溃/重启也不会重复执行）
echo "$c_turn $c_ref" >> "$LEDGER"
log "[task] 有效任务 turn=$c_turn ref=$c_ref → 隔离沙箱内启动一次 CC"

if [ -n "${CC_LAUNCH_CMD:-}" ]; then
  CC_TASK_REF="$c_ref" timeout "$LAUNCH_TIMEOUT" bash -c "$CC_LAUNCH_CMD" >>"$LOG" 2>&1; rc=$?
else
  # 默认占位：token 就绪前沙箱内不联网启动真实 CC（OPS-00.3 BLOCKER 未解）
  timeout "$LAUNCH_TIMEOUT" "$DIR/sandbox-cc.sh" -- /bin/echo "[placeholder] 沙箱内 CC ref=$c_ref（待 OPS-00.3 token）" >>"$LOG" 2>&1; rc=$?
fi
log "[task] CC 启动结束 ref=$c_ref exit=$rc"
exit 0
```
