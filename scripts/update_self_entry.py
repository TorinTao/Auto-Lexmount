"""Update the existing Auto Lexmount material version and existing contest entry."""
import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import expect
from autolex.release_browser import ReleaseBrowser, CONTEST_URL, YOURS_URL
from autolex.common import read_json,write_json,now,WorkflowError

class Sources(HTMLParser):
    def __init__(self):super().__init__();self.mode=None;self.name='';self.parts=[];self.files={}
    def handle_starttag(self,tag,attrs):
        if tag in ('summary','pre'):self.mode=tag;self.parts=[]
    def handle_data(self,text):
        if self.mode:self.parts.append(text)
    def handle_endtag(self,tag):
        if tag==self.mode:
            if tag=='summary':self.name=''.join(self.parts)
            else:self.files[self.name]=''.join(self.parts)
            self.mode=None

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--send',action='store_true');args=parser.parse_args()
    root=Path.cwd();proof=root/'runs/visual-release-lab/self-update-final';proof.mkdir(parents=True,exist_ok=True);proof.chmod(0o700)
    archive=root/'dist/submission-site-v4.zip';journal=proof/'state.json'
    if not args.send:print(json.dumps({'prepared':archive.is_file(),'target':'existing Agent entry'}));return
    if journal.exists():raise WorkflowError('An update attempt already exists; inspect the remote outcome before repeating')
    slug='ct83Wy9aja_U';url=YOURS_URL+'/s/'+slug;receipt='e15da2e1-f41e-4b96-beae-1953f1dbd6fb'
    live=read_json(root/'runs/agent-copy-visual/release-state.json');assert live['status']=='submitted'
    title=read_json(root/'runs/submission-draft/fields.json')['workTitle']
    with ReleaseBrowser(read_json('.release-profile.json')) as b:
        b.page.goto(url,wait_until='domcontentloaded')
        b.page.locator('iframe.fs-frame').wait_for(timeout=30000)
        b.capture(proof/'00-before-update.png')
        write_json(proof/'page-snapshot.json',{'url':b.page.url,'buttons':b.page.get_by_role('button').all_text_contents()})
        old=b.context.request.get(YOURS_URL+'/api/sites/'+slug).json();version=old['version']['id']
        record={'status':'updating','at':now(),'url':url,'prior_version':version,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
        write_json(journal,record)
        try:
            response=b.context.request.post(YOURS_URL+'/api/sites/'+slug+'/versions?expected_version='+version,
                headers={'Origin':'https://yours.lexmount.cn'},multipart={'mode':'zip','file':{'name':'Auto-Lexmount-v4.zip','mimeType':'application/zip','buffer':archive.read_bytes()}},timeout=60000)
            if response.status not in (200,201):raise WorkflowError('Version update returned HTTP '+str(response.status))
            current=b.context.request.get(YOURS_URL+'/api/sites/'+slug).json()
            if current['version']['id']==version:raise WorkflowError('Updated version not visible; inspect before retry')
            record.update(status='updated',version_id=current['version']['id']);write_json(journal,record)
        except Exception:
            if record['status']=='updating':record.update(status='unknown');write_json(journal,record)
            raise
        exported=b.context.request.get(YOURS_URL+'/api/sites/'+slug+'/export',timeout=30000)
        if exported.status!=200:raise WorkflowError('Cannot verify exported source')
        with zipfile.ZipFile(io.BytesIO(exported.body())) as z:
            parser=Sources();parser.feed(z.read('materials.html').decode())
            with zipfile.ZipFile(archive) as local:
                if set(z.namelist())!=set(local.namelist()) or any(z.read(n)!=local.read(n) for n in local.namelist()):raise WorkflowError('Hosted archive differs from the prepared materials')
        checked=[]
        for directory in ['autolex','tests','scripts']:
            for p in sorted((root/directory).rglob('*')):
                if not p.is_file() or '__pycache__' in p.parts or p.suffix not in ('.py','.js','.cjs','.html','.css','.svg','.sh'):continue
                name=str(p.relative_to(root))
                if parser.files.get(name)!=p.read_text():raise WorkflowError('Hosted source differs: '+name)
                checked.append(name)
        write_json(proof/'source-verification.json',{'all_match':True,'files':checked,'version':record['version_id']})
        guest=b.browser.new_context(viewport={'width':1440,'height':1050})
        try:
            p=guest.new_page();p.set_default_timeout(30000);p.goto(url,wait_until='domcontentloaded')
            p.locator('#main-passcode').fill('NH8EPP');p.get_by_role('button',name='Open work',exact=True).click()
            frame=p.frame_locator('iframe.fs-frame')
            try:expect(frame.locator('h1')).to_have_text('读资料、写代码，自动看图验收再投稿。',timeout=3000)
            except Exception:frame.get_by_text('index.html',exact=True).click()
            expect(frame.locator('h1')).to_have_text('读资料、写代码，自动看图验收再投稿。')
            p.screenshot(path=str(proof/'01-guest-updated.png'),full_page=True)
            frame.get_by_role('link',name='在线查看最新源码与证据',exact=True).click()
            expect(frame.locator('h1')).to_have_text('最新源码与自动视觉验收证据')
            source=frame.locator('details').filter(has=frame.get_by_text('autolex/visual.py',exact=True));source.locator('summary').click()
            if source.locator('pre').text_content()!=(root/'autolex/visual.py').read_text():raise WorkflowError('Guest source mismatch')
            p.screenshot(path=str(proof/'02-guest-visual-source.png'),full_page=True)
            record['guest_verified']=True;write_json(journal,record)
        finally:guest.close()
        b.page.goto(CONTEST_URL,wait_until='domcontentloaded');expect(b.page.locator('#campus-work')).to_be_enabled(timeout=30000)
        b.page.locator('#campus-work').click();b.page.get_by_role('option',name=re.compile('^Auto Lexmount')).click()
        b.page.get_by_role('button',name='查看／修改作品',exact=True).click()
        expect(b.page.locator('#workTitle')).to_have_value(title)
        expect(b.page.locator('#evidenceLink')).to_have_value(url)
        result=('Agent 本体第4版：DeepSeek 负责选题、代码生成和修复；Lexmount 抓取官网与资料，Docker 隔离执行。新增自动视觉验收：桌面/手机共8张截图直接发送DeepSeek，结合溢出、锚点、字号检查；发现阅读障碍后自动调整受限制的表现层设置并截图复验，最多修复两次，失败停止投稿。两个独立故障夹具均完成失败→修复→通过；字号夹具曾被模型漏判，由浏览器规则挡住。130项Python与17项前端测试通过。七主题实验最终68项工作流、40项独立输入检查通过。本轮浅拷贝/深拷贝指南由单条命令完成真实生成、3次代码修复、测试、自动视觉验收、Yours发布、无登录访客源码核验与官方收件，编号：'+live['receipt']['id']+'。现有五件独立作品的链接和回执见材料页。本条仍是Agent本体；截图为抽样验收，模型可能漏判。当前限于公开资料报告与表现层修复，不宣称任意应用开发或性能提速。')
        cloud='Lexmount WebFetch读取活动页与公开资料并保留快照。DeepSeek Flash生成Python、按测试和引用反馈修复，直接评审PNG截图并提出受限制的样式调整；视觉调用共用任务预算。Lexmount云浏览器复用作者登录，将生成作品独立上传Yours、设置分享、核验访客报告和精确源码，再填写官网并保存回执。Codex协助开发Agent与测试，作者提供方向、登录和授权。'
        for field,value in [('taskResult',result),('cloudRole',cloud)]:
            element=b.page.locator('#'+field);limit=element.get_attribute('maxlength')
            if limit and len(value)>int(limit):raise WorkflowError('Form text too long')
            element.fill(value)
        form=b.page.locator('form').filter(has=b.page.locator('#workTitle'))
        if not form.evaluate('(f)=>f.checkValidity()'):raise WorkflowError('Invalid contest form')
        b.capture(proof/'03-before-save.png')
        record.update(status='saving',receipt_id=receipt);write_json(journal,record)
        try:
            form.get_by_role('button',name='保存修改',exact=True).click()
            b.page.get_by_text('作品已收到',exact=True).wait_for(timeout=30000)
            if receipt not in b.page.locator('body').inner_text():raise WorkflowError('Original receipt missing')
            record.update(status='saved');write_json(journal,record)
        except Exception:
            record.update(status='unknown_entry_save');write_json(journal,record);raise
        b.capture(proof/'04-updated-receipt.png')
        b.page.reload(wait_until='domcontentloaded');expect(b.page.locator('#campus-work')).to_be_enabled(timeout=30000)
        b.page.locator('#campus-work').click();b.page.get_by_role('option',name=re.compile('^Auto Lexmount')).click()
        b.page.get_by_role('button',name='查看／修改作品',exact=True).click()
        expect(b.page.locator('#taskResult')).to_have_value(result)
        record['reloaded_content_matches']=True;write_json(journal,record)
        print(json.dumps({'status':record['status'],'url':url,'receipt':receipt,'source_files':len(checked),'guest_verified':True,'reloaded_content_matches':True}),flush=True)

if __name__=='__main__':main()
