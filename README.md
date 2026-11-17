# 观点视频工作室

把一份 Markdown 讲稿制作成正片、封面、字幕和上传文案。可以在任意目录克隆源码；作品、私有素材和输出位置由命令参数指定。

## 安装与离线验收

环境需要 Python 3.10–3.13、Node 22 或以上、FFmpeg（含 ffprobe）以及 Chrome 或 Chromium。实际验收环境为 macOS、Python 3.13、Node 25。Linux 的浏览器可执行文件可通过 HYPERFRAMES_BROWSER_PATH 指定。当前进程锁使用 POSIX flock。

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
npm ci
youtube-studio check-workspace
youtube-studio produce --technical-preview --script examples/offline/script.md --assets examples/offline/assets --destination ./build/offline-upload
```

安装依赖后，随库的短样例使用预录测试语音和时间戳；制作期间无需云端密钥、识别模型或另一个仓库。命令返回私有候选和审阅记录的路径。正式交付目录须为新目录。进一步验证可执行 `python -m unittest discover -s tests -v`。

## 制作与备份

```sh
youtube-studio produce --script "/path/to/作品/脚本/本期.md" --assets "/path/to/私有素材/本期" --destination "/path/to/作品/上传成品/本期"
youtube-studio deliver --source "/path/to/produce返回的round目录"
youtube-studio export-upload --source "/path/to/作品/上传成品" --destination "/path/to/备份/面朝北北-最终上传物-$(date +%Y%m%d)"
```

制作时可重复指定 `--goal "本期可观察的验收目标"`。每次导出先生成待审候选。制作助手连续听看、记录问题、针对原因修复，再运行同一制作命令。在新版记录逐项目标和复测依据后，deliver 才写入六件套。自定义编排产生的私有六件套通过 register-cut 接入相同流程。字段、退出状态和返工步骤见[质量验收](skills/youtube-produce/references/quality.md#当期成片的自审返工和交付)。

正式配音前使用 `review --script 本期.md --init-review` 建立同名审稿表，填写逐段证据后再制作。历史脚本另存修订稿。已编排的多章片用 `rsi --script 本期.md --source 私有六件 --destination 新交付目录 --av-manifest 清单.json --repair-with 本期修复程序` 自动验收、返工、复验。

录音前可用 `youtube-studio review --script "/path/to/本期.md"` 校对段数和中文口播预计时长。命令与制作共用正文解析，每个汉字、英文词或数字各计一个单位，按每分钟 250 个单位粗估。章节、引用块和注释不计时，停顿及英文读法以录音为准。

讲稿用一级标题和空行分段。独立标题、引用块和 HTML 注释用于非口播说明。纯文本模式按段生成基础分镜。每段可以提供 001.wav、001.words.json 等录音和时间戳，详见 examples/offline。频道默认用阿里云 TTS 生成正文，本机已选模型、voice_id 和表达指令保存在 Git 忽略的 config/channel-voice.local.json（顶层 settings，可选 base_url）。密钥从环境变量或 .env.local 读取。本期显式提供的 config.json 优先；缺时间戳时按 alignment 配置识别。默认识别模型需预先安装，云服务凭证通过环境变量配置。

私有素材包可带 config.json，以及带有原分镜的 script.json。正文逐段匹配后复用分镜和相对路径素材；改稿后同步对应分镜、配音和字音时间。可附一张独立封面（cover.jpg、cover.jpeg 或 cover.png），以及标题.txt、简介.txt、标签.txt。无单独文案时使用讲稿标题和首段，缺标签时取发布标题的主题部分。手动上传每期一个「日期-选题」目录，只交付六个文件：正片.mp4、封面.jpg、中文字幕.zh-Hans.srt、标题.txt、简介.txt、标签.txt。独立备份的上层目录用「面朝北北-最终上传物-YYYYMMDD」，日期取实际备份日。复杂投资选题沿用已审阅的图片、数据、分镜和声音。私有 request-cache/ 可复用同键同哈希的服务结果及未决记录。历史缓存键变更或缺失时，执行前核对原请求记录、模型与凭证。

本地过程目录默认在 ~/.cache/youtube-studio/projects/，可设置 YOUTUBE_STUDIO_CACHE。凭证、私有素材和运行缓存随机器单独管理。每次验收记录覆盖的实际片段，发布由作者手动执行。

## 工程入口

- [目录契约](docs/guides/repository-structure.md)说明源码、作品和私有素材如何分工。
- [制作流程](skills/youtube-produce/SKILL.md)串联写作、配音、素材、视觉与交付。
- [快速试剪](docs/guides/fast-review-workflow.md)介绍高级 JSON 工程的预览和增量合成。原有 init、doctor、validate、run、resume、preview、sample 命令仍接受显式 --episode。
- [历史决策](docs/decisions)保留当时的目录与验收记录。
