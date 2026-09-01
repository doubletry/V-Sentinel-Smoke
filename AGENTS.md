# V-Sentinel-Smoke 仓库约定

## 发布流程

在 `doubletry/V-Sentinel-Smoke` 仓库发布新版本时，按以下步骤执行：

1. **合并到 main**：将功能分支 PR 以 `gh pr merge <PR号> --squash --delete-branch` 合并进 main。
2. **改版本号**：只改根目录 `pyproject.toml` 的 `version`（例如 `"2.7.1"`），不改 `core/pyproject.toml` 和 `frontend/package.json`。
3. **更新锁文件**：执行 `uv sync`（会同步更新 `uv.lock` 中的项目版本）。
4. **提交**：`git commit -m "chore(release): bump version to X.Y.Z"` 并 `git push origin main`。
5. **打标签**：`git tag -a vX.Y.Z -m "<说明>"` 并 `git push origin vX.Y.Z`。
6. **发布 GitHub Release**：`gh release create vX.Y.Z --title "vX.Y.Z" --notes-file <说明文件>`。**不要上传 tar.gz / docker 镜像等附件**（本地代理无法完成大文件上传，用户也不需要）。
7. 版本号规则：release 标签用 `vX.Y.Z`，`pyproject.toml` 的 `version` 与 release 版本保持同步。
