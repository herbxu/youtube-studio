from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from youtube_studio.core import StudioError, file_hash, read, write
from youtube_studio.cut_review import FILES, deliver, stage


class CutReview(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bundle = self.root / 'private'
        self.bundle.mkdir()
        self.dest = self.root / 'uploads' / 'episode'
        for name in FILES:
            (self.bundle / name).write_bytes(name.encode())

    def candidate(self, goals=None, machine='passed'):
        report = {'duration': 12, 'machine_checks': machine,
                  'movie_sha256': file_hash(self.bundle / '正片.mp4')}
        result = stage(self.root / 'review', self.bundle, self.dest, goals, report, 'inputs')
        return Path(result['round'])

    def fill(self, folder):
        path = folder / 'review.json'
        r = read(path)
        for goal in r['goals']:
            r['goals'][goal] = {'status': 'passed', 'observation': 'test observation'}
        for field in ('continuous_viewing', 'listening'):
            r[field] = {'status': 'passed', 'start': 0, 'end': 12, 'observation': 'test observation'}
        write(path, r)

    def test_repair_retest_and_promote(self):
        one = self.candidate(['示例目标'])
        r = read(one / 'review.json')
        issue = dict(id='late', time='00:06', problem='结果抢先', criterion='听到结果时出现')
        r['issues'] = [issue]
        write(one / 'review.json', r)
        self.assertEqual(deliver(one)['status'], 'needs_repair')
        self.assertFalse(self.dest.exists())
        (self.bundle / '正片.mp4').write_bytes(b'revised')
        two = self.candidate()
        self.assertIn('示例目标', read(two/'review.json')['goals'])
        with self.assertRaises(StudioError):
            deliver(one)
        write(two/'review.json', read(one/'review.json'))
        with self.assertRaises(StudioError):
            deliver(two)
        r.update(candidate=read(two/'candidate.json')['key'], round=two.name, issues=[])
        write(two/'review.json', r)
        self.fill(two)
        self.assertEqual(deliver(two)['status'], 'needs_repair')
        r = read(two/'review.json')
        r['issues'] = [{**issue, 'status':'fixed', 'retest':'00:06 新版逐帧复查'}]
        write(two/'review.json', r)
        self.assertEqual(deliver(two)['status'], 'delivered')
        self.assertEqual({p.name for p in self.dest.iterdir()}, set(FILES))
        self.assertEqual((self.dest/'正片.mp4').read_bytes(), b'revised')
        with self.assertRaises(StudioError):
            deliver(two)

    def test_machine_or_partial_review_cannot_deliver(self):
        one = self.candidate(machine='failed')
        self.fill(one)
        self.assertEqual(deliver(one)['status'], 'needs_repair')
        two = self.candidate()
        self.assertEqual(deliver(two)['status'], 'needs_review')
        self.fill(two)
        r = read(two/'review.json')
        r['listening']['end'] = 6
        write(two/'review.json', r)
        self.assertIn('实际听审', deliver(two)['pending'])
        self.assertFalse(self.dest.exists())
        self.fill(two)
        (two/'files/中文字幕.zh-Hans.srt').write_bytes(b'different')
        with self.assertRaises(StudioError):
            deliver(two)
        self.assertFalse(self.dest.exists())

    def test_metadata_change_does_not_repair_picture(self):
        folder = self.candidate()
        r = read(folder/'review.json')
        r['issues'].append(dict(id='frame', time='00:03', problem='字太小', criterion='能辨认'))
        write(folder/'review.json', r)
        (self.bundle/'标题.txt').write_text('新标题')
        two = self.candidate()
        self.fill(two)
        r = read(two/'review.json')
        r['issues'][0].update(status='fixed', retest='已查')
        write(two/'review.json', r)
        self.assertEqual(deliver(two)['status'], 'needs_repair')
        self.assertFalse(self.dest.exists())
