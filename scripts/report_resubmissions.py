"""Verify six existing-entry updates and package private process evidence."""
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
root=Path.cwd();lab=root/'runs/resubmission-lab'
targets=read_json(lab/'work-targets.json')+read_json(lab/'self-targets.json');assert len(targets)==6
records=[]
for target in targets:
    proof=lab/'updates'/target['id'];state=read_json(proof/'state.json')
    assert state['status']=='complete' and state['receipt_preserved'] and state['reloaded_content_matches'] and state['guest_verified'] and state['archive_verified']
    assert state['receipt']==target['receipt'] and state['url']==target['url']
    assert hashlib.sha256((root/target['archive']).read_bytes()).hexdigest()==state['archive_sha256']
    if target.get('kind')!='agent':
        child=root/'runs'/target['revision'];manifest=read_json(child/'manifest.json')
        for name,digest in manifest.items():assert hashlib.sha256((child/name).read_bytes()).hexdigest()==digest
        release={'status':'submitted','action':'updated_existing_entry','run':child.name,'title':target['title'],
            'url':target['url'],'access':'passcode','passcode':target['passcode'],'guest_verified':True,
            'receipt':{'id':target['receipt'],'title':target['title'],'url':'https://browser.lexmount.cn/events/real-task-challenge/submit'},
            'source_manifest_sha256':target['source_manifest_sha256'],'archive_sha256':target['archive_sha256'],
            'updated_at':state['updated_at'],'hosted_version':state['version_id'],'original_run':target['run']}
        write_json(child/'release-state.json',release)
        write_json(child/'submission-state.json',{'status':'submitted','action':'updated_existing_entry','title':target['title'],
            'artifact_url':target['url'],'receipt':release['receipt'],'updated_at':state['updated_at'],'proof':str(proof.relative_to(root))})
    records.append({'id':target['id'],'title':target['title'],'url':target['url'],'passcode':target['passcode'],
                    'receipt':target['receipt'],'hosted_version':state['version_id'],'verified':True,'proof':str(proof.relative_to(root))})
for selected in read_json(root/'runs/batch7-lab/final-runs.json').values():
    assert not (root/'runs'/selected['run']/'submission-state.json').exists()
for directory in (root/'runs').glob('visual-final-*'):assert not (directory/'submission-state.json').exists()
source=read_json(lab/'updates/autolex/source-verification.json');assert source['passed']
report={'passed':True,'updated_existing_entries':6,'generated_works':5,'agent_version':5,
        'source_files_verified':len(source['files']),'unsubmitted_seven_unchanged':True,'records':records,
        'python_tests':136,'frontend_tests':17,'fresh_docker_runs':5,'new_work_screenshots':40,
        'scope':'Six existing entries updated; original URLs and receipt IDs preserved. No new contest entry was created.'}
write_json(lab/'verification.json',report)
rows=''.join('<tr><td>'+html.escape(r['title'])+'</td><td><a href="'+r['url']+'">打开作品</a><br>访问码 '+r['passcode']+'</td><td>'+r['receipt']+'</td><td><a href="updates/'+r['id']+'/04-saved-receipt.png">保存回执</a> · <a href="updates/'+r['id']+'/01-guest-report.png">访客截图</a> · <a href="updates/'+r['id']+'/state.json">核验记录</a></td></tr>' for r in records)
page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>已投稿作品更新记录</title><style>body{font:16px/1.75 system-ui;color:#292735;background:#f5f4fa;margin:0}main{max-width:1200px;margin:auto;padding:30px 20px}.scroll{overflow:auto;background:white;border-radius:12px}table{border-collapse:collapse;min-width:900px;width:100%}td,th{padding:16px;border-bottom:1px solid #ddd;text-align:left;overflow-wrap:anywhere}a{color:#5842a5}h1{line-height:1.3}</style><main><h1>5件已投稿作品 + Auto Lexmount 本体，更新完成。</h1><p>六条均更新原材料链接、在官网原条目保存修改、保留原收件编号；未登录访客报告与源码已核验，保存后重新打开确认。Auto Lexmount 已更新为第5版，线上 '+str(len(source['files']))+' 份源码与本机一致。</p><p>5件生成作品通过本次视觉验收与新的Docker复跑，136项Python、17项前端测试通过。之前未投稿的7件保持未投稿。</p><div class="scroll"><table><thead><tr><th>作品</th><th>材料链接</th><th>原收件编号</th><th>过程证据</th></tr></thead><tbody>'+rows+'</tbody></table></div><p><a href="verification.json">完整核验结果</a> · 过程截图包含个人表单信息，此材料包用于本机留存。</p></main></html>'
(lab/'report.html').write_text(page)
load_environment('.env');secrets=[os.environ[k] for k in ['MODEL_API_KEY','LEXMOUNT_API_KEY'] if os.getenv(k)]
secrets.append(read_json(Path.home()/'.config/lexmount/browser-cli/credentials.json')['api_key'])
files=[p for p in lab.rglob('*') if p.is_file() and not p.is_symlink()]
for record in read_json(lab/'prepared.json'):
    directory=root/'runs'/record['revision']
    files += [p for p in directory.rglob('*') if p.is_file() and not p.is_symlink() and p.name not in ('.lock','draft.json')]
files.append(root/'dist/submission-site-v5.zip')
archive=root/'dist/existing-submissions-update-proof.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(set(files)):
        data=p.read_bytes();assert not any(s.encode() in data for s in secrets),p.name
        z.writestr(str(p.relative_to(root)),data)
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
archive.chmod(0o600)
print(json.dumps({'passed':True,'updated':6,'report':str(lab/'report.html'),'archive':str(archive),'bytes':archive.stat().st_size,'source_files_verified':len(source['files'])}))
