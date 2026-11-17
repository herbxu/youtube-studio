import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from youtube_studio.av_review import audio_window
from youtube_studio.core import StudioError, read, write
from youtube_studio.portable import narration, produce
from youtube_studio.cut_review import FILES
from youtube_studio.rsi import repair_from_sources
from youtube_studio.script_review import admit, assess, review_path, template


class ScriptAdmission(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.script = self.root / "script.md"
        self.script.write_text("# 标题\n\n买价十元，等下一份财报。\n\n> 出处不口播。\n")
        self.paragraphs = narration(self.script)[1]
        self.report = template(self.script, self.paragraphs)
        for row in self.report["criteria"].values():
            row.update(status="passed", quote="买价十元", evidence="算例")
        self.report["paragraphs"][0]["contribution"] = "规定报价和查账时点"
        self.save()

    def save(self):
        write(review_path(self.script), self.report)

    def test_editorial_cannot_pass_on_a_reference_or_old_script(self):
        self.assertEqual(admit(self.script)["status"], "passed")
        self.report["criteria"]["evidence"]["quote"] = "出处不口播"
        self.save()
        with self.assertRaises(StudioError):
            admit(self.script)
        self.report["criteria"]["evidence"]["quote"] = "买价十元"
        self.save()
        self.script.write_text(self.script.read_text().replace("十元", "五元"))
        with self.assertRaises(StudioError):
            admit(self.script)

    def test_insufficient_evidence_blocks_production_before_preparation(self):
        self.report["criteria"]["alternative"]["status"] = "insufficient"
        self.save()
        with self.assertRaisesRegex(StudioError, "配音前脚本"):
            produce(self.script, None, self.root / "delivery")
        self.assertFalse((self.root / "delivery").exists())

    def test_every_paragraph_needs_a_distinct_decision_or_evidence(self):
        self.report["paragraphs"] = []
        self.save()
        self.assertEqual(assess(self.script, self.paragraphs)["status"], "needs_repair")

    def test_music_absent_from_encoded_mix_fails_with_identical_voice(self):
        rng = np.random.default_rng(12)
        voice, music = rng.normal(0,.08,8000), rng.normal(0,.014,8000)
        self.assertTrue(audio_window(voice + music,voice,music,0,1)["passed"])
        self.assertFalse(audio_window(voice,voice,music,0,1)["passed"])

    def test_chapter_repair_preserves_original_and_surrounding_copy(self):
        originals = self.root / "private"
        originals.mkdir()
        for name in FILES:
            (originals/name).write_bytes(b"fixture")
        body = "正文\n\n00:00 过期\n02:00 过期\n\n来源\n"
        (originals/"简介.txt").write_text(body)
        manifest = self.root / "manifest.json"
        write(manifest, {"chapters":[{"label":"问题","start":0},{"label":"证据","start":17.3}]})
        machine = {"editorial":{"status":"passed"}, "audiovisual":{"issues":[{"id":"description"}]}}
        target = self.root / "repaired"
        self.assertTrue(repair_from_sources(originals,manifest,machine,target))
        self.assertEqual((originals/"简介.txt").read_text(), body)
        self.assertEqual((target/"简介.txt").read_text(), "正文\n\n00:00 问题\n00:17 证据\n\n来源\n")
