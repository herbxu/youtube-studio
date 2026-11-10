"""Offline, deterministic narration-first mix for locally sourced SFX/BGM."""
from .core import duration, probe, require, run, number


def mix_audio(voice, tracks, output, length):
    args = ['ffmpeg','-y','-v','error','-i',str(voice)]
    filters, labels = [], ['voice']
    ducked = sum(t.get('duck', False) for t in tracks)
    if ducked:
        filters.append(f'[0:a]apad,atrim=end_sample={round(length*48000)},asplit='+str(ducked+1)+'[voice]'+''.join(f'[side{i}]' for i in range(ducked)))
    else:
        filters.append(f'[0:a]apad,atrim=end_sample={round(length*48000)}[voice]')
    side = 0
    for i,t in enumerate(tracks):
        require(any(s['codec_type']=='audio' for s in probe(t['path'])['streams']), f"{t['id']} 素材没有音轨")
        begin, span, at = t.get('source_in',0), t['duration'], t['at']
        require(begin+span <= duration(t['path'])+.02, f"{t['id']} 音频区间越界；不自动循环")
        require(at >= 0 and at+span <= length+.001, f"{t['id']} 音轨超出成片")
        args += ['-i',str(t['path'])]
        fade = min(t.get('fade',.04),span/2)
        fade_out = min(t.get('fade_out',fade),span/2)
        filters.append(f'[{i+1}:a]atrim=start={begin}:duration={span},asetpts=PTS-STARTPTS,'
                       f'aformat=sample_rates=48000:channel_layouts=stereo,volume={t["gain_db"]}dB,'
                       f'afade=t=in:d={fade},afade=t=out:st={span-fade_out}:d={fade_out},'
                       # Count samples after delay: a timestamp-based duration trim
                       # can discard leading silence on delayed/cropped input frames.
                       f'adelay={round(at*48000)}S:all=1,apad,atrim=end_sample={round(length*48000)},'
                       f'asetpts=N/SR/TB[track{i}]')
        if t.get('duck',False):
            release=t.get('duck_release_ms',250)
            number(release,100,2000,'audio.duck_release_ms')
            filters.append(f'[track{i}][side{side}]sidechaincompress=threshold=0.025:ratio=8:attack=15:release={release}[duck{i}]')
            labels.append(f'duck{i}');side += 1
        else:
            labels.append(f'track{i}')
    filters.append(''.join(f'[{label}]' for label in labels)+f'amix=inputs={len(labels)}:normalize=0:duration=first,'
                   f'alimiter=limit=0.84:level=false:latency=true,aresample=48000,apad,atrim=end_sample={round(length*48000)}[mix]')
    run(args+['-filter_complex',';'.join(filters),'-map','[mix]','-ar','48000','-ac','2','-c:a','pcm_s16le',output])
