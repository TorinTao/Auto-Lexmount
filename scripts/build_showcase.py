"""Build the public-facing Yours showcase from reviewed copy and real test artifacts."""
import hashlib
import html
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autolex.common import read_json,write_json
from autolex.config import load_environment
root=Path.cwd();site=root/'dist/submission-site-v6';site.mkdir(parents=True,exist_ok=True)
proof=root/'runs/yours-redesign';proof.mkdir(exist_ok=True)
identity=read_json(root/'runs/self-entry-current.json');copy=read_json(root/identity['copy'])
records=read_json(root/'runs/resubmission-lab/prepared.json')
def esc(value):return html.escape(str(value),quote=True)
for name in ['style.css','app.js','mark.svg']:shutil.copyfile(root/'showcase'/name,site/name)
labels={
 'polish-csv':('CSV / JSON，选哪个？','两种常见的数据文件，什么时候用哪种？给新手一张带出处的选择指南。'),
 'polish-sqlite':('数据库，怎么备份更合适？','把两种 SQLite 备份办法放在一起，先看区别，再看适用条件。'),
 'agent-url-guide-v2':('网址拼接，少踩几个坑。','把网址拆开、再拼起来，会碰上什么问题？整理成一份能查原文的小抄。'),
 'agent-git-guide':('代码改错了，怎么撤回来？','改动还没保存，和已经提交，是两回事。用一张对照卡把撤销步骤分清楚。'),
 'agent-copy-visual':('复制了一份，为什么还会一起变？','浅拷贝和深拷贝有什么不同？用一份中文指南，解释“复制”背后的区别。')}
ordered=sorted(records,key=lambda r:r['run']!='agent-copy-visual');cards=[]
for index,r in enumerate(ordered):
    run=root/'runs'/r['revision'];visual=read_json(run/'visual-review.json');assert visual['passed']
    screenshot=next(run/path for path in visual['last']['images'] if path.endswith('desktop-top.png'))
    filename=r['run']+'.png';shutil.copyfile(screenshot,site/filename)
    title,description=labels[r['run']]
    cards.append('<article class="work-card'+(' featured' if index==0 else '')+'"><button class="work-image" type="button" data-preview="'+filename+'" data-title="'+esc(title)+'" aria-label="查看'+esc(title)+'的实际截图"><img src="'+filename+'" alt="'+esc(title)+'的实际作品页面" width="1440" height="1050" loading="lazy"><span class="image-hint">查看实际截图 ↗</span></button><div class="work-body"><span class="work-badge">TEST WORK '+str(index+1).zfill(2)+' / 流程测试作品</span><h3>'+esc(title)+'</h3><p>'+esc(description)+'</p><div class="work-bottom"><a href="'+esc(r['url'])+'" target="_blank" rel="noopener noreferrer">打开测试作品 ↗</a><button class="copy-code" type="button" data-copy="'+esc(r['passcode'])+'" aria-label="复制'+esc(title)+'的访问码">复制访问码 <strong>'+esc(r['passcode'])+'</strong></button></div></div></article>')
steps=['读规则','想点子','写代码','跑测试','看界面','交作品']
buttons=''.join('<button type="button" id="step-'+str(i)+'" role="tab" aria-selected="'+str(i==0).lower()+'" aria-controls="step-panel" tabindex="'+('0' if i==0 else '-1')+'" data-step="'+str(i)+'"><small>0'+str(i+1)+'</small>'+label+'</button>' for i,label in enumerate(steps))
disclaimer=copy['taskProblem'].split('\n\n')[0].removeprefix('先声明：')
index=(root/'showcase/index.html').read_text().replace('__TITLE__',esc(identity['title'])).replace('__DISCLAIMER__',esc(disclaimer)).replace('__STEP_BUTTONS__',buttons).replace('__WORK_CARDS__',''.join(cards))
(site/'index.html').write_text(index)
# Keep readable source and actual evidence one click away; no credential files or form screenshots.
source=[]
for folder in ['autolex','tests','scripts','examples','showcase']:
    source += [p for p in sorted((root/folder).rglob('*')) if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts and p.suffix in ['.py','.js','.cjs','.html','.css','.svg','.sh','.json']]
source += [root/'README.md',root/'pyproject.toml',root/'.env.example']
evidence=[root/'runs/resubmission-lab/verification.json',root/'runs/resubmission-lab/official-final-verification.json',root/identity['copy']]
for r in records:
    run=root/'runs'/r['revision']
    evidence += [run/name for name in ['main.py','input.json','output.json','tests.json','quality.json','review.json','visual-review.json','visual-history.json','visual-theme.json']]
files=source+evidence
sections=''.join('<details class="source-file" data-filename="'+esc(str(p.relative_to(root)))+'"><summary>'+esc(str(p.relative_to(root)))+'</summary><pre>'+esc(p.read_text())+'</pre></details>' for p in files)
receipts=''.join('<li><strong>'+esc(labels[r['run']][0])+'</strong><span>测试收件编号：'+esc(r['receipt'])+'</span><span>访问码：'+esc(r['passcode'])+' · 已做访客访问与源码核验</span><a href="'+esc(r['url'])+'" target="_blank" rel="noopener noreferrer">打开测试材料 ↗</a></li>' for r in ordered)
fullcopy=''.join('<details><summary>'+label+'</summary><p>'+esc(copy[key])+'</p></details>' for key,label in [('taskProblem','为什么做这个娱乐实验？'),('cloudRole','怎么做的，云平台参与了什么？'),('taskResult','实际结果与发现')])
body='<header class="site-header wrap"><a class="brand" href="index.html"><img src="mark.svg" width="34" height="34" alt=""><span>Auto<span class="brand-light">Lexmount</span><small>让 AI 去忙。</small></span></a><a class="text-link" href="index.html">← 回到介绍页</a></header><main class="wrap"><div class="evidence-hero"><p class="eyebrow">把话说轻松，把证据留认真。</p><h1>想看它有没有吹牛？<br>记录都在这里。</h1><p>这里收录真实运行记录、测试回执，以及可阅读和下载的源码。没有把流程演示当成真实运行，也没有把收件成功写成获奖。</p></div><div class="evidence-layout"><nav class="evidence-nav" aria-label="证据分类"><a href="#checks">做过哪些检查</a><a href="#receipts">五件测试回执</a><a href="#start-guide">想自己跑起来</a><a href="#source">源码与运行记录</a><a href="#about">实验说明全文</a></nav><div><section class="evidence-section" id="checks"><h2>真的跑过，也真的改过。</h2><div class="proof-stats"><div><strong>136</strong>程序回归测试通过</div><div><strong>17</strong>网页交互测试通过</div><div><strong>5</strong>作品重新执行，结果一致</div></div><p>五件测试作品都做了电脑与手机截图检查，并实际运行程序核对结果。之前还故意做过“小到看不清的字”和“挤成细条的排版”，看看检查流程能不能发现并修好。</p><p>模型也会漏判：过小字号曾被 AI 放过，最终由浏览器规则挡住。所以这些检查是帮忙把关，不是百分之百正确的保证。</p></section><section class="evidence-section" id="receipts"><h2>五件测试作品，五份过程记录。</h2><p>这些提交用于流程测试，不作为正式参赛作品。测试用途已与审核人员沟通，后续测试提交会按约定标记。这里保留收件号，是为了核对流程确实走到了最后一步。</p><ul class="proof-list">'+receipts+'</ul></section><section class="evidence-section" id="start-guide"><h2>想自己跑，先做一点准备。</h2><ol class="setup-steps"><li><strong>下载源码，按 README 配好环境。</strong>需要 Python、Docker、AI 模型和 Lexmount 的配置。</li><li><strong>登录并授权。</strong>验证码由你本人完成；想自动投稿，还要配置发布资料并勾选相应选项。</li><li><strong>打开本机控制台。</strong>填一个方向，点启动，再看它交作业。</li></ol><p>配置完成后的启动命令：</p><code class="command">./scripts/autolex.sh serve</code><p>在运行它的电脑上打开 <code>http://127.0.0.1:8765</code>。本页是展示页，不会调用你的 AI 或替你发起投稿。</p><a class="button primary" href="source.zip" download>下载源码与记录 ↓</a></section><section class="evidence-section" id="source"><h2>源码不藏着，想看就展开。</h2><p>按文件名搜索。不了解代码也没关系，回到首页看作品和流程就够了。</p><div class="source-search"><label for="source-search" class="fine">找文件</label><input type="search" id="source-search" placeholder="例如：visual.py、README、测试记录" autocomplete="off"><span id="source-count" role="status">共 '+str(len(files))+' 个文件</span></div>'+sections+'</section><section class="evidence-section about-copy" id="about"><h2>实验说明，和表单同步。</h2><p>页面已同步最新作品名称与三栏说明。作者提供方向、账号登录和授权；Codex 协助开发，DeepSeek 和 Lexmount 执行已配置的工作流。</p>'+fullcopy+'</section></div></div></main><footer class="site-footer wrap"><a class="brand" href="index.html">Auto Lexmount ✳</a><p>流水线负责干活，不包中奖。</p><a href="index.html">回到介绍页 ↗</a></footer>'
body=body.replace('<h2>实验说明，和表单同步。</h2>','<h2>实验说明，和表单同步。</h2><p><strong>作品名称：</strong>'+esc(identity['title'])+'</p>')
(site/'materials.html').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>源码与验证记录 · Auto Lexmount</title><link rel="icon" href="mark.svg" type="image/svg+xml"><link rel="stylesheet" href="style.css"><script src="app.js" defer></script></head><body>'+body+'</body></html>')
load_environment('.env');secrets=[os.environ[k] for k in os.environ if any(s in k for s in ['API_KEY','ACCESS_TOKEN']) and len(os.environ[k])>8]
secrets.extend([read_json(root/'.release-profile.json')['contact_email'],read_json(Path.home()/'.config/lexmount/browser-cli/credentials.json')['api_key']])
for p in files:
    if any(s.encode() in p.read_bytes() for s in secrets):raise RuntimeError('Private value in '+p.name)
with zipfile.ZipFile(site/'source.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in files:z.write(p,p.relative_to(root))
for p in site.rglob('*'):
    if p.is_file() and p.suffix!='.zip' and any(s.encode() in p.read_bytes() for s in secrets):raise RuntimeError('Private value in '+p.name)
archive=root/'dist/submission-site-v6.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(site.rglob('*')):
        if p.is_file():z.write(p,p.relative_to(site))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
write_json(proof/'build.json',{'archive':str(archive.relative_to(root)),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size,'files':[str(p.relative_to(root)) for p in files],'source_files':len(source),'source_and_evidence_files':len(files),'private_scan':'passed','title':identity['title'],'copy_source':identity['copy']})
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'source_files':len(source),'source_and_evidence_files':len(files)}))
