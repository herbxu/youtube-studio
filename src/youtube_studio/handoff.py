"""Portable repository diagnostics and release metadata; never uploads media."""
import html
import os
import json
import subprocess
import zipfile
from tempfile import TemporaryDirectory
from pathlib import Path
from urllib.parse import quote

from .core import read, write, require, file_hash
from .storage import STUDIO, works, bench
from .planning import input_refs


def roots():
    repos = {'youtube-studio': STUDIO}
    if os.getenv('YOUTUBE_WORKS_ROOT'):
        repos['youtube'] = works()
    if os.getenv('YOUTUBE_WORKBENCH_ROOT'):
        repos['youtube-workbench'] = bench()
    return repos


def git(root, *args):
    if not root.is_dir():
        return None
    result = subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def actual_repo(root):
    top = git(root,'rev-parse','--show-toplevel')
    return bool(top and Path(top).resolve() == root.resolve())


def asset_status(root, ref, expected=None):
    p = (root/ref).resolve()
    if Path(ref).is_absolute() or not p.is_relative_to(root.resolve()):
        return 'invalid_path'
    if not p.is_file():
        return 'missing'
    with p.open('rb') as f:
        if f.read(43).startswith(b'version https://git-lfs.github.com/spec/v1'):
            return 'lfs_pointer'
    if expected and file_hash(p) != expected:
        return 'hash_mismatch'
    return 'ready'


def workspace(episode=None):
    repos=roots()
    found={name:{'path':str(root),'present':actual_repo(root)} for name,root in repos.items()}
    issues=[]
    def check(name,base,ref,expected=None):
        state=asset_status(base,ref,expected)
        if state!='ready':issues.append(dict(repository=name,path=ref,status=state))
    for name,root in repos.items():
        if not found[name]['present'] and not (name == 'youtube-studio' and (root/'pyproject.toml').is_file()):
            issues.append(dict(repository=name,status='missing_checkout'))
    lfs_counts={}
    for name,root in repos.items():
        if not found[name]['present']:continue
        listing=git(root,'lfs','ls-files','--json','HEAD')
        if listing is None:
            issues.append(dict(repository=name,status='cannot_list_lfs',hint='检查 Git LFS 安装及 HEAD'));continue
        entries=json.loads(listing)['files'] or [];lfs_counts[name]=len(entries)
        for entry in entries:check(name,root,entry['name'])
    idx=STUDIO/'resources/media/index.json'
    if idx.is_file():
        for row in read(idx)['assets']:
            name=row['repository'];check(name,repos[name],row['path'],row['sha256'])
    else:check('youtube-studio',STUDIO,'resources/media/index.json')
    if 'youtube' not in repos:
        if episode:
            from .pipeline import doctor
            result = doctor(Path(episode).resolve())
            issues.extend(dict(repository='episode', status=message) for message in result['issues'])
        return dict(ok=not issues, repositories=found, lfs_files_checked=lfs_counts, issues=issues)
    if episode:
        episode=Path(episode).resolve()
        require(episode.parent==works()/'episodes','--episode 必须属于作品库 episodes/')
        for f in ['config.json','script.json']:check('youtube',works(),str((episode/f).relative_to(works())))
        if (episode/'script.json').is_file() and (episode/'config.json').is_file():
            cfg=read(episode/'config.json')
            refs={v for u in read(episode/'script.json')['units'] for v in input_refs(u)}
            refs.update([cfg.get('voice',{}).get('reference_audio'),cfg.get('style',{}).get('branding',{}).get('asset')])
            for ref in sorted(filter(None,refs)):
                status=asset_status(episode,ref)
                if status!='ready':issues.append(dict(repository='youtube',episode=episode.name,path=ref,status=status))
    episodes = [episode] if episode else sorted((repos['youtube']/'episodes').glob('*'))
    for item in episodes:
        out = item/'deliverables'
        if not any((out/name).exists() for name in ('qa.json', 'output.mp4', 'release.json')):
            continue
        check('youtube', works(), str((out/'release.json').relative_to(works())))
        if not (out/'release.json').is_file():
            continue
        record = read(out/'release.json')
        for field in ('script', 'video', 'selection', 'source_snapshot'):
            ref = record.get(field)
            if ref:
                check(ref['repository'], repos[ref['repository']], ref['path'], ref['sha256'])
        for ref in (record.get('selection') or {}).get('decision', {}).get('evidence', []):
            check(ref['repository'], repos[ref['repository']], ref['path'], ref['sha256'])
        hashes = record.get('delivery_hashes', {})
        for required in ('output.mp4', '交付清单.html', 'qa.json'):
            if not hashes.get(required):
                issues.append(dict(repository='youtube', episode=item.name, path=required, status='missing_release_hash'))
        for name, expected in hashes.items():
            check('youtube', out, name, expected)
    return dict(ok=not issues,repositories=found,lfs_files_checked=lfs_counts,issues=issues)


def archive_source(episode):
    """Preserve the actual Python implementation and dependency pins for a dirty export."""
    target = bench()/'episodes'/episode.name/'production-source'
    target.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target) as tmp:
        snapshot = Path(tmp)/'source.zip'
        with zipfile.ZipFile(snapshot, 'w') as archive:
            files = sorted((STUDIO/'src/youtube_studio').glob('*.py'))
            files.extend(STUDIO/name for name in ('package-lock.json', 'pyproject.toml', 'requirements.txt'))
            for file in files:
                info = zipfile.ZipInfo(file.relative_to(STUDIO).as_posix())
                archive.writestr(info, file.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
        checksum = file_hash(snapshot)
        path = target/(checksum+'.zip')
        snapshot.replace(path)
    return {'repository': 'youtube-workbench', 'path': str(path.relative_to(bench())), 'sha256': checksum}


def review_summary(out, qa):
    path = out/'quality.json'
    quality = read(path) if path.exists() else {}
    matches = bool(qa.get('input_signature') and qa.get('movie_sha256')
                   and quality.get('movie_sha256') == qa['movie_sha256']
                   and quality.get('input_signature') == qa['input_signature'])
    areas = {}
    for key in ('content', 'audio', 'visual'):
        row = quality.get('checks', {}).get(key, {})
        areas[key] = row.get('status', 'pending') if matches and quality.get('review_bound') else 'pending'
    return {'machine_checks': qa.get('machine_checks', 'unknown'), 'editorial_checks': areas}


def release(episode, historical=False, historical_source=None):
    episode=Path(episode).resolve()
    require(episode.parent==works()/'episodes','仅为正式剧集生成发布清单')
    out=episode/'deliverables'; qa=read(out/'qa.json')
    movie=out/'output.mp4'; h=file_hash(movie)
    require(h==qa.get('movie_sha256'),'发布视频与 QA 哈希不符')
    revisions={}
    for name,root in roots().items():
        if actual_repo(root):
            revisions[name]={'commit':git(root,'rev-parse','HEAD'),'dirty':bool(git(root,'status','--porcelain'))}
        else:revisions[name]=None
    decision=bench()/'episodes'/episode.name/'selection.json'
    record={'schema':'studio-release/v1','episode':episode.name,'record_type':'historical_inventory' if historical else 'final_export',
            'repositories_at_recording':revisions,'production_studio_commit':None if historical or not revisions['youtube-studio'] or revisions['youtube-studio']['dirty'] else revisions['youtube-studio']['commit'],
            'script':{'repository':'youtube','path':str((episode/'script.json').relative_to(works())),'sha256':file_hash(episode/'script.json'),'basis':'at_inventory' if historical else 'at_export'},
            'video':{'repository':'youtube','path':str(movie.relative_to(works())),'sha256':h},'qa_input_signature':qa.get('input_signature'),
            'selection':None}
    if historical_source:
        require(historical, '历史来源仅用于盘点')
        record['historical_source'] = historical_source
    if not historical and record['production_studio_commit'] is None and 'youtube-workbench' in revisions:
        record['source_snapshot'] = archive_source(episode)
    if 'youtube-workbench' in revisions and decision.is_file():
        decision_data=read(decision)
        for ev in decision_data.get('evidence',[]):
            require(ev['repository'] in roots() and asset_status(roots()[ev['repository']],ev['path'],ev['sha256'])=='ready','选用依据已变化，请更新 selection.json 后交付')
        record['selection']={'repository':'youtube-workbench','path':str(decision.relative_to(bench())),'sha256':file_hash(decision),'decision':decision_data}
    # Prefer curated upload files, but never link a different video or an internal archive.
    files=[movie,out/'captions.srt']
    package=next((out/n for n in ('youtube-upload','youtube') if (out/n).is_dir()),out)
    covers=sorted(package.glob('*封面*')) if package!=out else []
    cover=next((p for p in covers if p.suffix.lower() in ('.png','.jpg','.jpeg')),out/'cover.png')
    if cover.is_file():files.append(cover)
    if package!=out:
        files += [p for p in sorted(package.iterdir()) if p.is_file() and (p.suffix=='.txt' or p.name=='metadata.json')]
    files=[p for p in files if p.is_file()]
    for p in files:require(asset_status(out,str(p.relative_to(out)))=='ready',f'不可交付：{p.name}')
    summary = review_summary(out, qa)
    record['review'] = summary
    labels = {'content': '内容', 'audio': '听审', 'visual': '连续观看'}
    states = {'passed': '通过', 'failed': '未通过', 'pending': '待审'}
    review_text = '，'.join(labels[k] + ' ' + states.get(v, '待审') for k, v in summary['editorial_checks'].items())
    receipt = out/'youtube-upload-receipt.json'
    receipt_data = read(receipt) if receipt.exists() else {}
    upload_text = '本地未归档该成片的上传回执'
    if receipt_data.get('video_sha256') == h:
        record['upload_receipt'] = receipt.name
        upload_text = '已归档匹配的上传回执，可见性以回执核验时为准：' + str(receipt_data.get('privacy', '未知'))
    items=''.join(f'<li><a href="{quote(p.relative_to(out).as_posix())}">{html.escape(p.name)}</a></li>' for p in files)
    missing=[]
    if not cover.is_file():missing.append('独立封面')
    if package==out:missing.append('上传文案')
    if not (out/'captions.srt').is_file():missing.append('字幕')
    note='未归档：'+'、'.join(missing) if missing else ''
    page=f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>发布清单</title><main><h1>{html.escape(episode.name)} · 发布清单</h1><p>人工验收：{html.escape(review_text)}。</p><p>{html.escape(upload_text)}。</p><ul>{items}</ul><p>{note}</p></main></html>'
    (out/'交付清单.html').write_text(page,encoding='utf-8')
    evidence = [out/'qa.json', out/'quality.json', out/'交付清单.html']
    if 'upload_receipt' in record:
        evidence.append(receipt)
    record['delivery_hashes'] = {p.relative_to(out).as_posix(): file_hash(p) for p in files + evidence if p.is_file()}
    write(out/'release.json',record)
    return record
