"""Build the public-facing Yours showcase from reviewed copy and real test artifacts."""
import argparse
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
parser=argparse.ArgumentParser()
parser.add_argument('--out',default='dist/submission-site-v7')
parser.add_argument('--proof',default='runs/autolex-public-refresh')
parser.add_argument('--screenshots',default='runs/showcase-screenshots-current.json')
args=parser.parse_args()
root=Path.cwd();site=(root/args.out).resolve();site.mkdir(parents=True,exist_ok=True)
proof=(root/args.proof).resolve();proof.mkdir(parents=True,exist_ok=True)
identity=read_json(root/'runs/self-entry-current.json');copy=read_json(root/identity['copy'])
assert identity['url']=='https://yours.lexmount.cn/artifact-site/s/ct83Wy9aja_U', 'Wrong showcase target'
records=read_json(root/'runs/resubmission-lab/prepared.json')
current=read_json(root/'runs/presentation-current.json')
records=[{**r,'revision':current.get(r['run'],{}).get('run',r['revision'])} for r in records]
screenshot_manifest=root/args.screenshots
screenshots=read_json(screenshot_manifest) if screenshot_manifest.exists() else None
latest_checks=read_json(root/'runs/plain-language-lab/verification.json')
assert latest_checks['local_passed']

def esc(value):return html.escape(str(value),quote=True)
for name in ['style.css','app.js','mark.svg']:shutil.copyfile(root/'showcase'/name,site/name)
labels={
 'polish-csv':('资料存成哪种文件更合适？','把两种常见的数据文件放在一起比较，给新手一份带出处的选择说明。'),
 'polish-sqlite':('数据库，怎么备份更合适？','把两种 SQLite 备份办法放在一起，先看区别，再看适用条件。'),
 'agent-url-guide-v2':('网址拼接，少踩几个坑。','把网址拆开、再拼起来，会碰上什么问题？整理成一份能查原文的小抄。'),
 'agent-git-guide':('代码改错了，怎么撤回来？','改动还没保存，和已经提交，是两回事。用一张对照卡把撤销步骤分清楚。'),
 'agent-copy-visual':('复制了一份，怎么还会互相影响？','用标签、清单和玩具打比方，把程序里几种不同的复制方式讲明白。')}
ordered=sorted(records,key=lambda r:r['run']!='polish-csv');cards=[]
for index,r in enumerate(ordered):
    run=root/'runs'/r['revision'];visual=read_json(run/'visual-review.json');assert visual['passed']
    screenshot=next(run/path for path in visual['last']['images'] if path.endswith('desktop-top.png'))
    if screenshots:
        captured=screenshots['works'][r['run']]
        assert captured['url']==r['url'], 'Screenshot belongs to another work'
        screenshot=root/captured['image']
        assert hashlib.sha256(screenshot.read_bytes()).hexdigest()==captured['sha256'], 'Screenshot changed after capture'
    image_hash=hashlib.sha256(screenshot.read_bytes()).hexdigest()
    filename=r['run']+'-'+image_hash[:12]+'.png';shutil.copyfile(screenshot,site/filename)
    title,description=labels[r['run']]
    cards.append('<article class="work-card'+(' featured' if index==0 else '')+'"><button class="work-image" type="button" data-preview="'+filename+'" data-title="'+esc(title)+'" aria-label="查看'+esc(title)+'的实际截图"><img src="'+filename+'" alt="'+esc(title)+'的实际作品页面" width="1440" height="1050" loading="lazy"><span class="image-hint">查看实际截图 ↗</span></button><div class="work-body"><span class="work-badge">测试作品 '+str(index+1).zfill(2)+' / 流程测试作品</span><h3>'+esc(title)+'</h3><p>'+esc(description)+'</p><div class="work-bottom"><a href="'+esc(r['url'])+'" target="_blank" rel="noopener noreferrer">打开测试作品 ↗</a><button class="copy-code" type="button" data-copy="'+esc(r['passcode'])+'" aria-label="复制'+esc(title)+'的访问码">复制访问码 <strong>'+esc(r['passcode'])+'</strong></button></div></div></article>')
steps=['读规则','想点子','写代码','跑测试','看界面','交作品']
buttons=''.join('<button type="button" id="step-'+str(i)+'" role="tab" aria-selected="'+str(i==0).lower()+'" aria-controls="step-panel" tabindex="'+('0' if i==0 else '-1')+'" data-step="'+str(i)+'"><small>0'+str(i+1)+'</small>'+label+'</button>' for i,label in enumerate(steps))
disclaimer=copy['taskProblem'].split('\n\n')[0].removeprefix('先声明：')
index=(root/'showcase/index.html').read_text().replace('__TITLE__',esc(identity['title'])).replace('__DISCLAIMER__',esc(disclaimer)).replace('__STEP_BUTTONS__',buttons).replace('__WORK_CARDS__',''.join(cards))
(site/'index.html').write_text(index)
# GitHub is the only code/details destination. Remove stale outputs on rebuild.
for obsolete in ('materials.html','source.zip'):
    (site/obsolete).unlink(missing_ok=True)
load_environment('.env');secrets=[os.environ[k] for k in os.environ if any(s in k for s in ['API_KEY','ACCESS_TOKEN']) and len(os.environ[k])>8]
secrets.extend([read_json(root/'.release-profile.json')['contact_email'],read_json(Path.home()/'.config/lexmount/browser-cli/credentials.json')['api_key']])
for p in site.rglob('*'):
    if p.is_file() and p.suffix!='.zip' and any(s.encode() in p.read_bytes() for s in secrets):raise RuntimeError('Private value in '+p.name)
archive=site.with_suffix('.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(site.rglob('*')):
        if p.is_file():z.write(p,p.relative_to(site))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
write_json(proof/'build.json',{'target_url':identity['url'],'screenshots':screenshots,'archive':str(archive.relative_to(root)),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size,'file_hashes':{str(p.relative_to(site)):hashlib.sha256(p.read_bytes()).hexdigest() for p in site.rglob('*') if p.is_file()},'github_url':'https://github.com/TorinTao/Auto-Lexmount','details_page_removed':True,'private_scan':'passed','title':identity['title'],'copy_source':identity['copy']})
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'details_page_removed':True}))
