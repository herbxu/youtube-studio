# 三仓库布局

三个 Git checkout 默认放在同一父目录。代码仓库是 youtube-studio；用 YOUTUBE_WORKS_ROOT 和 YOUTUBE_WORKBENCH_ROOT 可分别覆盖另外两个仓库的根路径（在 shell 中 export）。

正式作品在同级 `youtube/episodes/<ID>`；试剪样片在 `youtube-workbench/examples/<ID>`。文中的 `build/`、`.cache/`、`state.json` 和 `.run.lock` 均相对工作台 `runtime/episodes/<ID>/`（样片使用 `runtime/examples/<ID>/`）；`deliverables/` 相对剧集根。

| 位置 | 内容 |
|---|---|
| youtube/episodes/<ID> | script.json、brief.json、config.json、原始记录、素材、正式交付与验收记录 |
| youtube-studio | src、skills、config、tests、resources、docs；.env.local 和本地依赖不进 Git |
| youtube-workbench/episodes/<ID> | 开发稿、试剪版本、听审对照 |
| youtube-workbench/examples/<ID> | 可编辑的制作样片 |
| youtube-workbench/runtime/{episodes,examples}/<ID> | build（预览在 build/preview）、缓存、状态、运行锁；整体忽略 |
| youtube-workbench/runtime/historical-project-build | 原根 build 中的一次性制作、迁移和检查工具及其输出 |

在 youtube-studio 运行：`youtube-studio doctor --episode ../youtube/episodes/<ID>`。CLI 的 --episode 仍是输入目录；独立临时工程保留本地布局。三仓库使用相同剧集名，无需嵌套 Git 仓库或符号链接。

完成的全片文件、QA 与审阅结论不因迁移重算或升级。历史报告中的路径按迁移映射解析，代码版本变化后 status / quality 可能提示旧输入。运行中的锁及未决或付费任务记录不得清理。历史结构可在作品库拆分前提交 d3bf0d5 中查阅。
