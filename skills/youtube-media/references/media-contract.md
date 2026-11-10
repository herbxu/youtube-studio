# 素材计划、台账与可用能力

## 文件职责

- media-plan.json：选择需求、候选、使用计划与缺口，可编辑。
- media/manifest.json：已获取文件及来源/检查记录；没有文件的候选不得登记为已下载。
- media-review.md：本次选择理由、实际检查范围和待接入项。
- build/assets.manifest.json：现有流水线生成的视觉素材编排清单，不能用新台账覆盖它。

## 计划格式

```json
{
  "schema": "opinion-media-plan/v1",
  "requests": [
    {
      "id": "m-entry",
      "shot_id": "s-entry-photo",
      "type": "video",
      "purpose": "让观众看到一家店营业，作为新店进入前的状态",
      "subject": "街边小店",
      "action": "推门、顾客进出",
      "queries": ["街边小店 开门 顾客", "small shop entrance customers entering"],
      "usage": "illustrative",
      "cue": "别人能不能在你隔壁",
      "duration_s": null,
      "status": "planned",
      "selected_asset_id": null,
      "render_status": "unsupported"
    }
  ]
}
```

type 为 image / video / sfx / bgm。usage 为 illustrative / evidence；evidence 必须关联 script.sources 的 source_ids，并检查实体、事件与日期。status 为 planned / searching / selected / acquired / inspected / blocked；render_status 为 unbound / bound / unsupported。绑定素材只有在生成器确实能消费这些字段时才能设为 bound。

候选保存在对应 request.candidates，记录 source_url、preview_url（若有）、作者/许可待核实项、selected 布尔和 reason。不要求每项机械搜满固定数量；素材语义不合适时继续搜或标记缺口。

BGM 请求另写 mood、density、vocal=false、bpm_range（可空）；选中音乐登记 bpm.value、bpm.method=provider/measured/estimated/unknown。未知值用 null，未检测到不能当作 0 BPM。节拍需要准确同步时再进行实际分析，保留工具与置信度；不从文件名猜值。

SFX 的 placement 为 unit_id + cue + offset_s；BGM 记录 intended_gain_db、fade 和 ducking 意图。它们是编辑计划；执行时需明确回填单元 audio_tracks，不能只写在 media-plan.json。

## 台账最小字段

每个 assets 项包含 id、type、path（相对剧集根目录）、sha256、source_url、author、license_name、license_url、retrieved_at、usage、attribution、inspection、bindings。用户自有素材可使用提供记录替代网页来源，不能凭“用户提供”自动认定所有版权归用户。

视频与音频加 duration_s；视频/图片加 width、height。视频区间使用 source_in_s、source_out_s，并检查是否越界；音乐与音效不能只保存试听网页。inspection 分开记录 frames_reviewed、continuous_playback、listened、technical_probe；分别使用 passed / pending / failed，不用一个总通过掩盖未听审。

## 环境中的 media-use

从当前会话 skill 目录定位其真实路径，不把个人绝对路径写死到本仓库。读过对应参考后运行：

```bash
node <MEDIA_USE_DIR>/scripts/resolve.mjs --doctor
node <MEDIA_USE_DIR>/scripts/resolve.mjs --type image --intent "small shop entrance" --project <episode> --candidates
node <MEDIA_USE_DIR>/scripts/resolve.mjs --type image --intent "small shop entrance" --project <episode>
node <MEDIA_USE_DIR>/scripts/resolve.mjs --type sfx --intent "short soft shop door bell" --project <episode>
node <MEDIA_USE_DIR>/scripts/resolve.mjs --type bgm --intent "restrained instrumental underscore, sparse arrangement, no vocals" --project <episode>
```

命令只是示例，需使用真实分镜意图。resolve 返回的文件和 ledger 要核实、登记后才能回填。它可能把文件放在 .media 下；若复制到本仓库 media/，保留来源、哈希和原路径，不误清理缓存。

本机检查与服务安装不等价。现有 media-use 提供图片/音乐/音效的检索入口，但依赖外部 provider；实拍视频检索不属于其当前 resolve 类型表，不能未经验证调用 `--type video` 并宣称等价。不要默认运行会生成新旁白的 audio engine；已有作者录音时只处理需要的音乐和音效。

## 当前渲染边界

- 本地照片：可用现有 collage / illustration 进入生产流程。
- 视频片段：footage 已支持本地视频、source_in、实测镜头时长裁切、focus 裁切、去除源声音及 HyperFrames 解码。超出素材长度会失败，不自动循环。
- BGM/SFX：单元 audio_tracks 支持真实 cue 定位、source_in/duration、gain_db、fade 和 duck；资产阶段生成 audio.mixed.wav，作者母带另存。两个 SFX 已进入实际样片；BGM 侧链压低通过信号测试，尚未选曲听审。
- BPM：是选曲/节拍信息，不是媒体类型，也不表示已具备自动踩点剪辑。

交付明确区分 skill 已建立、素材已获取、轨道已接入、实际成片已验证四种状态。缺少凭证时保留精确缺项，不能把流程文档称为端到端自动化已经完成。
