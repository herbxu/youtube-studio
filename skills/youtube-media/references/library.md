# 可复用素材库

索引：resources/media/index.json。执行入口是生产程序，不在 skill 内复制实现：

```bash
python -m youtube_studio.library search --query '咖啡 服务'
python -m youtube_studio.library check
python -m youtube_studio.library add --record /absolute/record.json
python -m youtube_studio.library freeze --id cafe-service --episode <episode>
```

记录包含 id、type、path（仓库相对路径）、sha256、subject、action、environment、usage、license_name、source_url/用户提供依据、recovery。可加 tags、作者、许可页、可用区间、裁切限制和已用剧集。add 从实际文件计算哈希，拒绝已有 ID；更新须重新检查用途和许可后编辑索引。search 是本地关键词匹配，不宣称在线语义检索。

check 区分 ready、missing、changed。missing 使用 recovery 指定的原始提供位置或来源页恢复；changed 必须核对新文件，不能直接更新哈希掩盖变化。不自动绕过登录或下载权限。

freeze 校验哈希并复制到本期 media/library，同时输出 media/library-manifest.json；同名不同内容拒绝覆盖。它不会自动把素材绑定到镜头，回填 script.json 后再验证。冻结成功只证明字节完整，本期语义、裁切与听审仍待检查。

视频和图片全局 Git 忽略；音色参考不上传仓库，不把其声音作为公开视频素材复用。索引记录复用权利和用途；不能把下载成功当许可充分。先用已有资产建立小库，再按真实制作需求补充。
