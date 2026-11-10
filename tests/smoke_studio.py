"""Optional real macOS integration test: say → ASR → templates → HyperFrames MP4.

Run from repo root: python3 tests/smoke_studio.py [--through compose]
Requires the configured multilingual base ASR model already cached. This fixture
is an engineering verification, not an example of final illustration/voice quality.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CLI=[sys.executable,"-m","youtube_studio"]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--through",default="verify",choices=["compose","verify"])
    args=p.parse_args()
    if not shutil.which("say"):
        raise SystemExit("此真实声音 smoke 使用 macOS say；其他平台可用本地 audio/words 测试")
    episode=ROOT/"build/smoke"
    project=episode
    if not (project/"config.json").exists():
        subprocess.run([*CLI,"init","--episode",str(episode),"--title","新架构技术验证"],check=True)
        config=json.loads((project/"config.json").read_text())
        config["voice"]={"provider":"say","voice":"Tingting","rate":220}
        (project/"config.json").write_text(json.dumps(config,ensure_ascii=False,indent=2))
        shutil.copy2(ROOT/"tests/fixtures/smoke-script.json",project/"script.json")
        media=project/"media"
        media.mkdir(exist_ok=True)
        # Test-pattern raster exercises image cropping/motion without external media.
        subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i","color=c=0xf4f0e4:s=1920x1080",
                        "-vf","drawgrid=w=120:h=120:t=1:c=0xe7e3d8,drawbox=x=850:y=180:w=460:h=650:c=0xa3ad98:t=fill,drawbox=x=420:y=700:w=1100:h=15:c=0x687660:t=fill",
                        "-frames:v","1",str(media/"fixture.png")],check=True)
    subprocess.run([*CLI,"run","--episode",str(episode),"--mode","preview","--through",args.through],check=True)


if __name__=="__main__": main()
