import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from youtube_studio.core import Blocked, Cache
from youtube_studio.portable import narration, review_markdown
from youtube_studio.upload_backup import export_backup


class Portable(unittest.TestCase):
    def test_markdown_omits_nonspoken_headings_and_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp)/"s.md"
            script.write_text("# 标题\n\n## 章节\n\n<!-- 灯光 -->\n\n**第一段**。\n\n> 说明\n\n第二段。")
            self.assertEqual(narration(script), ("标题", ["第一段。", "第二段。"]))

    def test_markdown_review_counts_only_spoken_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp)/"input.md"
            script.write_text("# 题目\n\n> 备注与链接\n\n## 开场\n\n微软 Claude。\n\n收入 2.5 亿。")
            result = review_markdown(script)
            self.assertEqual(result["paragraphs"], 2)
            self.assertEqual(result["spoken_units"], 7)
            self.assertEqual(result["estimated_seconds"], 2)

    def test_unresolved_request_in_private_pack_blocks_paid_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            prior = Path(tmp)/"prior"
            with self.assertRaises(RuntimeError):
                Cache(prior).task("speech", {}, ".wav", Mock(side_effect=RuntimeError), paid=True)
            action = Mock()
            with self.assertRaises(Blocked):
                Cache(Path(tmp)/"empty", prior_root=prior).task("speech", {}, ".wav", action, paid=True)
            action.assert_not_called()

    def test_export_old_upload_package_as_six_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root/"source"/"20260101-示例"
            package.mkdir(parents=True)
            for name in ["正片.mp4", "中文字幕.zh-Hans.srt", "简介.txt", "置顶评论.txt"]:
                (package/name).write_text("保留内容")
            (package/"标题.txt").write_text("护城河｜面朝北北")
            (package/"封面.png").write_bytes((Path(__file__).resolve().parents[1]/
                                          "resources/branding/studio-paper.png").read_bytes())
            export_backup(root/"backup", source_dir=package.parent)
            result = root/"backup"/package.name
            self.assertEqual({p.name for p in result.iterdir()},
                             {"正片.mp4", "封面.jpg", "中文字幕.zh-Hans.srt", "标题.txt", "简介.txt", "标签.txt"})
            self.assertTrue((result/"封面.jpg").read_bytes().startswith(bytes.fromhex("ffd8ff")))
            self.assertEqual((result/"标签.txt").read_text().strip(), "护城河")
            self.assertEqual((result/"正片.mp4").read_bytes(), (package/"正片.mp4").read_bytes())
