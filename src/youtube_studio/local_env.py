"""Read a small, non-executable local credential file; never log its values."""
import os
from pathlib import Path

NAMES = {'ALIYUN_TTS_API_KEY', 'DASHSCOPE_API_KEY', 'ALIYUN_TTS_BASE_URL'}


def load_local_env(path=None):
    path = Path(path) if path else Path(__file__).resolve().parents[2] / '.env.local'
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        key, sep, value = line.strip().partition('=')
        if not sep or key not in NAMES:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value and not os.environ.get(key):
            os.environ[key] = value
