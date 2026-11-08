"""Portable before/after report and proof archive for the seven visual revisions."""
import hashlib
import html
import json
import os
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autolex.common import read_json,write_json
from autolex.config import load_environment
root=Path.cwd();lab=root/'runs/visual-retrospective'
verified=read_json(lab/'verification.json');assert verified['passed']
assert 'Ran 133 tests' in (lab/'unit.log').read_text() and '\nOK\n' in (lab/'unit.log').read_text()
assert '# pass 17' in (lab/'frontend.log').read_text()
records=[];cards=[];allfiles=[]
def esc(s):return html.escape(str(s),quote=True)
def rel(p):return os.path.relpath(p,lab)
for key,choice in read_json(root/'runs/batch7-lab/final-runs.json').items():
    before=root/'runs'/('visual-revisit-'+key);after=root/'runs'/('visual-final-'+key)
    first=read_json(lab/(key+'.json'));last=read_json(lab/('final-'+key+'.json'))
    initial_history=read_json(before/'visual-history.json');final_history=read_json(after/'visual-history.json')
    final_review=read_json(after/'visual-review.json')
    before_images=before/'visual/pass-1';after_images=after/'visual'/('pass-'+str(final_history[-1]['attempt']))
    title=read_json(after/'spec.json')['selected']['title']
    screenshots=len(list((before/'visual').rglob('*.png')))+len(list((after/'visual').rglob('*.png')))
    records.append({'case':key,'original':choice['run'],'first_review':before.name,'final':after.name,
                    'model_calls_this_round':first['visual_calls']+last['visual_calls'],
                    'screenshot_rounds':len(initial_history)+len(final_history),'screenshots':screenshots,
                    'remaining_issues':final_review['last']['review']['issues']})
    issues=final_review['last']['review']['issues']
    remains='<p>本轮最终评审没有列出剩余问题。</p>' if not issues else '<details><summary>保留 '+str(len(issues))+' 条非阻断建议</summary><ul>'+''.join('<li>'+esc(i['problem'])+'</li>' for i in issues)+'</ul></details>'
    cards.append('<article><div class="label">'+esc(key)+' · 视觉验收通过</div><h2>'+esc(title)+'</h2><p><a href="'+rel(after/'index.html')+'">打开修订作品</a> · <a href="'+rel(after/'submission.zip')+'" download>下载作品包</a> · <a href="'+rel(after/'visual-history.json')+'">最终评审记录</a></p><p>代码自动换行，文件大小与单位保持同行；原程序、资料、引用和结论不变。</p><div class="compare"><figure><figcaption>首次截图</figcaption><a class="image-link" href="'+rel(before_images/'mobile-implementation.png')+'"><img loading="lazy" data-dir="'+rel(before_images)+'" src="'+rel(before_images/'mobile-implementation.png')+'" alt="修改前的手机代码与目录截图"></a></figure><figure><figcaption>修改后重新截图</figcaption><a class="image-link" href="'+rel(after_images/'mobile-implementation.png')+'"><img loading="lazy" data-dir="'+rel(after_images)+'" src="'+rel(after_images/'mobile-implementation.png')+'" alt="修改后的手机代码与目录截图"></a></figure></div>'+remains+'</article>')
    for directory in [before,after]:
        allfiles += [p for p in directory.rglob('*') if p.is_file() and not p.is_symlink() and not p.name.startswith('.')]
summary={'passed':True,'works':7,'fresh_docker_runs':verified['fresh_container_runs'],'viewports_checked':verified['viewports_checked'],
 'python_tests':133,'frontend_tests':17,'new_model_calls':sum(r['model_calls_this_round'] for r in records),
 'screenshots':sum(r['screenshots'] for r in records),'records':records,
 'scope':'Visual-only review and model-generated presentation adjustments of seven prior works. Original program/data/reviews preserved; fresh Docker reruns match. No remote publication.',
 'limitations':'Sampled screenshots and stochastic model review; nonblocking filename wrapping/vertical-scroll suggestions remain for two works.'}
write_json(lab/'report-summary.json',summary)
style='body{margin:0;background:#f5f4fa;color:#292735;font:16px/1.75 system-ui}main{max-width:1100px;margin:auto;padding:32px 20px}h1{font-size:clamp(28px,5vw,44px);line-height:1.3}h2{font-size:23px;line-height:1.4}article{background:white;padding:24px;border:1px solid #e3dfee;border-radius:16px;margin:24px 0}a{color:#5842a5;overflow-wrap:anywhere}.label{font-size:13px;color:#655775}.compare{display:grid;grid-template-columns:1fr 1fr;gap:20px}figure{margin:0;text-align:center}figcaption{font-weight:600;margin:12px 0}img{max-width:100%;max-height:820px;border:1px solid #ddd;border-radius:10px}select{font:inherit;padding:8px;max-width:100%}details{margin-top:16px}li{overflow-wrap:anywhere}@media(max-width:600px){.compare{gap:8px}article{padding:16px}main{padding:22px 12px}}'
options=''.join('<option value="'+v+'"'+(' selected' if v=='mobile-implementation' else '')+'>'+label+'</option>' for v,label in [('mobile-implementation','手机 · 代码'),('mobile-directory','手机 · 文件目录'),('mobile-top','手机 · 页首'),('mobile-sources','手机 · 依据'),('desktop-implementation','桌面 · 代码'),('desktop-directory','桌面 · 文件目录'),('desktop-top','桌面 · 页首'),('desktop-sources','桌面 · 依据')])
body='<header><p>AUTO LEXMOUNT · 视觉回顾</p><h1>7 件作品，逐件看图后修改。</h1><p>7 件作品均完成自动视觉复查与反馈修订。新增 '+str(summary['new_model_calls'])+' 次模型调用，保存 '+str(summary['screenshots'])+' 张真实截图。7 次新容器复跑输出一致，14 个视口独立检查通过；133 项 Python 与 17 项前端测试通过。</p><p>本轮复用已有代码与内容验收记录，只调整展示；旧版本保留，未重复投稿。两件作品仍保留非阻断的文件名换行或纵向滚动提示建议。</p><p><a href="verification.json">独立核验记录</a> · <a href="report-summary.json">本轮统计</a></p><label>对比区域：<select id="view">'+options+'</select></label></header>'+''.join(cards)
script="document.getElementById('view').addEventListener('change',e=>{document.querySelectorAll('img[data-dir]').forEach(img=>{img.src=img.dataset.dir+'/'+e.target.value+'.png';img.parentElement.href=img.src})});"
(lab/'report.html').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>七作品视觉回顾与修订</title><style>'+style+'</style></head><body><main>'+body+'</main><script>'+script+'</script></body></html>')
allfiles += [p for p in lab.rglob('*') if p.is_file() and not p.is_symlink()]
for directory in ['autolex','tests','scripts','examples']:
    allfiles += [p for p in (root/directory).rglob('*') if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts and p.suffix in ['.py','.js','.cjs','.html','.css','.svg','.sh','.json']]
allfiles += [root/'README.md',root/'pyproject.toml',root/'.env.example']
load_environment('.env');secrets=[os.environ[k] for k in ['MODEL_API_KEY','LEXMOUNT_API_KEY'] if os.getenv(k)]
archive=root/'dist/seven-works-visual-revisions.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(set(allfiles)):
        data=p.read_bytes();assert not any(s.encode() in data for s in secrets),p.name
        z.writestr(str(p.relative_to(root)),data)
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
print(json.dumps({'report':str(lab/'report.html'),'archive':str(archive),'bytes':archive.stat().st_size,**{k:summary[k] for k in ['works','new_model_calls','screenshots']}},ensure_ascii=False))
