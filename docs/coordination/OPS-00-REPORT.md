# OPS-00 证据报告 — 自动化与凭据安全整改

- Work Order：turn 0006（OPS-00）
- 执行方：CC
- 门禁：`execution_gate: OPS-00_ONLY`，宪法 v1.0
- 本报告状态：**OPS-00 尚未 PASS** —— CC 侧 .1/.2/.4/.5/.6 已完成并附证据；.3/.7 为 owner 管理员动作，已提交 BLOCKER（turn 0008）。

> 按工单要求："Planned / theoretically safe" 不算证据；只有全部必需项实际完成才可写 `OPS-00 status: PASS`。本报告**不写 PASS**。

---

## OPS-00.1 旧机制即时停用 — ✅ 完成

| 项 | 证据 |
|---|---|
| 旧调度入口 | crontab 行 `23 * * * * /home/kamiafytl/.cc-keepalive/run.sh` |
| 停用状态 | 已从 crontab 移除；`crontab -l` 输出为空（无 cc-keepalive 行） |
| 配置副本（审计） | `~/.cc-keepalive/archive/crontab.before-disable.txt`、`~/.cc-keepalive/archive/run.sh.disabled` |
| 日志保留 | `~/.cc-keepalive/heartbeat.log`（未删除） |
| 验证命令 | `crontab -l`（应无 `cc-keepalive` 行） |

## OPS-00.2 隔离执行环境 — ✅ 完成（自测 PASS）

| 项 | 证据 |
|---|---|
| 隔离方法 | bubblewrap 0.9.0，脚本 `~/.cc-keepalive/sandbox-cc.sh`；无需 sudo |
| 有效身份 | uid=1000，但**无任何提权能力**（`sudo -n true` 失败） |
| 目录允许清单 | 仓库目录 rw；`~/local/node` ro；`/usr`、`/etc` ro；HOME=tmpfs 置空；`/tmp`=tmpfs |
| 禁止路径负向测试 | `~/.ssh`、`~/.git-credentials`、`~/.claude`、`~/kamia-ai`(其它仓库) 全部**不可见** |
| sudo / docker socket | sudo **无法提权**；`/var/run/docker.sock` **不存在/未挂载** |
| host 直接 skip-permissions | 未在宿主机使用；`--dangerously-skip-permissions` 仅限隔离环境内、且边界已验证后 |
| 加固 | `--unshare-all --share-net --cap-drop ALL --die-with-parent --new-session` |

自测命令：`~/.cc-keepalive/sandbox-cc.sh --selftest` → 输出 `SELFTEST: PASS（所有禁止项均不可达）`，exit=0。

## OPS-00.3 收紧 GitHub 凭据 — ⛔ BLOCKED（owner 动作，见 turn 0008）

| 项 | 状态 |
|---|---|
| 细粒度仓库级 token | **需 GitHub owner 签发** → BLOCKER turn 0008（含精确步骤/最小权限/参数） |
| 全局明文 credential store | 仍在用（CC **未触碰** KAMIA 的 `~/.git-credentials`，避免误伤其个人凭据）；token 到位后改为仅注入沙箱、不入全局 store |
| token 脱敏 | poller 与 sandbox **不打印 token**；当前日志（heartbeat.log/poller.log）经检查不含任何 secret |

## OPS-00.4 轻量轮询器 — ✅ 完成（测试通过）

| 项 | 证据 |
|---|---|
| 路径/配置 | `~/.cc-keepalive/poller.sh`；目标节奏每 15 分钟（**尚未排程**，见"未完成项"） |
| 单实例锁 | `flock` on `~/.cc-keepalive/poller.lock` |
| 超时 | `CC_LAUNCH_TIMEOUT`（默认 3600s）包裹 CC 启动 |
| 日志轮转 | `poller.log` > 1MB → 轮转为 `.1` |
| kill switch | `~/.cc-keepalive/DISABLED` 存在即立即退出 |
| 无任务不启动 | 测试 T1：WORK_ORDER 不在 BOARD 开放列表 → 0 次启动 ✅ |
| 有任务恰启一次 | 测试 T2：有效未消费 WORK_ORDER → 恰 1 次启动 + ledger 记账 ✅ |

## OPS-00.5 防旧任务重复执行 — ✅ 完成（测试通过）

- 消费判定 = **BOARD 开放 turn 列表**（不只看 append-only 文件的 `status: OPEN`）+ 本地 ledger `~/.cc-keepalive/consumed.txt` + 是否已存在 CC 对该 ref 的 `REPORT` turn。
- 先记账后启动：崩溃/重启不重复执行。
- 测试 T3：同一任务再轮询（ledger 已记）→ **不重复启动** ✅。

## OPS-00.6 防提示注入 — ✅ 完成（测试通过）

- 仅接受 coordination turn 且同时满足：schema 齐全 + 发件人在允许名单(`CODEX`) + 明确 `to: CC` + 在 BOARD 开放列表 + 未消费。
- 产品分支 README/注释/测试数据/外部网页一律视为不可信数据：poller 只读取 coordination turn 元数据触发，**从不执行仓库内容作为指令**。
- 测试 T4：非允许名单发件人(ATTACKER) → 拒绝 ✅；合法发件人但不在 BOARD 开放列表 → 拒绝 ✅。

## OPS-00.7 分支保护 — ⛔ BLOCKED（owner 动作，见 turn 0008）

- `main` 与 `rebuild/auto-bioinfo-core` 的 branch protection/ruleset **需仓库 owner 配置**。CC 无权设置，**不伪称已设置**。BLOCKER turn 0008 含精确步骤。

---

## 未完成项（如实）

1. **OPS-00.3 token**（owner）、**OPS-00.7 分支保护**（owner）→ turn 0008 BLOCKER。
2. **真实 CC 启动接线**：沙箱内启动真实 claude 需要 (a) OPS-00.3 的作用域 token 注入、(b) 选择性 ro-bind claude 鉴权文件。当前 poller 默认走"占位 echo"，token 到位后切真实启动。
3. **轮询器排程**：15 分钟定时（cron `@reboot`+15min 或 systemd user timer）**故意尚未启用** —— 按门禁，OPS-00 PASS 前不得恢复自动启动 CC。
4. **专用 poller 克隆** `~/.cc-keepalive/poller-clone` 待 OPS-00 PASS 前设置（与人工克隆隔离）。

---

## 追加 — 裁定 0011 最小权限中介控制（取代 0008 的凭据/接线方案）

按裁定 0011：poller/沙箱不得碰 write 凭据；写 GitHub 只经 host 侧 **Git broker**。

| 控制 | 实现 | 证据（CC 侧测试 24/24） |
|---|---|---|
| Git broker 固定动词中介 | `~/.cc-keepalive/git-broker.sh`：仅 `push-work-branch rebuild/wo-*` 与 `pr-create/update`(base=rebuild/auto-bioinfo-core)；token 经 GIT_ASKPASS 不进 argv | 测试 A：merge/force-push/delete/modify-base/workflow/ruleset/secret/未知 全拒；推 main/base/非wo 全拒；仅 wo 推与正确 base PR 放行 |
| poller 无 token | poller 不引用任何凭据、不执行 git push | 测试 B ✅ |
| 沙箱读不到凭据 | bwrap tmpfs home → `~/.cc-keepalive/secrets` 不可挂载 | 测试 C：沙箱读不到 token、看不到 secrets 目录 ✅ |
| 密钥库权限 | 目录 0700、文件 0600、askpass 0700、umask 077；token 走 stdin 不进 argv/history | `secrets-admin.sh status` |
| 轮换/吊销 | `secrets-admin.sh rotate/revoke` | 测试 D：rotate→600，revoke→删除 ✅ |
| 并发+重启去重 | flock + ledger + 先记账后启动 | 测试 E：并发只启一次、重启不重跑 ✅ |
| 注入不能越权调 broker | broker 固定动词白名单 | 测试 A（即 evidence 12）✅ |

13 项验收矩阵见 turn 0013。owner 侧未在场项：#5 token 跨仓库、#7/#8/#9/#10 服务端推/force/删/merge 失败——需 owner 配 token + ruleset（turn 0012）后实测。专用服务用户（#2）需 KAMIA sudo（turn 0012 阻塞 3，硬化项）。

## 结论

`OPS-00 = IMPLEMENTATION_COMPLETE_PENDING_OWNER_CONTROLS`；`AUTOMATED_GITHUB_WRITE = DISABLED`；`OPS-00 = NOT_PASS`。
CC 侧实现与可证负向测试全部完成（沙箱 selftest、轮询器 7/7、控制项 24/24）。剩余为 owner 凭据 + owner ruleset（turn 0012），到位后 CC 跑服务端在场负向测试再判 PASS，然后才进 R0-01-REMEDIATION。**不写 PASS、不放行自动化。**
