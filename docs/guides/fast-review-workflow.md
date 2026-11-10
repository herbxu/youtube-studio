# 快速预览与增量合成

正式作品在同级 `youtube/episodes/<ID>`；试剪样片在 `youtube-workbench/examples/<ID>`。文中的 `build/`、`.cache/`、`state.json` 和 `.run.lock` 均相对工作台 `runtime/episodes/<ID>/`（样片使用 `runtime/examples/<ID>/`）；`deliverables/` 相对剧集根。

以 script.json 为唯一编辑源。脚本和配音听审完成后，先通过浏览器看全片，收集修改；只导出修改片段检查，再更新受影响的正式镜头，合成并验收。以下命令从仓库根目录执行，示例剧集可替换。

## 1. 脚本与配音

```bash
.venv/bin/python -m youtube_studio run --episode ../youtube/episodes/20260913-企业再融资-增发和发债 --through align
```

阅读 build/script.md，试听 build/voice.master.wav，检查 build/voice-review.json。作者确认是人工步骤，程序不会把生成成功标记为声音已批准。修改原稿用 script.json；改口播会重做相应单元声音与对齐，可能移动后续镜头、字幕和导航。已授权的正常流程无需反复请求批准。

## 2. 浏览器看全片

```bash
.venv/bin/python -m youtube_studio preview --episode ../youtube/episodes/20260913-企业再融资-增发和发债 --port 3017
```

命令生成编排、执行 HyperFrames check，再在后台启动本地 Studio；以命令返回的 studioUrl 为准（默认端口3017）。修改 script.json 后，在另一个终端运行 `run --through compose`，Studio 重新加载生成结果。浏览器播放不生成 MP4。不要直接把 Studio 对派生 HTML 的手改当作源文件修改；需要回写 script.json 或生成程序。关闭服务使用同一条 preview 命令加 `--stop`。

## 3. 只预览修改片段

```bash
.venv/bin/python -m youtube_studio sample --episode ../youtube/episodes/20260913-企业再融资-增发和发债 --shot s-debt
.venv/bin/python -m youtube_studio sample --episode ../youtube/episodes/20260913-企业再融资-增发和发债 --start 38.8 --end 42.8
```

`--shot` 包含镜头前后各0.6秒用于检查衔接；时间范围使用全片秒数，程序按帧边界裁切。输出 build/preview/preview.mp4、同步裁切的 captions.srt 和局部 qa.json。默认1280×720、30fps；可设置 render.preview_fps 为15用于粗看，动画验收使用30fps。无选区的 sample 生成全片低分辨率预览。预览不会覆盖 deliverables。

## 4. 更新正式镜头与合成

```bash
.venv/bin/python -m youtube_studio run --episode ../youtube/episodes/20260913-企业再融资-增发和发债
```

默认 render.strategy 为 incremental，可显式使用 monolithic 保留整片渲染路径。正式镜头固定1080p，帧率使用 render.fps（默认30）。所有片段以同一全局帧网格划分、校验帧数，然后无损拼接视频流；音频另行编码和封装。

- .cache/visual-segment：无声画面片段，键包含生成HTML、实际引用素材、字体、浏览器版本、依赖锁和输出规格。
- .cache/visual-join：按顺序无损拼接的画面母版。
- .cache/av-mux：画面与独立声音母带合成。音频改动且时间轴不变时，复用全部画面。
- build/render-plan.json：本次正式片段命中、失效、耗时、帧区间；build/preview-plan.json 对应预览。
- build/visual-qa.json：绑定画面哈希与抽帧文件哈希的验收证据。画面和取样时间不变且文件完整时复用，音频响度和解码仍检查当前成片。

首次必须建立正式画面缓存，增加分段启动和检查成本，不承诺比整片首轮更快。预览与正式规格不同，不直接把720p预览当1080p缓存。文字/配图修改会使本镜头及包含其转场的相邻片段失效；跨镜头连续对象保留整个场景状态。修改章节时长、导航文字或全局样式可能影响多个乃至全部片段。只有时间轴不变的配乐/音量调整能完全跳过画面渲染。

## 验收边界

正式交付仍执行声音存在、尺寸、时长差、响度、真峰值、持续黑场、纸色边缘和关键抽帧检查。缓存不能代替主观听审与连续观看。局部预览的 qa.json 明确标记 preview 和全片区间，不冒充全片验收。

state.json 每阶段记录 seconds；render-plan.json 记录片段和合成耗时。评估速度应分别比较首次构建、局部修改、纯音频修改和无变化重跑，不能只报告最后封装的耗时。
