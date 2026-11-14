"""Storage layout shared by production, inspection and voice utilities."""
import os
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[2]


def works():
    return Path(os.environ.get('YOUTUBE_WORKS_ROOT', Path.cwd())).expanduser().resolve()


def bench():
    return Path(os.environ.get('YOUTUBE_WORKBENCH_ROOT', Path(os.environ.get("YOUTUBE_STUDIO_CACHE", Path.home()/".cache"/"youtube-studio")))).expanduser().resolve()


def runtime(episode):
    episode = Path(episode).resolve()
    if not os.environ.get("YOUTUBE_WORKBENCH_ROOT"):
        return episode
    for base, namespace in ((works() / 'episodes', 'episodes'), (bench() / 'examples', 'examples')):
        if episode.parent == base:
            return bench() / 'runtime' / namespace / episode.name
    # Isolated smoke tests and temporary standalone projects keep their own root.
    return episode


def adapter_revision(path):
    # Only this storage-only move is byte-compatible with previously billed voice requests.
    from .core import file_hash
    actual = file_hash(path)
    return '3286020f82ce32e6e3db348536c26fc64455ac3865bbb2420ed0f7a6cfc31717' if actual == 'd50d63a722938f02523563c1c175dc183cf9b00931e8abee09550b95411012d4' else actual
