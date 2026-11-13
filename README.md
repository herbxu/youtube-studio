# 观点视频工作室

正式作品在同级 `youtube/episodes/<ID>`；试剪样片在 `youtube-workbench/examples/<ID>`。文中的 `build/`、`.cache/`、`state.json` 和 `.run.lock` 均相对工作台 `runtime/episodes/<ID>/`（样片使用 `runtime/examples/<ID>/`）；`deliverables/` 相对剧集根。

本地视频制作项目，默认形式为 **观点口播 + 财经杂志式摄影拼贴 + 动态图解 + 短句观点**。

流程：脚本 → 配音或录音导入 → 时间对齐 → 素材 → HyperFrames 编排 → MP4 → 检查。可以通过命令行直接使用，也可以通过通用 skills 协助研究、写稿和制作。

## 目录结构

```text
.
├── AGENTS.md            # 通用项目协作约定
├── src/youtube_studio/   # Python 源码、CLI、生产流水线
├── tests/               # 单元测试、集成验证与测试数据
├── config/              # 默认非敏感配置
├── resources/           # 字体、许可证及可复用素材索引
├── skills/              # 通用工作流说明及配套参考文档
├── ../youtube/episodes/            # 正式剧集：原稿、制作输入与最终交付
├── ../youtube-workbench/examples/            # 保留的连续场景样片
├── docs/                # guides / research / decisions
├── build/               # 测试运行时生成，可清理，不纳入版本控制
├── pyproject.toml       # Python 包配置和 youtube-studio 命令入口
├── requirements.txt     # 固定版本的 Python 运行依赖
├── package.json         # 固定版本的 JavaScript 渲染依赖
└── package-lock.json    # JavaScript 依赖锁文件
```

目录职责、迁移说明和临时文件清理规则见 [仓库结构](docs/guides/repository-structure.md)。工具协作约定见 [AGENTS.md](AGENTS.md)，博主参考分析见 [文档目录](docs/README.md)。

## 安装

需要 Python 3.10+、Node 22+、FFmpeg/ffprobe 和本地 Chrome/Chromium。当前支持 macOS/Linux。

这是依赖仓库内配置、字体和渲染工具的本地应用，使用源码可编辑安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
npm ci
```

## 使用

```bash
youtube-studio init --episode ../youtube/episodes/my-video --title '视频标题'
```

填写 `brief.json`，准备 `script.json`，并在 `config.json` 配置实际可用的服务。默认配置来自 [config/default.json](config/default.json)，服务凭证只通过指定的环境变量读取。

```bash
youtube-studio validate --episode ../youtube/episodes/my-video
youtube-studio review --episode ../youtube/episodes/my-video
youtube-studio quality --episode ../youtube/episodes/my-video
youtube-studio doctor --episode ../youtube/episodes/my-video
youtube-studio run --episode ../youtube/episodes/my-video
youtube-studio status --episode ../youtube/episodes/my-video
youtube-studio resume --episode ../youtube/episodes/my-video
```

也可以用 `python -m youtube_studio` 调用同一入口。`run` 和 `resume` 都复用经过文件哈希校验的缓存；仅生成时间线和 HTML 时增加 `--through compose`。临时配音验证需明确使用 `--mode preview`。

唯一编辑源是 `script.json`，正文、读音展开、分镜和素材引用都在这里。原稿与策划放 `source/`，录音与素材放 `media/`；阅读稿、对齐字幕草稿、时间线、母带和 HTML 写入 `build/`，正式成片、同步字幕和 QA 写入 `deliverables/`。preview 交付写入 `build/preview/`。只编排不会覆盖已有成片或交付字幕。不要把历史 aligned 文件当作当前原稿。

新稿围绕一个主问题填写 `editorial` 和逐段 `argument`，再决定画面如何帮助理解。已有录音优先导入，TTS 按完整语义段生成。流程会输出论证检查 `editorial-review.json`、录音差异 `voice-review.json` 和实测分镜 `storyboard.md`；机器检查不会代替听审、事实核验与真实导出画面检查。

快速修改默认使用：`preview` 浏览器看全片 → `sample --shot <镜头ID>` 或 `sample --start <秒> --end <秒>` 查看改动 → `run` 增量合成。具体操作和缓存失效边界见 [快速预览与增量合成](docs/guides/fast-review-workflow.md)。

完整配置和缓存协议见 [运行契约](skills/youtube-produce/references/runtime.md)。

新稿可用 `narrative` 规划观众原有判断、观点变化和章节推进；画面支持真实资料高亮 `evidence`、保持对象身份的情境变化与关系展开 `object_scene`。字段及边界见 [动态图解契约](skills/youtube-visuals/references/explain-scenes.md)。素材索引支持本地搜索、完整性检查和冻结到本期：

```bash
python -m youtube_studio.library search --query '公司 融资'
python -m youtube_studio.library check
python -m youtube_studio.library freeze --id <素材ID> --episode ../youtube/episodes/my-video
```

在线选材仍由工作流执行。自定义音色需要实际服务、音色 ID 和样本听审；项目未附带云端服务账户。参考录音不会自动成为本期旁白。

阿里云配音支持从本机 `.env.local` 读取密钥，创建自有音色并生成中文样音，见 [阿里云配音配置](docs/guides/aliyun-voice.md)。现有账户可直接接入，无需部署本地克隆模型。

## 工作流

| Skill | 职责 |
|---|---|
| [youtube-produce](skills/youtube-produce/SKILL.md) | 总控、能力检查、缓存、恢复与交付 |
| [youtube-write](skills/youtube-write/SKILL.md) | 研究、观点、口播、语义分镜与来源 |
| [youtube-voice](skills/youtube-voice/SKILL.md) | TTS、录音导入、时间戳、字幕和母带 |
| [youtube-media](skills/youtube-media/SKILL.md) | 按分镜搜集图片、视频、音效、BGM，检查来源并登记使用计划 |
| [youtube-visuals](skills/youtube-visuals/SKILL.md) | 摄影拼贴、机制动画、语义分镜与画面验收 |

Skills 是仓库内的通用流程文档，不包含生产程序，也不要求使用特定助手客户端。实际程序统一位于 `src/youtube_studio/`。

## 验证

激活虚拟环境后：

```bash
python -m unittest discover -s tests -v
```

可选的 macOS 实际集成验证：

```bash
python tests/smoke_studio.py --through compose
python tests/smoke_studio.py
```

它使用本地 say、已缓存的中文识别模型和测试图案，输出到 `build/smoke/build/`。用于验证流程，不代表正式配音或插画质量。

已有编排工程可运行浏览器回归检查，验证流程节点与箭头按口播出现、倒序拖动可恢复、字幕文字在安全区内：

```bash
python -m youtube_studio run --episode ../youtube-workbench/examples/competition-continuity --through compose
node tests/check_composition.cjs ../youtube-workbench/examples/competition-continuity
```

当前样片：[连续场景源稿](../youtube-workbench/examples/competition-continuity/script.json) · [35.76 秒成片](../youtube-workbench/examples/competition-continuity/deliverables/output.mp4)。它复用作者录音并接入实拍、连续对象动画和音效。完整《竞争优势》位于 [正式剧集](../youtube/episodes/20260829-竞争优势/script.json)。

两套旧风格样片工程已按用户批准删除，结论及少量对照图保存在 docs/decisions。当前 CLI 直接使用 `--episode` 指定目录；仅有原稿的历史剧集可在该目录初始化，已有制作文件不会被覆盖。

## 工作约定

- 不自动上传、发布或提交 Git；保留历史剧集的原始内容与素材。
- 默认不下载识别模型；只有显式开启配置才下载。
- 缺少正式配音、必要图片或可靠时间戳时明确停止，不用静音或空画面代替。
- 机器检查不等于事实核验或视觉审阅，交付时分别说明实际验证范围。
- 研究和事实核验由写作流程完成；无人值守程序仅使用已提供的来源内容。

连续场景与实拍样片见 [实施记录](docs/decisions/continuous-scene-implementation-2026-10-24.md)：本地视频裁切、跨口播单元的对象动画、SFX/BGM 混音与人声侧链压低。素材检索仍由 skill 编排执行。

2026-10-24：已完成目录迁移和旧工程清理，详见 [实施方案](docs/decisions/directory-plan-2026-10-24.md) 与 [迁移清单](docs/decisions/layout-migration-2026-10-24.json)。历史 QA 和人工审阅保留原记录，不代表新结构下重新渲染或听审。

目录迁移时曾清理可重装依赖；本轮功能验证已重新安装 `.venv/` 和 `node_modules/`，均受 Git 忽略。迁移记录见 [目录迁移验证](docs/decisions/layout-validation-2026-10-24.json)，本轮能力、验证及配音缺项见 [Skills 改进实施记录](docs/decisions/skills-improvement-2026-10-24.md)。

三仓检查：运行 `.venv/bin/youtube-studio check-workspace`；加 `--episode ../youtube/episodes/<ID>` 可核对该期正在使用的素材。缺仓库、LFS 指针未展开、缺文件、无效路径将列在 issues 并返回非零。研究出处使用 `repo:trade/<相对路径>`，指向可选的独立研究仓库，不是渲染输入。历史报告保留原值，迁移路径见 [路径清单](docs/decisions/three-repositories-2026-11-10.json)。

交付检查会重算成片、发布文件、选版证据和 QA 的 SHA256。status 单列 archived_delivery 与当前输入的运行状态。工作区有未提交制作代码时，正式交付会保存 Python 源码和依赖清单的私有工作台快照。
