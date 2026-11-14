from pathlib import Path
import tempfile, unittest
from unittest.mock import patch
from youtube_studio import handoff as h
from youtube_studio.core import write, file_hash, StudioError

class Handoff(unittest.TestCase):
    def test_missing_checkout_pointer_and_escape_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);media=root/'a';media.write_bytes(b'version https://git-lfs.github.com/spec/v1\noid sha256:example')
            self.assertEqual(h.asset_status(root,'a'),'lfs_pointer')
            self.assertEqual(h.asset_status(root,'absent'),'missing')
            self.assertEqual(h.asset_status(root,'../escape'),'invalid_path')
            missing=root/'missing'
            with patch.object(h,'roots',return_value={n:missing for n in ('youtube','youtube-studio','youtube-workbench')}):
                self.assertEqual(sum(x['status']=='missing_checkout' for x in h.workspace()['issues']),3)

    def test_historical_inventory_checks_identity_and_keeps_private_files_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();ep=root/'episodes/episode';out=ep/'deliverables';out.mkdir(parents=True)
            (out/'output.mp4').write_bytes(b'video');(out/'secret-review.txt').write_text('internal')
            write(ep/'script.json',{});write(out/'qa.json',{'movie_sha256':h.file_hash(out/'output.mp4')})
            with patch.object(h,'works',return_value=root),patch.object(h,'bench',return_value=root/'bench'):
                record=h.release(ep,historical=True)
                self.assertIsNone(record['production_studio_commit'])
                self.assertNotIn('secret-review',(out/'交付清单.html').read_text())
                (out/'output.mp4').write_bytes(b'wrong')
                with self.assertRaises(StudioError):h.release(ep,historical=True)

    def test_archive_is_stable_for_unchanged_source(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(h, 'bench', return_value=Path(tmp)):
            episode = Path('episode')
            first = h.archive_source(episode)
            self.assertEqual(first, h.archive_source(episode))
            self.assertEqual(file_hash(Path(tmp)/first['path']), first['sha256'])
            with h.zipfile.ZipFile(Path(tmp)/first['path']) as archive:
                self.assertIn('src/youtube_studio/pipeline.py', archive.namelist())
                self.assertNotIn('.env.local', archive.namelist())

    def test_review_summary_requires_movie_input_and_bound_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            qa = {'movie_sha256': 'movie', 'input_signature': 'a', 'machine_checks': 'passed'}
            quality = {**qa, 'review_bound': True, 'checks': {'audio': {'status': 'passed'}}}
            for signature, bound, expected in [('a', True, 'passed'), ('b', True, 'pending'), ('a', False, 'pending')]:
                write(out/'quality.json', {**quality, 'input_signature': signature, 'review_bound': bound})
                self.assertEqual(h.review_summary(out, qa)['editorial_checks']['audio'], expected)
