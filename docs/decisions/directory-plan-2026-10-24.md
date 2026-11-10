# 目录清理结果与待确认规划

状态：用户已回复“采用，批准删除旧工程”，目录迁移和两套旧样片删除已执行。下文保留审批时的方案及清理背景；执行明细见 [迁移审计](layout-migration-2026-10-24.json)，当前使用规则见 [目录指南](../guides/repository-structure.md)。

## 已执行的清理

| 范围 | 文件字节合计（约） | 处理 |
|---|---:|---|
| node_modules | 131.3 MB | 删除可重装的 Node 安装目录 |
| .venv | 11.0 MB | 删除本项目 Python 环境，未触碰系统或其他项目依赖 |
| 根目录 build | 0.06 MB | 删除检查脚本、日志和临时联系表 |
| archive | 43.2 MB | 删除旧架构/技能方案、历史报告副本及研究中间文件；docs 正式报告和保留证据仍在 |
| 四个 production/.cache | 1,502.7 MB | 全部为成功完成的 normalize/master/render/footage/audio-mix 本地任务，无生成图片、TTS 或 uncertain 计费请求记录 |

共删除 10,301 个文件，文件大小合计 1,688,160,600 字节（约 1.69 GB / 1.57 GiB）。这不是精确物理空间回收量；文件系统压缩、克隆和分配单位会影响实际占用。du 近似占用由 3.4G 降至 1.8G。

[机器清单](cleanup-2026-10-24.json) 保留删除路径、文件数、字节数及受保护文件哈希。清理前后复核 113 个脚本、配置、录音/对齐/媒体引用及现有成片，未发生变化。Git 历史、依赖声明/锁文件、src、tests、skills、resources 和未提交修改保留。

删除依赖后当前不能直接完成视频生产。需要运行时按 README 重建项目环境并安装 Python 依赖、执行 npm ci；本轮不重新下载已要求删除的安装包。没有将删依赖后的状态报告为完整生产测试通过。

## 当前目录的问题

1. 源码侧已有合理分工。src 约 128K、tests 约 76K、skills 约 72K，整体重构成复杂多包工程没有实际收益。Python 与 Node 依赖清单都仍在使用，不应当作无关文件删除。
2. 内容侧约 1.6G。21 单元《竞争优势》成片约 838 MiB，是已有交付，不是重复缓存；另有输入素材和中间产物。删除缓存后，大文件不会全部消失。
3. 正式剧集与三种风格样片并列在 episodes，难以区分实际选题和制作实验。
4. production/build 混放最终成片、QA、可重建 HTML，以及必须保留的录音输入。《竞争优势》有 42 条 audio/words 引用指向 build/recording-import；清空整个 build 会直接损坏工程。
5. docs 混合使用指南、博主研究、实施记录及迁移审计；历史状态容易被误认为当前规则。skills 保留操作方法，docs 保存依据，不再重复维护同一套技术契约。
6. CLI 当前固定追加 production，素材路径也要求位于 production 内。下面的扁平结构是目标方案，必须同步改代码和测试；仅移动文件不成立。

## 推荐目录

保留根目录标准依赖清单；不为了减少几个文件另设依赖目录。

```text
youtube/
├── README.md
├── AGENTS.md
├── pyproject.toml / requirements.txt
├── package.json / package-lock.json
├── src/youtube_studio/       # 程序；本轮不再拆包
├── tests/                   # 单元、集成检查与固定测试数据
├── skills/                  # 五个制作技能及契约
├── config/                  # 默认配置
├── resources/               # 公共字体与许可证
├── docs/
│   ├── guides/              # 安装、运行、结构与维护
│   ├── research/            # 小A、思维咖啡报告及各自 evidence
│   └── decisions/           # 当前设计决策、迁移与清理审计
├── episodes/<日期>-<主题>/  # 正式内容
│   ├── source/              # 原稿、原始录音、策划及输入资料
│   ├── brief.json
│   ├── script.json          # 唯一可编辑制作脚本
│   ├── config.json
│   ├── media/               # 分段录音、词时间、图片、视频、声音及来源
│   ├── media-plan.json / media-review.md
│   ├── review.json / state.json
│   ├── deliverables/        # 最终 MP4、字幕、封面与绑定本版成片的 QA
│   ├── build/               # 可重建母带、编排、抽帧、日志
│   └── .cache/              # 可删除的本地缓存；未知计费请求状态先保留核查
└── examples/
    └── competition-continuity/ # 最新连续场景样片，采用同样的剧集契约
```

约束：source/media 是输入，deliverables 是交付，build 是可再生成内容。代码仍允许把整个项目目录作为素材安全边界，但模板应把媒体放进 media。素材台账与运行清单继续分别管理，不能因迁移合并掉来源记录。

正式剧集不因日期早就判为垃圾。只有最新连续场景样片进入 examples；建议删除此前“表达样片”和“杂志拼贴样片”两套独立工程与旧成片，必要结论保留在 decisions，少量对照图保留在研究/设计证据中。此项尚未执行，随本方案确认，避免把仍需对照的作品当成缓存。

## 迁移映射与改动

| 当前位置 | 目标 |
|---|---|
| episodes/正式剧集/scripts、specs | 同剧集 source/scripts、source/planning，保留原稿内容 |
| episodes/正式剧集/production 下脚本、配置、媒体和审阅记录 | 提到该剧集根目录，移除 production 这一层 |
| production/build/recording-import 中录音和词时间 | 同剧集 media/recordings；更新 script.json 和导入工具 |
| production/build/output.mp4、captions.srt、qa.json | deliverables；保留原视频字节，QA 路径迁移记录另存，不冒充重渲染 |
| production/build 其他输出 | 复核引用后删除；需要时生成到新的 build |
| 最新连续场景样片 | examples/competition-continuity |
| 前两套风格样片 | 按上述建议删除，更新引用它们的当前说明 |
| docs 报告、证据、指南、实施记录 | 分到 research、guides、decisions，更新相对链接 |

同步更新 CLI、Pipeline 根路径、素材安全边界、导入脚本、测试调用和固定测试数据、skills 路径说明、README、AGENTS、.gitignore。保留原录音与不可重建的生成素材；先验证输入路径再删除旧中间产物。

新结构下运行状态需重新计算，旧状态不自动标为有效。恢复依赖后检查原稿与媒体哈希、全部脚本引用、validate/doctor、现有测试与缓存失效行为。若只迁移而不改视觉，不重做付费配音或图像；需要渲染验证时先使用最新样片。

## 审批记录

已获用户批准并实施：正式剧集保留输入与交付，最新样片进入 examples，删除两套旧风格工程。原视频未转码，旧 QA 原样保留，新的路径与验证结果单独记录。
