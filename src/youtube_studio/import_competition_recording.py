"""Episode-specific importer for the 20260829 competition recording and subtitles.

Run: python -m youtube_studio.import_competition_recording --episode <directory>
Reviewed SRT boundaries below apply only to this recording.

Uses actual Whisper cross-attention / DTW alignment, never character-count timing.
The transcript is constrained: 100% text coverage is not independent ASR accuracy.
"""
import argparse
import json
import math
import re
import subprocess
import sys
import wave
from pathlib import Path

from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio
from faster_whisper.tokenizer import Tokenizer

from youtube_studio.storage import runtime
from youtube_studio.core import normalize, file_hash

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", required=True, type=Path)
    args = parser.parse_args()
    ROOT = args.episode.resolve()
    out = ROOT / "media/recordings"
    evidence = ROOT / "source/import-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (runtime(ROOT) / "build").mkdir(parents=True,exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'media/audio/original.mp3'
    captions = []
    subtitle_source = ROOT / 'source/scripts/录音_final.srt'
    for block in subtitle_source.read_text().strip().split('\n\n'):
        lines = block.splitlines()
        stamps = re.findall(r'(\d+):(\d+):(\d+),(\d+)', lines[1])
        def seconds(p):
            return int(p[0])*3600+int(p[1])*60+int(p[2])+int(p[3])/1000
        captions.append({'text':''.join(lines[2:]),'start':seconds(stamps[0]),'end':seconds(stamps[1])})
    write(evidence/'imported-captions.json',{'method':'Existing SRT, previously cross-checked against this recording with independent ASR','segments':captions})
    script = json.loads((ROOT / 'script.json').read_text())
    # Reviewed semantic boundaries, indexed into the existing SRT (1-based).
    first = [1,10,22,41,52,62,69,80,85,100,120,141,154,167,184,202,213,224,237,247,252,259]
    assert len(first) == len(script['units']) + 1
    full = runtime(ROOT) / 'build/recording-decoded.wav'
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(source),'-ar','48000','-ac','1','-c:a','pcm_s16le',str(full)],check=True)
    audio = decode_audio(str(source), sampling_rate=16000)
    model = WhisperModel('small', device='cpu', compute_type='int8', cpu_threads=6, local_files_only=True)
    tokenizer = Tokenizer(model.hf_tokenizer, model.model.is_multilingual, task='transcribe', language='zh')
    report = {'source_sha256':file_hash(source),'method':'faster-whisper/small cross-attention DTW forced alignment',
              'reference':'existing SRT cross-checked with independent base/small ASR',
              'coverage_warning':'Reference-constrained alignment; text coverage does not measure transcription accuracy.', 'units':[]}
    with wave.open(str(full),'rb') as wav:
        rate = wav.getframerate()
        total = wav.getnframes()
        boundaries = [0] + [round((captions[n-2]['end'] + captions[n-1]['start'])/2*rate) for n in first[1:-1]] + [total]
        for i,unit in enumerate(script['units']):
            rows = captions[first[i]-1:first[i+1]-1]
            actual = '，'.join(x['text'] for x in rows) + '。'
            if 'draft_text' not in unit:
                unit['draft_text'] = unit['text']
            unit['text'] = actual
            unit['editorial_status'] = '按现有录音字幕导入；独立 ASR 交叉核对，口误与事实问题见运行记录'
            start,end = boundaries[i]/rate,boundaries[i+1]/rate
            dest = out / (unit['id'] + '.wav')
            wav.setpos(boundaries[i])
            with wave.open(str(dest),'wb') as part:
                part.setparams(wav.getparams())
                part.writeframes(wav.readframes(boundaries[i+1]-boundaries[i]))
            measured = []
            groups = []
            group = []
            for row in rows:
                if group and row['end'] - group[0]['start'] > 23:
                    groups.append(group); group=[]
                group.append(row)
            if group: groups.append(group)
            raw_records = []
            for j,group in enumerate(groups):
                a = start if j == 0 else (groups[j-1][-1]['end'] + group[0]['start'])/2
                b = end if j+1 == len(groups) else (group[-1]['end'] + groups[j+1][0]['start'])/2
                clip = audio[round(a*16000):round(b*16000)]
                features = model.feature_extractor(clip)
                encoded = model.encode(features)
                text = '，'.join(x['text'] for x in group) + '。'
                words = model.find_alignment(tokenizer, [tokenizer.encode(text)], encoded, [min(features.shape[-1],3000)])[0]
                pending = ''
                for w in words:
                    raw_records.append({k:float(v) if k in {'start','end','probability'} else v for k,v in w.items() if k!='tokens'})
                    t = w['word']
                    if not normalize(t): continue
                    lo,hi = max(0,float(w['start'])+a-start),min(end-start,float(w['end'])+a-start)
                    if hi <= lo:
                        # Merge zero-duration tokens into a neighbouring measured word.
                        # Do not invent a duration or distribute them across a whole clip.
                        if measured: measured[-1]['text'] += t
                        else: pending += t
                        continue
                    measured.append({'text':pending+t,'start':lo,'end':hi,'probability':float(w['probability'])})
                    pending=''
                assert not pending, 'No measurable word for leading token'
            timing = {'method':report['method'],'words':measured,'reference_constrained':True,'audio_sha256':file_hash(dest)}
            write(out/(unit['id']+'.words.json'),timing)
            write(out/(unit['id']+'.raw-alignment.json'),{'words':raw_records})
            unit['audio'] = str(dest.relative_to(ROOT))
            unit['words'] = str((out/(unit['id']+'.words.json')).relative_to(ROOT))
            report['units'].append({'id':unit['id'],'start':start,'end':end,'srt_rows':[first[i],first[i+1]-1], 'words':len(measured)})
            print(unit['id'],round(start,2),round(end,2),len(measured),'words',flush=True)
    write(ROOT/'script.json',script)
    write(out/'report.json',report)

if __name__ == '__main__': main()
