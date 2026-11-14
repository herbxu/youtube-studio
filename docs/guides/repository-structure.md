# 作品与制作工具

| 位置 | 用途 |
|---|---|
| 作品库的 脚本/、知识/ | Git 跟踪口播原文、基于原稿的知识与来源链接。知识页可以引用多期判断 |
| 作品库的 上传成品/ | Git 忽略。每期一个目录，作者按期备份到网盘 |
| 源码库 src/youtube_studio/、config/、resources/ | Python 命令、制作程序、默认配置、字体、品牌与可再用的资源 |
| 源码库 examples/offline/、tests/ | 离线制作样例、单元测试、画面验证 |
| 源码库 skills/、docs/ | 制作方法、技术说明与历史证据 |
| --assets 指定的目录 | 每期私有素材、原始录音、来源记录、可选分镜及 request-cache/ |
| YOUTUBE_STUDIO_CACHE | 本机工作目录，保存构建、运行锁、任务状态和缓存 |

正常制作显式传入 --script、--destination，按需传入 --assets。高级工程可直接传给 --episode。旧三仓布局仅用于回退或读取历史记录；兼容模式通过 YOUTUBE_WORKS_ROOT 和 YOUTUBE_WORKBENCH_ROOT 显式启用。新机器无需复制旧工作台。依赖安装与离线渲染命令见[使用说明](../../README.md)。
