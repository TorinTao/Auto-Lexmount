"""Inspected Yours and Lexmount Challenge UI adapter, using a saved login context."""
import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

from .common import WorkflowError
from .release import CONTEST_URL, YOURS_URL
from .common import write_json


def publication_url(data):
    if not isinstance(data,dict):return None
    # The documented async upload poll returns the completed publication in result.
    result=data.get('result') if data.get('status')=='completed' else data
    if not isinstance(result,dict):return None
    slug=result.get('slug')
    if isinstance(slug,str) and re.fullmatch(r'[A-Za-z0-9_-]+',slug):
        return YOURS_URL+'/s/'+slug
    return None


class ReleaseBrowser:
    def __init__(self, profile):
        self.profile=profile
        self.cli=os.getenv('LEXMOUNT_BROWSER_CLI',str(Path.home()/'.agents/skills/lexmount-browser/bin/browser-cli'))
        self.session=None;self.playwright=None;self.browser=None

    def command(self,*args):
        result=subprocess.run([self.cli,*args],capture_output=True,text=True,timeout=60)
        try:data=json.loads(result.stdout)
        except ValueError:raise WorkflowError('Browser CLI returned invalid JSON') from None
        if result.returncode or not data.get('ok'):
            raise WorkflowError('Browser CLI failed; inspect login context and service availability')
        return data['data']

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        try:
            credentials=json.loads((Path.home()/'.config/lexmount/browser-cli/credentials.json').read_text())
            deadline=time.monotonic()+20
            while self.command('context','get','--context-id',self.profile['context_id']).get('status')=='locked':
                if time.monotonic()>=deadline:raise WorkflowError('Login context is still in use')
                time.sleep(1)
            self.session=self.command('session','create','--context-id',self.profile['context_id'],'--context-mode','read_write','--browser-mode','normal')
            self.playwright=sync_playwright().start()
            self.browser=self.playwright.chromium.connect_over_cdp(self.session['ws'],headers={'X-Api-Key':credentials['api_key'],'X-Project-Id':credentials['project_id']},timeout=30000)
            self.context=self.browser.contexts[0]
            self.page=self.context.new_page();self.page.set_default_timeout(20000)
            return self
        except Exception:
            self.__exit__(None,None,None)
            raise WorkflowError('Could not open the saved cloud-browser login context') from None

    def __exit__(self,*args):
        try:
            if self.browser:self.browser.close()
        finally:
            try:
                if self.playwright:self.playwright.stop()
            finally:
                if self.session:self.command('session','close','--session-id',self.session['session_id'])

    def capture(self,path):
        self.page.screenshot(path=str(path),full_page=True)

    def prepare_upload(self,archive,title):
        self.proof=Path(archive).parent
        self.page.goto(YOURS_URL,wait_until='domcontentloaded')
        self.page.locator('input[type=file]:not([webkitdirectory])').first.set_input_files({'name':title+'.zip','mimeType':'application/zip','buffer':Path(archive).read_bytes()})
        self.page.get_by_role('heading',name='Confirm upload',exact=True).wait_for()

    def publish(self, button='Upload'):
        # Archives are processed asynchronously. Read the actual creation/poll
        # result; a home-page navigation or popup is not the publication receipt.
        published=[];events=[];upload_ids=[]
        def response(response):
            if response.status not in (200,201,202) or not (response.url.startswith(YOURS_URL+'/api/uploads') or response.url.split('?')[0]==YOURS_URL+'/api/sites'):
                return
            try:data=response.json()
            except Exception:return
            events.append({'path':urlsplit(response.url).path,'http_status':response.status,'keys':list(data) if isinstance(data,dict) else [],'upload_status':data.get('status') if isinstance(data,dict) else None})
            write_json(self.proof/'publish-events.json',events)
            version=data.get('versionId') if isinstance(data,dict) else None
            if isinstance(version,str) and re.fullmatch(r'ver_[A-Za-z0-9]+',version):
                if not upload_ids:upload_ids.append(version)
                write_json(self.proof/'upload-operation.json',{'version_id':upload_ids[0]})
            url=publication_url(data)
            if url:
                published.append(url)
                write_json(self.proof/'publish-response.json',{'url':url,'response_url':response.url,'status':response.status})
        self.page.on('response',response)
        try:
            self.page.get_by_role('button',name=button,exact=True).click()
            deadline=time.monotonic()+90
            while not published and time.monotonic()<deadline:
                if upload_ids:
                    poll=self.context.request.get(YOURS_URL+'/api/uploads/'+upload_ids[0],timeout=15000)
                    if poll.status==200:
                        data=poll.json();url=publication_url(data)
                        if url:
                            published.append(url)
                            write_json(self.proof/'publish-response.json',{'url':url,'upload_id':upload_ids[0],'status':'completed'})
                            break
                        if data.get('status')=='failed':raise WorkflowError('Yours archive processing failed; inspect this upload job')
                self.page.wait_for_timeout(1500)
            if not published:raise WorkflowError('No completed publication response was observed')
            return {'url':published[-1]}
        finally:self.page.remove_listener('response',response)

    def share_and_verify(self,url,title,proof):
        from playwright.sync_api import expect
        self.page.goto(url,wait_until='domcontentloaded')
        expect(self.page.locator('iframe.fs-frame')).to_have_attribute('title',title+'.zip')
        self.page.get_by_role('button',name='Share',exact=True).click()
        self.page.locator('input[type=radio][value=passcode]').check()
        field=self.page.locator('input[id$="-code"]')
        expect(field).to_have_value(re.compile(r'^[A-Za-z0-9]{4,32}$'))
        passcode=field.input_value()
        self.capture(proof/'02-sharing.png')
        guest=self.browser.new_context(viewport={'width':1440,'height':1050})
        try:
            page=guest.new_page();page.set_default_timeout(20000)
            page.goto(url,wait_until='domcontentloaded')
            page.locator('#main-passcode').fill(passcode)
            page.get_by_role('button',name='Open work',exact=True).click()
            frame=page.frame_locator('iframe.fs-frame')
            frame.get_by_text('index.html',exact=True).click()
            expect(frame.locator('h1')).to_have_text(title)
            page.screenshot(path=str(proof/'02-guest-work.png'),full_page=True)
            frame.get_by_role('link',name='阅读本作品源码与运行证据 →',exact=True).click()
            expect(frame.locator('h1')).to_have_text(title+' · 源码与证据')
            source=frame.locator('details').filter(has=frame.get_by_text('main.py',exact=True))
            source.locator('summary').click()
            if source.locator('pre').text_content()!=(proof.parent/'main.py').read_text():
                raise WorkflowError('Published source does not match this generated work')
            page.screenshot(path=str(proof/'02-guest-code.png'),full_page=True)
        finally:guest.close()
        return {'access':'passcode','passcode':passcode,'guest_verified':True}

    def fill_contest(self,fields):
        from playwright.sync_api import expect
        self.page.goto(CONTEST_URL,wait_until='domcontentloaded')
        expect(self.page.locator('#campus-work')).to_be_enabled(timeout=30000)
        self.page.get_by_role('button',name='新增作品',exact=True).first.click()
        expect(self.page.locator('#campus-work')).to_contain_text('正在填写新作品')
        for key,value in fields.items():self.page.locator('#'+key).fill(value)
        for selector,label in [('#existingWork','本轮新开展的实践'),('#registrationStatus','已报名')]:
            self.page.locator(selector).click()
            self.page.get_by_role('option',name=label,exact=True).click()
        if self.page.locator('#careerContactConsent').get_attribute('aria-checked')!='false':
            raise WorkflowError('Unexpected optional contact consent; inspect the form')
        self.form=self.page.locator('form').filter(has=self.page.locator('#workTitle'))
        if not self.form.evaluate('(form)=>form.checkValidity()'):
            raise WorkflowError('Submission fields do not pass the website validation')
        self.submitted_title=fields['workTitle']
        if self.page.locator('#workTitle').input_value()!=self.submitted_title or self.page.locator('#evidenceLink').input_value()!=fields['evidenceLink']:
            raise WorkflowError('Contest title or artifact link does not match this run')

    def submit_contest(self):
        from playwright.sync_api import expect
        self.form.get_by_role('button',name='提交',exact=True).click()
        self.page.get_by_text('作品已收到',exact=True).wait_for(timeout=30000)
        expect(self.page.locator('#campus-work')).to_contain_text(self.submitted_title)
        body=self.page.locator('body').inner_text()
        match=re.search(r'收件编号[：:]\s*([0-9a-fA-F-]{36})',body)
        if not match:raise WorkflowError('Website did not display a receipt ID')
        return {'id':match.group(1),'title':self.submitted_title,'url':self.page.url}
