"""Build explicit public materials for the existing Agent entry, excluding credentials."""
import hashlib
import html
import json
import shutil
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autolex.common import read_json,write_json
from autolex.config import load_environment
import os
root=Path.cwd();lab=root/'runs/visual-release-lab';site=root/'dist/submission-site-v4';site.mkdir(parents=True,exist_ok=True)
run=root/'runs/agent-copy-visual';release=read_json(run/'release-state.json')
assert release['status']=='submitted' and release['guest_verified']
visual=read_json(run/'visual-review.json');assert visual['passed']
style='body{margin:0;background:#f5f4fa;color:#292735;font:17px/1.75 system-ui}main{max-width:1050px;margin:auto;padding:28px 20px}section,details{background:white;border:1px solid #ddd5ec;border-radius:14px;padding:22px;margin:18px 0}h1{font-size:clamp(28px,5vw,44px);line-height:1.25}a{color:#5842a5;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.65 monospace}summary{cursor:pointer;font-weight:600}img{max-width:100%;border:1px solid #ddd;border-radius:10px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}@media(max-width:650px){.grid{grid-template-columns:1fr}}'
def page(title,body):return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+style+'</style></head><body><main>'+body+'</main></body></html>'
records=read_json(root/'runs/polish-20261108/publications.json')
records.append({'title':release['title'],'url':release['url'],'passcode':release['passcode'],'receipt':release['receipt']['id']})
links=''.join('<li><a href="'+html.escape(r['url'])+'">'+html.escape(r['title'])+'</a><br>访问码：'+html.escape(r['passcode'])+' · 收件编号：'+html.escape(r['receipt'])+'</li>' for r in records)
copydir=site/'copy-guide';copydir.mkdir(exist_ok=True)
for name in ['index.html','materials.html']:shutil.copyfile(run/'release'/name,copydir/name)
proofs=[]
last=visual['last']
for key in last['images']:
 p=run/key
 if p.name in ['desktop-top.png','mobile-sources.png','desktop-implementation.png','mobile-directory.png']:
  label='visual-'+p.name;shutil.copyfile(p,site/label);proofs.append('<figure><img src="'+label+'" alt="'+html.escape(p.name)+'"><figcaption>'+html.escape(p.name)+'</figcaption></figure>')
body='''<p>AUTO LEXMOUNT · 第 4 版 · 2026-11-08</p><h1>读资料、写代码，自动看图验收再投稿。</h1><p>接入 DeepSeek 与 Lexmount 的公开资料任务 Agent。Agent 本体与生成作品分别发布、分别保存收件回执。</p><nav><a href="materials.html">在线查看最新源码与证据</a> · <a href="copy-guide/index.html">查看本轮独立作品</a></nav><section><h2>本轮新增：视觉反馈闭环</h2><p>生成和测试后自动采集桌面、手机的页首、来源、源码与目录，共 8 张截图。DeepSeek 直接评审图片；发现阅读障碍后自动调整受限制的表现层设置，再截图复验，最多修复两次。浏览器确定性检查与模型共同决定是否可打包投稿。</p><p>过小字号、过窄多列两份独立故障夹具均经历失败→自动修复→重新截图通过。字号案例中模型曾漏判，由浏览器检查阻止放行；模型视觉判断不是绝对保证。</p></section><section><h2>真实运行与质量证据</h2><p>130 项 Python、17 项前端回归测试通过。此前七主题实验最终 7/7 满足数量和来源要求，68 项工作流输入检查、40 项独立复验通过。本轮新作品从 Lexmount 取证、DeepSeek 生成/修复、容器执行与引用检查、自动截图验收，一路运行到独立发布与官方收件。</p><p>当前范围仍为 1–3 个公开来源的资料工具，使用固定报告模板。视觉自动修复处理样式，不能自动修复任意应用或保证事实正确；截图只覆盖抽样视口，未声称整体提速。</p></section><section><h2>五件独立生成作品与官方回执</h2><ol>'''+links+'''</ol></section><section><h2>本轮自动采集的作品截图</h2><div class="grid">'''+''.join(proofs)+'''</div></section><footer>作者提供任务方向、账号登录与授权；Codex 协助开发 Agent。作品生成、测试和截图评审由已配置工作流执行。收件成功不代表获奖。</footer>'''
(site/'index.html').write_text(page('Auto Lexmount · 第 4 版',body))
sources=[]
for directory in ['autolex','tests','scripts','examples']:
 sources += [p for p in sorted((root/directory).rglob('*')) if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts and p.suffix in ('.py','.js','.cjs','.html','.css','.svg','.sh','.json')]
sources += [root/'README.md',root/'pyproject.toml',root/'.env.example']
for name in ['state.json','manifest.json','main.py','tests.json','quality.json','citations.json','visual-review.json','visual-history.json','release-state.json','submission-state.json']:
 sources.append(run/name)
for kind in ['fixture','columns']:
 for name in ['result.json','visual-history.json']:sources.append(lab/kind/name)
sources += [root/'runs/batch7-lab/verification.json',root/'runs/batch7-lab/reviewer-final.json']
sections=''.join('<details><summary>'+html.escape(str(p.relative_to(root)))+'</summary><pre>'+html.escape(p.read_text())+'</pre></details>' for p in sources)
(site/'materials.html').write_text(page('最新源码与自动视觉验收证据','<a href="index.html">返回 Agent 本体</a><h1>最新源码与自动视觉验收证据</h1><p>只收录明确列出的源码及运行记录，未包含实际环境配置、联系人资料或登录凭据。</p>'+sections))
load_environment('.env')
secrets=[os.environ[k] for k in os.environ if any(s in k for s in ('API_KEY','ACCESS_TOKEN')) and len(os.environ[k])>8]
secrets += [read_json(root/'.release-profile.json')['contact_email'],read_json(Path.home()/'.config/lexmount/browser-cli/credentials.json')['api_key']]
for p in site.rglob('*'):
 if p.is_file() and any(s.encode() in p.read_bytes() for s in secrets):raise RuntimeError('Private value in public materials: '+p.name)
archive=root/'dist/submission-site-v4.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(site.rglob('*')):
  if p.is_file():z.write(p,p.relative_to(site))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
write_json(lab/'self-package.json',{'archive':str(archive.relative_to(root)),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size,'source_files':len(sources),'private_value_scan':'passed'})
print(json.dumps(read_json(lab/'self-package.json')))
