#!/usr/bin/env python3
"""Single entrypoint for opinion video production."""
import argparse
import json
import sys
import subprocess
import os
from pathlib import Path

from .storage import runtime
from .core import StudioError, read, write, validate_script, file_hash
from .pipeline import Pipeline, REPO, STAGES, doctor, input_signature
from .editorial import review_script


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["produce","export-upload","check-workspace","init","doctor","validate","review","quality","run","resume","status","preview","sample"])
    parser.add_argument("--episode", type=Path)
    parser.add_argument("--title", default="新一期观点视频")
    parser.add_argument("--mode", choices=["preview","final"], default="final")
    parser.add_argument("--through", choices=STAGES, default="verify")
    parser.add_argument('--shot', help='sample：只预览指定镜头及前后0.6秒')
    parser.add_argument('--start',type=float,help='sample：全片起始秒数')
    parser.add_argument('--end',type=float,help='sample：全片结束秒数')
    parser.add_argument('--port',type=int,default=3017,help='浏览器预览服务端口')
    parser.add_argument('--stop',action='store_true',help='停止本剧集的浏览器预览服务')
    parser.add_argument("--retry-uncertain", action="store_true", help="确认外部服务记录后，重试上次结果不确定的请求（可能重复计费）")
    parser.add_argument("--destination", type=Path, help="export-upload：新建的最终上传备份目录")
    parser.add_argument("--script", type=Path, help="Markdown 口播脚本")
    parser.add_argument("--assets", type=Path, help="可选的私有制作素材目录")
    parser.add_argument("--source", type=Path, help="export-upload：上传成品根目录")
    args = parser.parse_args()
    if args.command == "review" and args.script:
        if args.episode:
            parser.error("review 请选择 --script 或 --episode 其中一种输入")
        from .portable import review_markdown
        try:
            result = review_markdown(args.script.expanduser())
        except (StudioError, OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "produce":
        if not args.script or not args.destination:
            parser.error("produce 需要 --script 和 --destination")
        from .local_env import load_local_env
        from .portable import produce
        load_local_env()
        try:
            result = produce(args.script, args.assets, args.destination)
        except (StudioError, OSError, ValueError, KeyError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "export-upload":
        if not args.destination:
            parser.error("export-upload 需要 --destination")
        from .upload_backup import export_backup
        try:
            result = export_backup(args.destination, args.episode, args.source)
        except (StudioError, OSError, ValueError, KeyError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    from .local_env import load_local_env
    load_local_env()
    if args.command == 'check-workspace':
        from .handoff import workspace
        try: result=workspace(args.episode)
        except (StudioError,ValueError,OSError,KeyError) as exc: result={'ok':False,'error':str(exc)}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result['ok'] else 2
    if not args.episode:parser.error('--episode is required')
    root = args.episode.resolve()
    try:
        if args.stop and args.command!='preview': raise StudioError('--stop只用于preview')
        if args.shot or args.start is not None or args.end is not None:
            if args.command != 'sample': raise StudioError('局部范围参数只用于sample')
            if args.shot and (args.start is not None or args.end is not None): raise StudioError('--shot与时间范围不能同时使用')
            if (args.start is None) != (args.end is None): raise StudioError('--start与--end需要成对提供')
        if args.command == "init":
            if root.exists() and (not root.is_dir() or any((root/name).exists() for name in ("config.json", "brief.json", "script.json", "production"))):
                raise StudioError(f"已存在，未覆盖：{root}")
            root.mkdir(parents=True, exist_ok=True)
            write(root/"config.json",read(REPO/"config/default.json"))
            write(root/"brief.json",{"title":args.title,"thesis":"","audience":"普通投资者","sources":[],"constraints":[]})
            result = {"episode":str(root),"next":"填写 brief.json 并用 youtube-write 生成 script.json；配置 providers 后运行 doctor"}
        elif not (root / "config.json").is_file():
            raise StudioError("剧集根目录没有 config.json；新剧集先运行 init，旧 production 工程需迁移")
        elif args.command == "doctor":
            result = doctor(root,args.through,args.mode)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 0 if result["ok"] else 2
        elif args.command == "validate":
            doc = validate_script(read(root/"script.json"))
            result = {"ok":True,"units":len(doc["units"])}
        elif args.command == "review":
            result = review_script(validate_script(read(root/"script.json")))
        elif args.command == "quality":
            from .planning import quality_report
            doc = validate_script(read(root/"script.json"))
            qa_path = (root/"deliverables" if args.mode == "final" else runtime(root)/"build/preview")/"qa.json"
            qa = read(qa_path) if qa_path.exists() else None
            if qa:
                movie = qa_path.parent / ("output.mp4" if args.mode=="final" else "preview.mp4")
                if (not movie.is_file() or qa.get("input_signature") != input_signature(root)
                        or file_hash(movie) != qa.get("movie_sha256")):
                    qa = None
            timeline = read(runtime(root)/"build/timeline.json") if (runtime(root)/"build/timeline.json").exists() else None
            result = quality_report(root,doc,timeline,qa,args.mode)
        elif args.command == "status":
            result = read(runtime(root)/"state.json") if (runtime(root)/"state.json").exists() else {"status":"not_started"}
            if result.get("input_signature") and result["input_signature"] != input_signature(root):
                result = {**result,"status":"stale","previous_status":result["status"],"note":"输入或运行代码已变化，旧成片不是当前版本"}
            release_path = root/'deliverables/release.json'
            if release_path.is_file():
                from .handoff import asset_status
                record = read(release_path)
                result['archived_delivery'] = {
                    'record_type': record['record_type'],
                    'video_status': asset_status(release_path.parent, 'output.mp4', record['video']['sha256']),
                    'review': record.get('review'),
                }
        elif args.command == 'preview':
            from .pipeline import browser_for, hf
            if args.stop:
                return subprocess.call([str(REPO/'node_modules/.bin/hyperframes'),'preview',str(runtime(root)/'build/composition'),'--stop'])
            pipeline = Pipeline(root,args.mode,args.retry_uncertain)
            pipeline.execute('compose')
            browser = browser_for(pipeline.config)
            check = hf(['check','--json'],pipeline.project,browser=browser)
            payload,_ = json.JSONDecoder().raw_decode(check[check.index('{'):])
            if payload.get('ok') is not True: raise StudioError('浏览器预览检查未通过')
            if not 1024 <= args.port <= 65535: raise StudioError('端口须为1024–65535')
            env = dict(os.environ,HYPERFRAMES_BROWSER_PATH=browser)
            command = [str(REPO/'node_modules/.bin/hyperframes'),'preview',str(pipeline.project)]
            code = subprocess.call([*command,'--port',str(args.port),'--background','--no-open'],cwd=pipeline.project,env=env)
            if code: return code
            status = subprocess.check_output([*command,'--status','--json'],cwd=pipeline.project,env=env,text=True)
            result = json.loads(status)['result']
            if not result.get('ready'): raise StudioError('预览服务未就绪')
        elif args.command == 'sample':
            selection = (args.start,args.end) if args.start is not None else None
            result = Pipeline(root,'preview',args.retry_uncertain,selection,args.shot).execute('verify')
        else:
            result = Pipeline(root,args.mode,args.retry_uncertain).execute(args.through)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (StudioError,FileNotFoundError,KeyError,ValueError) as e:
        print(json.dumps({"error":str(e)},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
