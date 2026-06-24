# CI 工作流

`ci.yml` 是 GitHub Actions 工作流（安装 → ruff → mypy → 离线 unittest，矩阵 py3.10/3.11/3.12）。

本次推送用的 token 没有 `workflow` 权限范围，无法直接把它放进 `.github/workflows/`，
所以临时放在这里。启用方式（任选其一）：

1. 在 GitHub 网页端把本文件内容复制到 `.github/workflows/ci.yml` 并提交（网页提交不受 token scope 限制）；或
2. 给所用 PAT 加上 `workflow` 权限范围后，执行：
   `git mv ci/ci.yml .github/workflows/ci.yml && git commit -m "ci: enable workflow" && git push`
