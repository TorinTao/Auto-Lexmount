"""Package Agent v5 and only the five already-submitted works as publication evidence."""
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

root=Path.cwd();lab=root/'runs/resubmission-lab';site=root/'dist/submission-site-v5'
site.mkdir(parents=True,exist_ok=True)
records=read_json(lab/'prepared.json');assert len(records)==5
for record in records:
    update=read_json(lab/'updates'/record['run']/'state.json')
    assert update['status']=='complete' and update['guest_verified'] and update['reloaded_content_matches']
assert 'Ran 136 tests' in (lab/'unit.log').read_text() and '\nOK\n' in (lab/'unit.log').read_text()
assert '# pass 17' in (lab/'frontend.log').read_text()
def esc(s):return html.escape(str(s),quote=True)
style='body{margin:0;background:#f5f4fa;color:#292735;font:17px/1.75 system-ui}main{max-width:1050px;margin:auto;padding:28px 20px}section,details{background:white;border:1px solid #ddd5ec;border-radius:14px;padding:22px;margin:18px 0}h1{font-size:clamp(28px,5vw,44px);line-height:1.25}a{color:#5842a5;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.65 monospace}summary{cursor:pointer;font-weight:600}img{max-width:100%;border:1px solid #ddd;border-radius:10px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}@media(max-width:650px){.grid{grid-template-columns:1fr}}'
def page(title,body):return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+style+'</style></head><body><main>'+body+'</main></body></html>'
links=''.join('<li><a href="'+esc(r['url'])+'">'+esc(r['title'])+'</a><br>访问码：'+esc(r['passcode'])+' · 原收件编号：'+esc(r['receipt'])+'</li>' for r in records)
pictures=[]
for r in records:
    run=root/'runs'/r['revision'];visual=read_json(run/'visual-review.json')
    files=list(visual['last']['images'])
    source=next(run/name for name in files if name.endswith('mobile-implementation.png'))
    filename=r['run']+'-mobile.png';shutil.copyfile(source,site/filename)
    pictures.append('<figure><img src="'+filename+'" alt="'+esc(r['title'])+'"><figcaption>'+esc(r['title'])+'</figcaption></figure>')
body='''<p>AUTO LEXMOUNT · 第 5 版 · 2026-11-08</p><h1>读资料、写代码，自动看图验收再投稿。</h1><p>接入 DeepSeek 与 Lexmount 的公开资料工作流 Agent。工具本体与生成成果分别保留作品链接及官方回执。</p><nav><a href="materials.html">在线查看最新源码与证据</a></nav><section><h2>视觉回顾后的表现层修订</h2><p>工作流自动采集桌面与手机的页首、来源、源码和文件目录，共8张截图，交给 DeepSeek 逐张评审。发现阅读障碍时在有限预算内调整字号、宽度、间距和列数，再截图复验；新增代码自动换行与字节单位保持同行。浏览器确定性检查不能被模型的通过结论覆盖，未通过则阻止打包投稿。</p><p>模型视觉评审可能漏判或误判，截图仅覆盖抽样视口。修复限定于表现层，不能证明所有事实或任意应用均正确。</p></section><section><h2>本次只更新已投稿的五件作品</h2><p>CSV/JSON、SQLite备份、URL解析、Git撤销与copy模块五件已有成果均保留原始代码、输入和结论，应用更新后的展示方式，并通过新的DeepSeek截图评审。五次无网络Docker复跑与原输出一致。线上材料按原链接更新；访客已核验报告及精确源码；官网在原条目保存修改，保留原收件编号并重新打开核验。</p><p>另有七件内部回顾样例仍未作为独立作品投稿，本页不另行发布它们的成果页面。本体当前136项Python与17项前端回归测试通过。</p></section><section><h2>五件已投稿成果与原回执</h2><ol>'''+links+'''</ol></section><section><h2>本轮实际截图</h2><div class="grid">'''+''.join(pictures)+'''</div></section><footer>作者提供方向、登录与授权；Codex协助开发和调试Agent。DeepSeek执行作品生成、修复及模型辅助评审。官方收件成功不代表获奖。</footer>'''
(site/'index.html').write_text(page('Auto Lexmount · 第 5 版',body))
files=[]
for folder in ['autolex','tests','scripts','examples']:
    files.extend(p for p in sorted((root/folder).rglob('*')) if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts and p.suffix in ['.py','.js','.cjs','.css','.html','.svg','.sh','.json'])
files += [root/'README.md',root/'pyproject.toml',root/'.env.example',lab/'prepared.json']
for r in records:
    run=root/'runs'/r['revision']
    files += [run/name for name in ['main.py','input.json','output.json','tests.json','quality.json','review.json','visual-review.json','visual-history.json','visual-theme.json']]
    files.append(lab/'updates'/r['run']/'state.json')
sections=''.join('<details><summary>'+esc(str(p.relative_to(root)))+'</summary><pre>'+esc(p.read_text())+'</pre></details>' for p in files)
(site/'materials.html').write_text(page('最新源码与已投稿作品更新证据','<a href="index.html">返回Agent本体</a><h1>最新源码与已投稿作品更新证据</h1><p>公开源码与指定验证记录；不包含实际配置、登录凭据及联系人表单。</p>'+sections))
load_environment('.env')
secrets=[os.environ[k] for k in os.environ if any(s in k for s in ['API_KEY','ACCESS_TOKEN']) and len(os.environ[k])>8]
secrets.extend([read_json(root/'.release-profile.json')['contact_email'],read_json(Path.home()/'.config/lexmount/browser-cli/credentials.json')['api_key']])
for p in site.rglob('*'):
    if p.is_file() and any(s.encode() in p.read_bytes() for s in secrets):raise RuntimeError('Private value in '+p.name)
archive=root/'dist/submission-site-v5.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(site.rglob('*')):
        if p.is_file():z.write(p,p.relative_to(site))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
sha=hashlib.sha256(archive.read_bytes()).hexdigest()
write_json(lab/'self-package.json',{'archive':str(archive.relative_to(root)),'sha256':sha,'bytes':archive.stat().st_size,'public_source_files':len(files),'private_value_scan':'passed'})
original=read_json(root/'runs/submission-proof/submission-state.json')
target={'id':'autolex','kind':'agent','title':original['title'],'url':original['materials'],'receipt':original['receipt'],'passcode':'NH8EPP',
 'archive':str(archive.relative_to(root)),'archive_sha256':sha,'source_file':'autolex/visual.py',
 'heading':'读资料、写代码，自动看图验收再投稿。','source_link':'在线查看最新源码与证据',
 'taskResult':'Agent本体第5版：DeepSeek生成、修复与截图评审，Lexmount取证与云浏览器发布，Docker隔离执行。自动视觉反馈闭环支持字号、间距、宽度和列数调整，新增代码自动换行、文件字节单位保持同行；失败停止投稿。本次只更新5件已投稿的独立成果：CSV/JSON、SQLite备份、URL解析、Git撤销、copy模块。它们保留原代码、来源、引用与结论，分别通过新的桌面/手机截图验收和无网络容器复跑，输出一致。材料按原链接更新，访客已核验报告及精确源码，官网原条目保存后重新打开确认，原收件编号均保留。136项Python和17项前端测试通过。另7件内部回顾样例未新增投稿。本条为Agent本体。模型视觉判断仍可能漏判或误判，截图覆盖有限，自动修复限于表现层，不宣称任意应用开发或整体提速。',
 'cloudRole':'Lexmount WebFetch读取官网与公开资料，保留来源快照；DeepSeek Flash生成Python、按测试及引用反馈修复，并直接评审PNG截图。表现层修订受参数范围与调用预算限制，浏览器另检溢出、锚点和字号。Lexmount云浏览器复用作者登录，在已有Yours链接更新材料，核验未登录访客的报告及源码，再对官网原作品保存修改并核验收件号。Codex协助开发和测试，作者提供方向、账号登录和授权。'}
write_json(lab/'self-targets.json',[target])
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'source_files':len(files),'existing_entry':target['receipt']}))
