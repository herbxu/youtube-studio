import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from youtube_studio.storage import runtime
from youtube_studio.core import read, write
from youtube_studio.pipeline import Pipeline, REPO

class Storage(unittest.TestCase):
    def test_managed_project_and_example_do_not_share_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            works=Path(tmp).resolve()/'works'; bench=Path(tmp).resolve()/'bench'
            with patch.dict(os.environ,YOUTUBE_WORKS_ROOT=str(works),YOUTUBE_WORKBENCH_ROOT=str(bench)):
                root=works/'episodes/test'; example=bench/'examples/test'
                for path in (root,example):write(path/'config.json',read(REPO/'config/default.json'))
                p=Pipeline(root,'preview'); q=Pipeline(root,'final')
                self.assertEqual(p.cache.root,q.cache.root)
                self.assertEqual(p.output_dir,bench/'runtime/episodes/test/build/preview')
                self.assertEqual(q.output_dir,root/'deliverables')
                self.assertNotEqual(runtime(example),runtime(root))
                self.assertFalse((root/'build').exists())
