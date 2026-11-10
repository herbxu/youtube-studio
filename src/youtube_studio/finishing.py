"""Authored non-spoken opening/closing layers and conservative PCM repair."""
import re
import subprocess
import wave

from .core import require, write


def overlays(doc, units, shots):
    result = []
    for row in doc.get('overlays', []):
        unit = next(u for u in units if u['id'] == row['unit'])
        start = unit['start'] + row.get('offset', 0)
        end = start + row['duration']
        boundary = min(s['end'] for s in shots if s['start'] <= start < s['end'])
        require(end <= boundary-row.get('clear_before_cut', 0)+.001,
                '开场叠层须完成退场后再切镜；请缩短文字或调整入退场时长')
        require(end <= unit['end']+.001, '叠层不得超出口播单元')
        result.append(dict(row, start=start, end=end))
    return result


def add_closing(timeline, spec):
    if not spec:
        return
    start = timeline['duration']
    timeline['spoken_duration'] = start
    timeline['duration'] = start + spec['duration']
    timeline['shots'].append(dict(id='closing-card', kind='outro', start=start,
        end=timeline['duration'], tagline=spec['tagline'], transition='dissolve'))
    track = next((t for t in timeline['audio_tracks'] if t['id'] == spec['music_track']), None)
    require(track and abs(track['at']+track['duration']-start) < .01,
            '片尾音乐须指定当前结尾配乐；不能自动循环或用空白凑时长')
    track['duration'] += spec['duration']
    track['fade_out'] = min(3.2, spec['duration'])


def declick(source, output, threshold=4):
    """Interpolate detected short impulses; retain samples/timing and raw source."""
    with wave.open(str(source), 'rb') as f:
        count, rate, channels = f.getnframes(), f.getframerate(), f.getnchannels()
    graph = f'adeclick=t={threshold}:w=40:o=75:a=2:b=2,apad,atrim=end_sample={count}'
    proc = subprocess.run(['ffmpeg','-y','-hide_banner','-nostats','-i',str(source),
        '-af',graph,'-ar',str(rate),'-ac',str(channels),'-c:a','pcm_s16le',str(output)],
        capture_output=True,text=True,timeout=300)
    require(proc.returncode == 0, '脉冲修复失败：'+proc.stderr[-600:])
    with wave.open(str(output), 'rb') as f:
        require((f.getnframes(),f.getframerate(),f.getnchannels()) == (count,rate,channels),
                '声音修复改变了时长或声道')
    found = re.search(r'Detected clicks in (\d+) of (\d+) samples \(([^%]+)%\)', proc.stderr)
    write(output.parent/'repair.json', {'method':'adeclick','threshold':threshold,
        'samples':count,'sample_rate':rate,'channels':channels,
        'detected_impulse_samples':int(found[1]) if found else None,
        'detected_percentage':float(found[3]) if found else None,
        'listening_review':'pending','note':'算法检测是候选异常，不等同于听审确认杂音全部清除'})
