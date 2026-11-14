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
youtube-studio produce --script examples/offline/script.md --assets examples/offline/assets --destination ./build/offline-upload
```

安装依赖后，随库的短样例使用预录测试语音和时间戳；制作期间无需云端密钥、识别模型或另一个仓库。输出目录须为新目录。进一步验证可执行 `python -m unittest discover -s tests -v`。

## 制作与备份

```sh
youtube-studio produce --script "/path/to/作品/脚本/本期.md" --assets "/path/to/私有素材/本期" --destination "/path/to/作品/上传成品/本期"
youtube-studio export-upload --source "/path/to/作品/上传成品" --destination "/path/to/新备份"
```

讲稿用一级标题和空行分段。独立标题、引用块和 HTML 注释用于非口播说明。纯文本模式按段生成基础分镜。每段可以提供 001.wav、001.words.json 等录音和时间戳，详见 examples/offline。没有录音时按 config.json 的 voice 配置生成；缺时间戳时按 alignment 配置识别。默认识别模型需预先安装，云服务凭证通过环境变量配置。

私有素材包可带 config.json，以及带有原分镜的 script.json。正文逐段匹配后复用分镜和相对路径素材；改稿后同步对应分镜、配音和字音时间。可附独立 cover.png、标题.txt、简介.txt、标签.txt 和置顶评论.txt。无单独文案时以讲稿标题、首段作标题与简介。复杂投资选题沿用已审阅的图片、数据、分镜和声音。私有 request-cache/ 可复用同键同哈希的服务结果及未决记录。历史缓存键变更或缺失时，执行前核对原请求记录、模型与凭证。

本地过程目录默认在 ~/.cache/youtube-studio/projects/，可设置 YOUTUBE_STUDIO_CACHE。凭证、私有素材和运行缓存随机器单独管理。每次验收记录覆盖的实际片段，发布由作者手动执行。

## 工程入口

- [目录契约](docs/guides/repository-structure.md)说明源码、作品和私有素材如何分工。
- [制作流程](skills/youtube-produce/SKILL.md)串联写作、配音、素材、视觉与交付。
- [快速试剪](docs/guides/fast-review-workflow.md)介绍高级 JSON 工程的预览和增量合成。原有 init、doctor、validate、run、resume、preview、sample 命令仍接受显式 --episode。
- [历史决策](docs/decisions)保留当时的目录与验收记录。
