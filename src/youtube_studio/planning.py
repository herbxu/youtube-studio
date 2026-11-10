"""Argument progression and evidence-based delivery status; never auto-approve taste."""
from .core import require, read, file_hash, normalize

REVIEW_AREAS=('content','audio','visual','engineering','efficiency')

def input_refs(unit):
    refs=[unit.get('audio'),unit.get('words')]
    for s in unit.get('shots',[]):
        refs += [s.get('asset'),s.get('secondary_asset')]
        refs += [o.get('asset') for o in s.get('objects',[])]
    refs += [t.get('asset') for t in unit.get('audio_tracks',[])]
    return [r for r in refs if r]


def validate_plan(doc):
    plan=doc.get('narrative')
    if plan is None:return
    require(isinstance(plan,dict),'narrative 必须为对象')
    for k in ['audience_belief','intended_shift','author_position']:
        require(isinstance(plan.get(k),str) and plan[k].strip(),f'narrative 缺少 {k}')
    chapters=plan.get('chapters',[]);require(isinstance(chapters,list) and chapters,'narrative 缺少 chapters')
    seen=[];ids=set()
    for c in chapters:
        require(isinstance(c,dict) and isinstance(c.get('id'),str) and c['id'] not in ids,'章节 ID 重复/无效');ids.add(c['id'])
        for k in ['question','changes','bridge']:
            require(isinstance(c.get(k),str) and c[k].strip(),f'章节缺少 {k}')
        require(isinstance(c.get('units'),list) and c['units'],'章节缺少 units');seen+=c['units']
    require(seen==[u['id'] for u in doc['units']],'章节须按顺序且不重复覆盖全部单元')


def quality_report(root,doc,timeline=None,qa=None,mode='final'):
    """Human results are valid only when bound to both this movie and inputs."""
    warnings=[];checks={k:{'status':'pending','evidence':[]} for k in REVIEW_AREAS}
    if not doc.get('narrative'):warnings.append('缺少整片认知递进规划')
    for u in doc['units']:
        for s in u['shots']:
            headline=normalize(s.get('headline',''))
            if headline and len(headline)>18 and headline in normalize(u['text']):warnings.append(f"{s['id']}：长标题复述口播，审查视觉贡献")
    if timeline:
        for s in timeline['shots']:
            for e in s.get('events',[]):
                if e['at']+e.get('duration',.55)+.8>s['end']:warnings.append(f"{s['id']}：动作后停留较短，检查可读性")
    if qa and qa.get('machine_checks')=='passed':checks['engineering']={'status':'passed','evidence':['qa.json']}
    review_path=root/'review.json';bound=False
    if review_path.exists() and qa:
        review=read(review_path)
        bound=review.get('movie_sha256')==qa.get('movie_sha256') and review.get('input_signature')==qa.get('input_signature')
        if bound:
            for key in REVIEW_AREAS:
                row=review.get('checks',{}).get(key,{})
                if row.get('status') in {'passed','failed'} and row.get('evidence'):
                    checks[key]=row
        else:warnings.append('人工审阅未绑定当前成片和输入，保持待审')
    ready=bool(qa and qa.get('machine_checks')=='passed' and mode=='final' and all(v['status']=='passed' for v in checks.values()))
    return {'schema':'opinion-quality/v1','status':'reviewed' if ready else 'needs_review',
            'mode':mode,'checks':checks,'warnings':warnings,'review_bound':bound,
            'movie_sha256':(qa or {}).get('movie_sha256'),'input_signature':(qa or {}).get('input_signature'),
            'note':'规则提示不是审美评分；未做听审/连续观看不能自动通过。'}
