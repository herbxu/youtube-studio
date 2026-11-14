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

版本试剪、修音对照和历史导航页随工作台的版本索引保存。使用作品库的交付清单取用发布文件。归档的 QA 描述当次导出；CLI status 的顶层状态描述当前输入，archived_delivery 单列已存成片的哈希核对结果。工作台私有运行资料的恢复位置和核对步骤见工作台 README。

作品库的 `知识学习/<主题>/README.md` 按问题组织学习顺序，直接链接 `episodes/<ID>` 下的成片或原稿。作者手动上传使用 export-upload 单独导出的目录。
