# CI 工作流

CI 工作流现已正式启用，位于 [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)。

它在 GitHub Actions 上运行与本地相同的 repo-native 质量门（矩阵 py3.10/3.11/3.12）：
`make install` → `make lint` → `make format-check` → `make typecheck` → `make test` → `make coverage`。
全部离线、确定性，不联网、不调用付费 LLM、不依赖数据库或外部服务。

> 历史说明：早期推送所用 token 缺少 `workflow` 权限范围，无法直接写入 `.github/workflows/`，
> 工作流曾临时暂存于本目录的 `ci.yml`。WP-01 CI 切片（T-01-08）授权后已将其落位到
> `.github/workflows/ci.yml`，本目录仅保留此说明。
