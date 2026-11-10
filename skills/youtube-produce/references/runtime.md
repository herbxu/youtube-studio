# 运行契约

正式作品在同级 `youtube/episodes/<ID>`；试剪样片在 `youtube-workbench/examples/<ID>`。文中的 `build/`、`.cache/`、`state.json` 和 `.run.lock` 均相对工作台 `runtime/episodes/<ID>/`（样片使用 `runtime/examples/<ID>/`）；`deliverables/` 相对剧集根。

## 安装与入口

从仓库根目录：

```bash
npm ci
python -m pip install -e .
youtube-studio init --episode <剧集目录> --title <标题>
youtube-studio doctor --episode <剧集目录>
youtube-studio review --episode <剧集目录>
youtube-studio run --episode <剧集目录>
youtube-studio status --episode <剧集目录>
youtube-studio resume --episode <剧集目录>
```

渲染会优先使用 render.browser 或 HYPERFRAMES_BROWSER_PATH，其次探测系统 Chrome/Chromium；找不到则明确阻塞，不在渲染阶段等待隐式浏览器下载。实际浏览器版本参与渲染缓存。HyperFrames 检查和渲染日志保存到 build/logs/。

当前 macOS Chrome 的长片导出曾出现底边白带，浏览器布局检查不能发现。生成器使用 1082px 的文档最小高度保留整页捕获，实际 composition 与导出裁切仍为 1920×1080。verify 会解码概念/文字镜头底部的纸色区域，发现颜色不符即拒绝交付；这项检查与当前模板配色绑定，调整底部设计时应同步更新。插画和全画幅 footage 不适用纸色边缘判断，仍需检查实际抽帧。

运行依赖 Python 3.10+（fcntl，macOS/Linux）、Node 22+、FFmpeg/ffprobe、HyperFrames 支持的本地浏览器。JS 精确版本在 package-lock.json；渲染不使用临时 npx latest，不在任务中途升级。字体随仓库提供，许可证为 resources/fonts/OFL.txt。

识别模型默认 base，`allow_download:false` 防止每次运行隐式下载大模型。首次需要下载时显式设 true，下载后可恢复 false。正式中文音频若识别错误多，使用合适的更大多语言模型或 command 对齐器，不能降低闸门掩盖关键错误。

## 文件职责

```text
<episode>/
  brief.json           # 用户方向、论点、来源摘录
  script.json          # 唯一可编辑的正文、读音展开、分镜、素材引用
  config.json          # 非敏感 provider 和风格配置
  media-plan.json      # agent 的需求、候选与使用计划，不是运行时执行配置
  media-review.md      # 素材检查范围与缺项
  review.json          # 本次导出的人工审阅记录，绑定 MP4 哈希
  media/               # 本地素材及 manifest.json 来源台账
  source/              # 原稿、策划与导入依据
  deliverables/        # final 成片、同步字幕与绑定本版的 QA
    output.mp4
    captions.srt
    qa.json

<workbench>/runtime/episodes/<ID>/
  .cache/              # 按内容寻址的配音/识别/插画/渲染结果与任务日志
  state.json           # 当前运行状态与输入指纹
  .run.lock            # 同一剧集正式与试剪共用
  build/               # 可重建中间文件；不存唯一输入
    editorial-review.json # 论证结构与人工待审项
    voice-review.json     # 识别差异，时间相对单元音频
    storyboard.md         # 根据实际音频生成的分镜阅读稿
    script.md
    voice.master.wav   # 人声母带
    audio.mixed.wav    # 配置 audio_tracks 时生成
    audio-mix.json     # 附加音轨落点、增益、混音结果
    timeline.json
    captions.srt       # 对齐阶段草稿；渲染成功时复制到交付目录
    assets.manifest.json
    composition/       # 独立 HyperFrames HTML 和实际用到的媒体
    preview/           # preview.mp4、captions.srt、qa.json；不覆盖正式交付
    frames/            # 从实际成片提取的镜头中点
```

`--episode` 直接指定剧集或 examples 样片根目录，不再追加 production。init 可在仅有 source 的目录内初始化，但已有 config/brief/script 或旧 production 时拒绝覆盖。只运行到 compose 不会修改已有 deliverables。

阶段是 script → voice → align → assets → compose → render → verify。`--through <阶段>` 停在所选阶段，并标记 prepared；`--mode preview` 允许 say。`run` 与 `resume` 都校验内容缓存，不盲信 state 中的 succeeded。status 对新输入显示 stale，旧成片不能当新结果交付。

没有 script.json 时，根据 brief 和作者契约调用 text provider；已有脚本绝不因 brief 修改被自动覆盖。要重写脚本由 youtube-write 显式修改，以防丢失用户编辑。

## 两种执行方式

**Agent 辅助自动化**：agent 完成研究、对象与动作规划、script.json、实际素材检索与检查，导入媒体后总控出片。必要插画才使用生图。工具不可用时准确说明缺口。

**无人值守执行**：已有可执行脚本、本地素材、录音或必要 provider、可用时间戳或对齐模型时，run 可执行生产阶段。没有 script.json 时可调用 text provider 起草，但生成字段仍须满足验证器与实际素材条件。程序不自动在线搜索实拍、音乐或事实证据；新方向的选材和复杂分镜仍由 agent 处理，不能承诺只给主题就无人值守完成研究、选材与审片。

内置 OpenAI 适配器：Chat Completions JSON 写稿、Speech WAV 配音、GPT Image PNG 生图。示例模型是配置示例，不代表当前最新或账号必然可用；可单独替换。接口依据：

- [Chat API](https://developers.openai.com/api/reference/resources/chat)
- [Speech API](https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create)
- [Image API](https://developers.openai.com/api/reference/resources/images/methods/generate)

只从 `key_env` 指定的环境变量读取密钥，不读取或输出用户其他凭证。内置适配器固定官方地址，不把密钥发往任意 base_url。429 最多重试 2 次；超时、5xx 等不确定状态不自动重发。`--retry-uncertain` 仅在核查上次调用结果后使用。

## command 适配器

支持已有的 TTS、图像和对齐服务，不绑定某个厂商。配置示例：

```json
{"provider":"command","argv":["/absolute/python","/absolute/adapter.py","--request","{request}","--output","{output}"],"timeout":300,"settings":{"voice":"your-voice"}}
```

运行程序写 request.json，将路径替换到 argv；不用 shell，不把正文拼成 shell 命令。适配器读取 JSON，写 output，成功退出 0。超时结果未知时遵守同样的防重复规则。模型、音色、服务版本应放 settings 以参与缓存；修改适配器也应更新 settings.version。

| task | 请求主要字段 | 输出 |
|---|---|---|
| draft | brief、instructions、settings | opinion-script/v1 JSON |
| speech | text、delivery、settings | 可解码 WAV |
| image | prompt、settings | PNG |
| transcribe | audio（绝对路径）、language、settings | `{"words":[{"text":"你好","start":0.1,"end":0.5}],"method":"真实方法"}` |

command provider 的 HTTP 行为、异步任务恢复、服务费用由该适配器负责。内置协议为同步，不承诺通用异步 job polling。按需新增有文档的供应商适配器。

## 缓存和验收边界

- voice 缓存只依赖实际朗读文本、表达意图、音色与供应商配置；镜头修改不影响配音。
- 识别依赖实际音频哈希，插画依赖提示词和模型配置。默认增量渲染按片段生成HTML及其引用素材、字体、浏览器和规格缓存；画面与音频分开缓存。实现与命令见 [快速预览指南](../../../docs/guides/fast-review-workflow.md)。monolithic兼容路径仍按整包和代码版本缓存。
- task.json 记录 running/succeeded/failed/uncertain。使用临时文件和原子替换；重跑校验结果文件哈希。单剧集文件锁防止并发写入。
- 当前自动检查包含结构、来源 ID、词时间戳、文字覆盖率、关键词、事件顺序、媒体存在/尺寸、HyperFrames 检查、音视频流和结尾时长漂移；实际 MP4 另查持续黑场、综合响度和真峰值。
- 当前不自动证明事实真实性、引用准确性、插画语义、音色自然程度；成片中点抽帧需实际查看，关键转场和数字变化需进一步抽查。
- 不存在“自动编辑审核已批准”的标签。无配音、无必需图片、锚点不匹配均失败；不会静音/空背景降级成正式成片。

## 录音导入与概念出场

可导入由实际音频强制对齐得到的词时间戳。必须记录对齐模型、参考文本来源和音频哈希；受文本约束的匹配率不等于独立转写准确率。不得用整段字数均分伪造时间戳。

已有准确原稿且独立识别出现同音字或数字格式差异时，可使用 `alignment.provider: "whisper-forced"`，配合本机已缓存的 `model: "small"` 和 `allow_download: false`。它先保留独立识别，再用 Whisper 注意力与 DTW 对齐原稿，记录真实测量词时间及音频哈希。当前每个语义单元须不超过29秒，过长则明确失败。覆盖率只验证参考文本与时间映射，不能证明音频读对了；`build/voice-review.json` 的 `independent_asr.differences` 必须另行审听，数字、否定词和金融术语尤其需要检查。不通过降低 `min_coverage` 掩盖识别或错读问题。

`comparison` 和 `flow` 可配置与 labels 等长的 `label_cues`，每条 cue 必须唯一且按朗读顺序出现于本镜头内；编排使用对齐后的绝对时间。`flow.layout: "parallel"` 去掉因果箭头，用于并列类别。脚本顶层 `overlays` 可指定 unit、text、duration，生成不朗读的短说明层。

## 风格配置与当前能力

封面创作要求见 [封面照片与频道标识](../../youtube-visuals/SKILL.md#封面照片与频道标识)：从脚本生成摄影式情境图，再独立叠加“面朝北北”原版logo。当前 `cover.asset/provenance` 接收已准备好的本地图片，并不会自行读脚本生成照片。现有 `config.style.branding` 可填写 `asset` 和 `provenance`，由编排器在右下角叠加logo，但当前作用于整段视频，不是仅封面的开关。仅封面品牌需求应在封面合成/导出范围内实现，不能把全片品牌配置描述成已具备封面专用时段控制。最终以实际导出的封面核验。

本期新增 `style.chapter_navigation: true`：从 `narrative.chapters` 的连续 units 与最终音频时长生成顶部导航。章节可提供8字以内的 `nav_label`；每段宽度与实际时长成比例，进度线随时间推进，过窄则明确失败，不强行挤入文字。导航页输出为 deliverables/navigation.html，按钮跳转同目录成片的真实章节时间；chapters.json 保存精确秒数。

`cover` 镜头使用本地 asset/provenance、10字符内 headline（含换行）、可省略的24字内 subtitle，生成全幅照片标题页，不在封面叠放章节目录。headline 支持1–2个非空行；subtitle 缺省、空串或仅空白时不生成副标题容器、装饰线或动画；有副标题时，手动换行后副标题随实际行数下移，仍需用最终照片检查两行标题与主体是否相撞。它与其他镜头一样由口播 cue 决定起止，不额外插入静音。顶部章节导航从开场封面结束后显示。verify 从封面内实测字幕间隙导出不带口播字幕的 navigation.png 与 cover.png，供导航页作封面；没有足够间隙时明确失败。图片负责情境，真实公告继续使用 evidence 模板。

镜头可设置 `show_note: false`，移除通用底部说明文字、对象场景的 note，以及 quantity 自动生成的“假设示例”标签；note 与 hypothetical 仍保留在脚本中供编辑核对。真实来源 credit、正文字幕与解释结论保持各自职责。画面应优先表达观点，不机械堆放“概念示意”等制作标签。

本期字幕采用 `captions.punctuation: "none"`：编排时移除字幕显示文本的句间、句末标点，同时写入SRT；原稿、配音文本和实测时间不变。小数、数字比例及日期中的必要分隔符保留，避免改变数值含义。画面大字的文字在 script.json 中编辑，分组标题仍须完整拼回 headline。导航使用浅暖底色和金棕进度线，与正文纸色协调。

创作优先采用对象与动作规划。init 的 style.id 默认为 opinion-explainer/v1；连续街区样片显式使用 continuous-explainer/v1。技能规则不会自动改写已有 config.json，制作时需按选用模板设置本剧集配置；旧插画配置继续兼容。collage 与 mechanism 的字段见作者契约。collage 只接受本地位图，secondary_asset 也参与来源校验、内容哈希和媒体冻结；mechanism 是定性示意，不提供真实数值输入。两种新模板应搭配 editorial-magazine/v1。另提供 footage 与跨单元的 continuity 模板。footage 使用本地视频裁切、去除源声音并按实测时长渲染；continuity 当前限 shop-competition/v1 的有序动作。单元 audio_tracks 接入本地 SFX/BGM 混音及人声侧链压低。素材搜集仍由 agent 执行，不是无人值守程序阶段。
