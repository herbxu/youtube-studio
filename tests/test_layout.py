"""CLI safety and delivery isolation for flat episode directories."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from youtube_studio.cli import main
from youtube_studio.core import read, write
from youtube_studio.pipeline import Pipeline, REPO


class Layout(unittest.TestCase):
    def invoke(self, *args):
        with patch('sys.argv', ['youtube-studio', *map(str, args)]), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main()

    def test_init_flat_directory_preserves_original_sources_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'episode'
            (root / 'source').mkdir(parents=True)
            original = root / 'source/original.txt'
            original.write_text('原文')
            self.assertEqual(self.invoke('init', '--episode', root), 0)
            self.assertTrue((root / 'config.json').is_file())
            self.assertFalse((root / 'production').exists())
            config = (root / 'config.json').read_bytes()
            self.assertEqual(self.invoke('init', '--episode', root), 2)
            self.assertEqual((root / 'config.json').read_bytes(), config)
            self.assertEqual(original.read_text(), '原文')

    def test_init_fresh_directory_and_rejects_legacy_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'new'
            self.assertEqual(self.invoke('init', '--episode', root), 0)
            legacy = Path(tmp) / 'legacy'
            (legacy / 'production').mkdir(parents=True)
            self.assertEqual(self.invoke('init', '--episode', legacy), 2)
            self.assertFalse((legacy / 'config.json').exists())

    def test_init_rejects_partial_authoring_files_without_writing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'script.json').write_text('{"draft":true}')
            self.assertEqual(self.invoke('init', '--episode', root), 2)
            self.assertFalse((root / 'config.json').exists())

    def test_render_deliveries_and_preview_are_isolated_from_existing_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / 'config.json', read(REPO / 'config/default.json'))
            final = root / 'deliverables'
            final.mkdir()
            (final / 'output.mp4').write_bytes(b'original movie')
            (final / 'captions.srt').write_text('original captions')
            for mode in ['preview', 'final']:
                pipeline = Pipeline(root, mode)
                pipeline.timeline = {}
                pipeline.config.setdefault('render',{})['strategy'] = 'monolithic'
                # Constructing/preparing a project must not overwrite deliveries.
                self.assertEqual((final / 'captions.srt').read_text(), 'original captions')
                pipeline.project = root / 'build/composition'
                pipeline.project.mkdir(exist_ok=True)
                (pipeline.build / 'captions.srt').write_text('new captions')
                cached = root / 'cached.mp4'
                cached.write_bytes(b'new movie')
                with patch('youtube_studio.pipeline.browser_for', return_value='/fake/chrome'), patch('youtube_studio.pipeline.run', return_value='Chrome test'), patch.object(pipeline, 'task', return_value=cached):
                    pipeline.render()
                expected = final if mode == 'final' else root / 'build/preview'
                self.assertEqual(pipeline.movie.parent, expected.resolve())
                self.assertEqual((expected / 'captions.srt').read_text(), 'new captions')
                if mode == 'preview':
                    self.assertEqual((final / 'output.mp4').read_bytes(), b'original movie')
                    self.assertEqual((final / 'captions.srt').read_text(), 'original captions')
