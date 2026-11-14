import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from youtube_studio.core import Blocked, Cache
from youtube_studio.portable import narration


class Portable(unittest.TestCase):
    def test_markdown_omits_nonspoken_headings_and_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp)/"s.md"
            script.write_text("# 标题\n\n## 章节\n\n<!-- 灯光 -->\n\n**第一段**。\n\n> 说明\n\n第二段。")
            self.assertEqual(narration(script), ("标题", ["第一段。", "第二段。"]))

    def test_unresolved_request_in_private_pack_blocks_paid_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            prior = Path(tmp)/"prior"
            with self.assertRaises(RuntimeError):
                Cache(prior).task("speech", {}, ".wav", Mock(side_effect=RuntimeError), paid=True)
            action = Mock()
            with self.assertRaises(Blocked):
                Cache(Path(tmp)/"empty", prior_root=prior).task("speech", {}, ".wav", action, paid=True)
            action.assert_not_called()
