"""Frame-aligned visual caches and audio-only assembly. No provider calls here."""
from copy import deepcopy
from html import escape
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import time

from .core import digest, file_hash, probe, require, run, write


def frame_windows(timeline, fps, selected=None):
    require(isinstance(fps, int) and 1 <= fps <= 60, 'fps须为1–60整数')
    total = math.ceil(timeline['duration'] * fps - 1e-7)
    if selected:
        start, end = selected
        require(math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= timeline['duration'], '预览范围越界')
        a, b = math.floor(start*fps), min(total, math.ceil(end*fps-1e-7))
        return [{'id':'range', 'first_frame':a, 'frames':b-a, 'start':a/fps, 'end':b/fps}]
    starts = [0] + sorted(set(math.ceil(s['start']*fps-1e-7) for s in timeline['shots'] if s['start'] > 0))
    starts = [n for n in starts if n < total]
    return [dict(id=f'segment-{i:03}', first_frame=a, frames=b-a, start=a/fps, end=b/fps)
            for i,(a,b) in enumerate(zip(starts, starts[1:]+[total]))]


def visual_slice(timeline, start, end):
    """Preserve absolute animation time and the incoming dissolve's predecessor."""
    shots = timeline['shots']
    selected = {s['id'] for s in shots if s['start'] < end and s['end']+.45 > start}
    # Continuous worlds need their original declaration and all actions for valid state.
    scenes = {s.get('scene_id') for s in shots if s['id'] in selected and s['kind']=='object_scene'}
    needs_street = any(s['id'] in selected and s['kind']=='continuity' for s in shots)
    view = {'duration':timeline['duration'], 'shots':[], 'captions':[],
            'chapters':deepcopy(timeline.get('chapters',[])), 'overlays':[],
            '_nav_end':next((s['start'] for s in shots if s.get('channel_signoff')),None),
            '_nav_start':next((s['end'] for s in shots if s['kind']=='cover' and s['start']==0),0)}
    for i,s in enumerate(shots):
        if s['id'] in selected or (s['kind']=='object_scene' and s.get('scene_id') in scenes) or (needs_street and s['kind']=='continuity'):
            next_is_cut = i + 1 < len(shots) and shots[i + 1].get('transition') == 'cut'
            view['shots'].append(dict(deepcopy(s), _global_index=i, _global_count=len(shots),
                                      _next_is_cut=next_is_cut))
    for key in ('captions','overlays'):
        view[key] = [deepcopy(c) for c in timeline.get(key,[]) if c['start'] < end and c['end'] > start]
    if timeline.get('branding'):
        view['branding'] = deepcopy(timeline['branding'])
    if timeline.get('upcoming_chapters'):
        view['upcoming_chapters'] = list(timeline['upcoming_chapters'])
    if 'spoken_duration' in timeline:
        view['spoken_duration'] = timeline['spoken_duration']
    return view


class WindowMarkup(HTMLParser):
    def __init__(self, start, end):
        super().__init__(convert_charrefs=False)
        self.start, self.end, self.output = start, end, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'data-start' in attrs and 'data-duration' in attrs:
            a = float(attrs['data-start']); b = a+float(attrs['data-duration'])
            left, right = max(a,self.start), min(b,self.end)
            if right <= left:
                attrs.update({'data-hidden':'true','data-start':'0','data-duration':'0.001'})
            else:
                attrs['data-start'] = str(left-self.start)
                attrs['data-duration'] = str(right-left)
                if tag in ('video','audio'):
                    attrs['data-media-start'] = str(float(attrs.get('data-media-start',0))+left-a)
        self.output.append('<'+tag+''.join(' '+k if v is None else ' '+k+'="'+escape(v,quote=True)+'"' for k,v in attrs.items())+'>')
    def handle_endtag(self, tag): self.output.append('</'+tag+'>')
    def handle_data(self, data): self.output.append(data)
    def handle_entityref(self, name): self.output.append('&'+name+';')
    def handle_charref(self, name): self.output.append('&#'+name+';')
    def handle_comment(self, data): self.output.append('<!--'+data+'-->')


def window_markup(markup, start, end):
    parser = WindowMarkup(start,end); parser.feed(markup); parser.close()
    return ''.join(parser.output)


def bundle_hash(project):
    """Only rendered dependencies, not stale files or audio, determine a visual key."""
    document = (project/'index.html').read_text()
    names = set(re.findall(r'(?:(?:src|href)=["\']|url\(["\']?)(media/[^"\')]+)', document))
    return digest({'html':document, 'files':{name:file_hash(project/name) for name in sorted(names)}})


def mux(video, audio, output, start, length):
    run(['ffmpeg','-y','-v','error','-i',video,'-ss',str(start),'-i',audio,
         '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k',
         '-t',str(length),'-movflags','+faststart',output])


def join_segments(paths, output):
    # Concat's relative file list avoids shell interpolation and preserves encoded frames.
    listing = Path(output).with_suffix('.concat.txt')
    def quoted(p):return str(Path(p).resolve()).replace("'", "'\\''")
    listing.write_text(''.join("file '"+quoted(p)+"'\n" for p in paths))
    run(['ffmpeg','-y','-v','error','-f','concat','-safe','0','-i',listing,
         '-map','0:v:0','-c:v','copy','-an',output])
    listing.unlink()


def validate_frames(path, count, fps, width):
    data = probe(path)
    videos = [s for s in data['streams'] if s['codec_type']=='video']
    require(len(videos)==1, '镜头缓存缺少唯一视频流')
    v = videos[0]
    require(v['width']==width and v['height']==width*9//16, '镜头缓存分辨率不匹配')
    require(int(v.get('nb_frames',-1))==count, '镜头帧数不匹配，不能无损拼接')
    num,den = map(int,v['r_frame_rate'].split('/'))
    require(abs(num/den-fps)<1e-6, '镜头帧率不匹配')
    require(not any(s['codec_type']=='audio' for s in data['streams']), '画面缓存混入音轨')


def render_incremental(pipeline, hf, runtime, browser, browser_version):
    from .composition import compile_html
    config = pipeline.config.get('render',{})
    fps = config.get('preview_fps',30) if pipeline.mode=='preview' else config.get('fps',30)
    width = config.get('preview_width',1280) if pipeline.mode=='preview' else 1920
    require(width in (1280,1920), 'preview_width支持1280或1920')
    windows = frame_windows(pipeline.timeline,fps,pipeline.selection)
    signature = {'fps':fps,'width':width,'quality':'draft' if pipeline.mode=='preview' else 'high',
                 'browser':browser_version,'lock':file_hash(runtime/'package-lock.json'),'contract':'visual-segments/v1'}
    previous_path = pipeline.build/('preview-plan.json' if pipeline.mode=='preview' else 'render-plan.json')
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    old = {r['id']:r['visual_key'] for r in previous.get('segments',[])}
    rows, paths = [], []
    for row in windows:
        began = time.perf_counter()
        view = visual_slice(pipeline.timeline,row['start'],row['end']-1/fps+1e-8)
        project = pipeline.build/'segments'/row['id']
        compile_html(view,project,runtime,pipeline.images,pipeline.mode,pipeline.config.get('style',{}).get('id'),
                     window=(row['start'],row['end']),silent=True,width=width)
        key = dict(signature,bundle=bundle_hash(project),frames=row['frames'])
        before = pipeline.cache.misses
        def render(out):
            check = hf(['check','--json'],project,browser=browser)
            try: data,_ = json.JSONDecoder().raw_decode(check[check.index('{'):])
            except (ValueError,json.JSONDecodeError): data = {}
            require(data.get('ok') is True, '局部画面检查未通过')
            hf(['render','--output',str(out),'--fps',str(fps),'--quality',signature['quality'],
                '--workers',str(config.get('workers',2))],project,timeout=config.get('timeout',3600),browser=browser)
            validate_frames(out,row['frames'],fps,width)
        path = pipeline.task('visual-segment',key,'.mp4',render)
        validate_frames(path,row['frames'],fps,width)
        paths.append(path)
        rows.append(dict(row,visual_key=digest(key),cache_hit=pipeline.cache.misses==before,
                         changed=old.get(row['id'])!=digest(key),seconds=round(time.perf_counter()-began,3),
                         shots=[s['id'] for s in view['shots']],movie=str(path)))
        print(f'[visual] {row["id"]}: {"cached" if rows[-1]["cache_hit"] else "rendered"}',flush=True)
    first, last = windows[0]['start'], windows[-1]['end']
    visual = pipeline.task('visual-join',{'segments':[file_hash(p) for p in paths],'contract':'concat/v1'},'.mp4',
                           lambda out:join_segments(paths,out))
    validate_frames(visual,sum(r['frames'] for r in rows),fps,width)
    length = min(last,pipeline.timeline['duration'])-first
    began = time.perf_counter()
    movie = pipeline.task('av-mux',{'video':file_hash(visual),'audio':file_hash(pipeline.timeline['audio']),
                                   'start':first,'length':length,'contract':'aac192-copyvideo/v1'},'.mp4',
                          lambda out:mux(visual,pipeline.timeline['audio'],out,first,length))
    report = {'schema':'incremental-render/v1','mode':pipeline.mode,'fps':fps,'width':width,
              'start':first,'end':first+length,'segments':rows,'rendered':sum(not r['cache_hit'] for r in rows),
              'reused':sum(r['cache_hit'] for r in rows),'mux_seconds':round(time.perf_counter()-began,3),
              'visual_master':str(visual),'movie':str(movie),'movie_sha256':file_hash(movie)}
    write(pipeline.build/('preview-plan.json' if pipeline.mode=='preview' else 'render-plan.json'),report)
    pipeline.render_report = report
    return movie


def verify_preview(pipeline):
    import subprocess
    report = pipeline.render_report
    meta = probe(pipeline.movie)
    video = next((s for s in meta['streams'] if s['codec_type']=='video'),None)
    require(video and video['width']==report['width'] and video['height']==report['width']*9//16,'预览尺寸错误')
    require(any(s['codec_type']=='audio' for s in meta['streams']),'预览缺少声音')
    drift = abs(float(meta['format']['duration'])-(report['end']-report['start']))
    require(drift <= .15,'局部音画时长不一致')
    result = subprocess.run(['ffmpeg','-hide_banner','-nostats','-i',str(pipeline.movie),'-vf','blackdetect=d=0.3:pix_th=0.1',
                             '-af','astats=metadata=0:reset=0','-f','null','-'],capture_output=True,text=True,timeout=600)
    require(result.returncode==0,'预览解码失败')
    require('black_start:' not in result.stderr,'预览出现持续黑场')
    # Very short clips may legitimately be in a narration pause; never certify listening.
    frames = pipeline.output_dir/'frames';frames.mkdir(exist_ok=True)
    for name,fraction in [('start',.05),('middle',.5),('end',.95)]:
        run(['ffmpeg','-y','-v','error','-ss',str((report['end']-report['start'])*fraction),'-i',pipeline.movie,
             '-frames:v','1',frames/(name+'.jpg')])
    qa = {'machine_checks':'passed','mode':'preview','range':[report['start'],report['end']],
          'duration':report['end']-report['start'],'drift_seconds':drift,'width':report['width'],
          'movie':str(pipeline.movie),'movie_sha256':file_hash(pipeline.movie),
          'input_signature':pipeline.state['input_signature'],'listening_review':'pending','full_final_qa':False}
    write(pipeline.output_dir/'qa.json',qa)
    from .planning import quality_report
    write(pipeline.output_dir/'quality.json',quality_report(pipeline.root,pipeline.doc,pipeline.timeline,qa,'preview'))
    return qa
