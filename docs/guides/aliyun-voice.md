# 阿里云音色与配音接入

使用本机 `.env.local` 保存 `ALIYUN_TTS_API_KEY=实际密钥`。CLI 只读取白名单变量，不执行 shell，不打印密钥；已有进程环境变量优先，也兼容官方示例的 DASHSCOPE_API_KEY。文件受 Git 忽略，建议权限600。

本期采用用户提供的北京接入地址 https://cn-beijing.maas.qianwenaiapi.com/api/v1。配置中的 base_url 优先于 ALIYUN_TTS_BASE_URL；不会从密钥推测域名。程序限制带凭证的请求使用受支持的官方域名，并禁止重定向。

```json
{"provider":"aliyun","key_env":"ALIYUN_TTS_API_KEY",
 "base_url":"https://cn-beijing.maas.qianwenaiapi.com/api/v1",
 "timeout":180,"requires_custom_voice":true,"voice_verified":false,
 "reference_audio":"media/voice-reference/author.mp3","reference_sha256":"原音频哈希",
 "settings":{"service":"aliyun-bailian","model":"cosyvoice-v3.5-plus",
 "voice_id":null,"instruction":"自然解释，平静，转折稍停顿。"}}
```

当前适配器按官方 HTTP 协议创建/查询音色、合成 WAV。音色绑定 target_model，切换到 Qwen-Audio 时需要为对应模型创建音色，不能直接沿用 CosyVoice 的 ID。表达指令采用 settings.instruction，当前不会自动把每个 unit.delivery 转换成供应商指令。

## 操作顺序

在已安装依赖的仓库中，将以下 `<剧集>` 替换为剧集根目录。

```bash
python -m youtube_studio.aliyun_voice check --episode <剧集>
python -m youtube_studio.aliyun_voice enroll --episode <剧集> --reference media/voice-reference/clone-reference.wav
python -m youtube_studio.aliyun_voice query --episode <剧集>
python -m youtube_studio.aliyun_voice sample --episode <剧集>
```

check 通过列表查询验证连接，不证明目标模型可合成。enroll 上传用户授权的音色片段，创建结果写 source/aliyun-voice.json；query 返回 OK 后再合成。sample 使用当前 script.json 前两个单元生成样音（--units 1 可只用第一段），写 media/voice-samples 和 source/aliyun-sample.json，保持 listening=pending。样音是首次风格验证，正式分段配音另按流水线缓存生成。

先选择10–20秒清晰完整句群，保留原录音和裁切来源。当前适配器允许10–60秒、10MB以内、至少16kHz的WAV/MP3/M4A。settings.max_prompt_audio_length 控制实际使用的参考长度（3–30秒，默认10），因此上传更长文件不等于模型会使用全部内容。Base64直接提交，无需把用户声音放到公开对象存储。参考片段质量仍需听审，自动转写不能证明音色或噪声合格。

确认样音后，将返回的 ID 填入 voice.settings.voice_id，并把实际审听结果记入 source/voice-profile.json；审听通过才设置 voice_verified=true。随后使用正常 `youtube-studio run` 完成分段配音、实测对齐与视频。示例不自动标记听审通过。

## 请求与缓存

创建和样音使用现有任务缓存及剧集锁；按模型、接入地址、音频/正文和配置哈希复用成功结果。POST 不自动重试。超时、5xx或缺失结果保持 uncertain，核查服务记录后才能显式使用 --retry-uncertain。收到 voice_id 后先保存再查询，避免查询中断导致重新创建。合成响应先保存到本机缓存，再下载媒体；同一请求恢复时可复用响应。阿里 OSS 返回的 HTTP 媒体链接会改为 HTTPS 下载。媒体下载不携带 API 密钥。

未配置服务或音色时不会换用系统音色。实际可用性、用量和费用以账号与服务端返回为准。

官方参考：[声音复刻 HTTP API](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api)、[非实时语音合成](https://help.aliyun.com/zh/model-studio/non-realtime-tts-user-guide)。
