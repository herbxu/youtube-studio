"""Local media catalog: search, audit and freeze verified assets into an episode."""
import argparse
import json
import re
import shutil
from pathlib import Path

from .storage import works, bench
from .core import read, write, require, file_hash, StudioError

REPO=Path(__file__).resolve().parents[2]
DEFAULT=REPO/'resources/media/index.json'


def load(index):
    data=read(index) if index.exists() else {'schema':'opinion-library/v1','assets':[]}
    require(data.get('schema')=='opinion-library/v1' and isinstance(data.get('assets'),list),'素材索引无效')
    ids=set()
    for row in data['assets']:
        require(isinstance(row,dict) and re.fullmatch(r'[a-z][a-z0-9-]{0,60}',row.get('id','')) and row['id'] not in ids,'素材 ID 无效/重复');ids.add(row['id'])
        for key in ['type','path','subject','action','usage','license_name','recovery']:
            require(bool(row.get(key)),f"{row['id']} 缺少 {key}")
        require(row['type'] in {'image','video','sfx','bgm','voice-reference'},'素材 type 无效')
        require(re.fullmatch(r'[a-f0-9]{64}',row.get('sha256','')),'素材 sha256 无效')
    return data


def local_path(row,repo=REPO):
    if repo == REPO and row.get('repository'):
        bases={'youtube':works(),'youtube-workbench':bench(),'youtube-studio':REPO}
        require(row['repository'] in bases,'未知素材仓库')
        repo=bases[row['repository']]
    elif repo == REPO:
        prefix = Path(row['path']).parts[:1]
        if prefix == ('examples',): repo = bench()
        if prefix == ('episodes',): repo = works()
    p=(repo/row['path']).resolve();require(p.is_relative_to(repo.resolve()),'素材路径不能越出仓库');return p


def audit(index=DEFAULT,repo=REPO):
    rows=[]
    for row in load(index)['assets']:
        p=local_path(row,repo)
        status='missing' if not p.is_file() else 'ready' if file_hash(p)==row['sha256'] else 'changed'
        rows.append({'id':row['id'],'status':status,'path':row['path'],'recovery':row['recovery']})
    return {'ok':all(r['status']=='ready' for r in rows),'assets':rows}


def search(query,index=DEFAULT):
    terms=query.lower().split()
    fields=['subject','action','environment','usage','tags','id']
    results=[]
    for row in load(index)['assets']:
        text=' '.join(str(row.get(k,'')) for k in fields).lower()
        score=sum(t in text for t in terms)
        if score or not terms:results.append(dict(row,match_score=score))
    return sorted(results,key=lambda r:(-r['match_score'],r['id']))


def freeze(asset_id,episode,index=DEFAULT,repo=REPO):
    row=next((r for r in load(index)['assets'] if r['id']==asset_id),None)
    require(row is not None,'素材 ID 不存在');src=local_path(row,repo)
    require(src.is_file(),f'素材缺失，按 recovery 恢复：{row["recovery"]}')
    require(file_hash(src)==row['sha256'],'共享素材已变化，先重新检查和登记')
    episode=episode.resolve();dest=episode/'media/library'/f"{asset_id}{src.suffix.lower()}"
    require(dest.resolve().is_relative_to(episode),'目标路径越界')
    if dest.exists():require(file_hash(dest)==row['sha256'],'同名本期素材内容不同，未覆盖')
    else:dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
    manifest_path=episode/'media/library-manifest.json'
    manifest=read(manifest_path) if manifest_path.exists() else {'schema':'opinion-library-freeze/v1','assets':[]}
    record={**row,'path':str(dest.relative_to(episode)),'library_path':row['path'],
            'inspection':{'reuse_fit':'pending','note':'冻结验证文件完整性；本期用途、裁切与听审另行检查。'}}
    manifest['assets']=[r for r in manifest['assets'] if r['id']!=asset_id]+[record]
    write(manifest_path,manifest)
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['search','check','add','freeze'])
    p.add_argument('--index',type=Path,default=DEFAULT);p.add_argument('--query',default='');p.add_argument('--record',type=Path)
    p.add_argument('--id');p.add_argument('--episode',type=Path);a=p.parse_args()
    try:
        if a.command=='search':result=search(a.query,a.index)
        elif a.command=='check':result=audit(a.index)
        elif a.command=='freeze':
            require(a.id and a.episode,'freeze 需要 --id 和 --episode');result=freeze(a.id,a.episode,a.index)
        else:
            require(a.record,'add 需要 --record');row=read(a.record);data=load(a.index)
            src=local_path(row);require(src.is_file(),'登记文件不存在');row['sha256']=file_hash(src)
            require(not any(r['id']==row['id'] for r in data['assets']),'ID 已存在，需人工检查后更新索引')
            data['assets'].append(row)
            # Validate before replacing the actual index.
            from tempfile import TemporaryDirectory
            with TemporaryDirectory() as tmp:
                candidate=Path(tmp)/'index.json';write(candidate,data);load(candidate)
            write(a.index,data);result=row
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 2 if a.command=='check' and not result['ok'] else 0
    except (StudioError,FileNotFoundError,KeyError,ValueError) as e:
        print(json.dumps({'error':str(e)},ensure_ascii=False));return 2

if __name__=='__main__':raise SystemExit(main())
