"""Update only the existing Yours showcase; preserve sharing and contest form copy."""
import fcntl
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import expect
from autolex.common import read_json,write_json,WorkflowError,now
from autolex.release_browser import ReleaseBrowser,YOURS_URL
from scripts.resubmit_existing import matching_archive,open_entry
from scripts.update_self_entry import Sources

root=Path.cwd();proof=root/'runs/yours-redesign';journal=proof/'deployment.json'
if journal.exists():raise WorkflowError('Deployment already attempted; inspect the saved outcome before retry')
assert read_json(proof/'browser-checks.json')['passed']
build=read_json(proof/'build.json');archive=root/build['archive'];data=archive.read_bytes()
if hashlib.sha256(data).hexdigest()!=build['sha256']:raise WorkflowError('Build archive changed')
identity=read_json(root/'runs/self-entry-current.json');form_copy=read_json(root/identity['copy'])
with (root/'runs/.release.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with ReleaseBrowser(read_json(root/'.release-profile.json')) as b:
        b.page.goto(identity['url'],wait_until='domcontentloaded');b.page.locator('iframe.fs-frame').wait_for(timeout=30000)
        write_json(proof/'prepublish-page.json',{'url':b.page.url,'buttons':b.page.get_by_role('button').all_text_contents()})
        old=b.context.request.get(YOURS_URL+'/api/sites/ct83Wy9aja_U').json();version=old['version']['id']
        if version!=read_json(proof/'before.json')['version_id']:raise WorkflowError('Hosted version changed since inspection')
        record={'status':'updating','url':identity['url'],'prior_version':version,'archive_sha256':build['sha256'],'at':now(),'scope':'Yours public showcase redesign only; existing form fields preserved'}
        write_json(journal,record)
        try:
            response=b.context.request.post(YOURS_URL+'/api/sites/ct83Wy9aja_U/versions?expected_version='+version,
              headers={'Origin':'https://yours.lexmount.cn'},multipart={'mode':'zip','file':{'name':'Auto-Lexmount-showcase.zip','mimeType':'application/zip','buffer':data}},timeout=60000)
            if response.status not in (200,201):raise WorkflowError('Yours returned HTTP '+str(response.status))
            current=b.context.request.get(YOURS_URL+'/api/sites/ct83Wy9aja_U').json()
            if current['version']['id']==version:raise WorkflowError('New version not observed')
            record.update(status='published',version_id=current['version']['id']);write_json(journal,record)
        except Exception:
            if record['status']=='updating':record['status']='unknown';write_json(journal,record)
            raise
        exported=b.context.request.get(YOURS_URL+'/api/sites/ct83Wy9aja_U/export',timeout=30000)
        if exported.status!=200:raise WorkflowError('Cannot verify hosted archive')
        matching_archive(exported.body(),data)
        with zipfile.ZipFile(io.BytesIO(exported.body())) as z:
            parser=Sources();parser.feed(z.read('materials.html').decode())
        checked=[]
        for name in build['files']:
            path=root/name
            if parser.files.get(name)!=path.read_text():raise WorkflowError('Hosted source or evidence differs: '+name)
            checked.append(name)
        write_json(proof/'hosted-source-verification.json',{'passed':True,'files':checked,'version_id':record['version_id']})
        guest=b.browser.new_context(viewport={'width':1440,'height':1050})
        try:
            page=guest.new_page();page.set_default_timeout(30000);page.goto(identity['url'],wait_until='domcontentloaded')
            page.locator('#main-passcode').fill('NH8EPP');page.get_by_role('button',name='Open work',exact=True).click()
            frame=page.frame_locator('iframe.fs-frame')
            try:expect(frame.locator('h1')).to_have_text('你动动手指，它跑完流程。',timeout=4000)
            except Exception:frame.get_by_text('index.html',exact=True).click()
            expect(frame.locator('h1')).to_have_text('你动动手指，它跑完流程。')
            expect(frame.locator('.experiment')).to_contain_text('后续测试提交会按约定加上标记')
            # Native model-explanation demo must work inside the hosted sandbox too.
            frame.locator('#step-4').click();expect(frame.locator('#step-title')).to_have_text('代码能跑，页面也得能看。')
            frame.locator('#step-5').click();expect(frame.locator('#step-title')).to_have_text('材料准备好，获得授权后交作业。')
            frame.locator('#step-0').click()
            frame.locator('[data-preview]').first.click();expect(frame.locator('#preview-dialog')).to_be_visible();frame.locator('#close-preview').click()
            for label,width,height in [('desktop',1440,1050),('mobile',390,844)]:
                page.set_viewport_size({'width':width,'height':height})
                frame.locator('body').evaluate('()=>window.scrollTo(0,0)')
                assert not frame.locator('html').evaluate('(e)=>e.scrollWidth>innerWidth'),label
                page.screenshot(path=str(proof/('hosted-'+label+'.png')))
            frame.locator('a[href="materials.html"]').first.click()
            expect(frame.locator('h1')).to_have_text('想看它有没有吹牛？记录都在这里。')
            frame.locator('#source-search').fill('autolex/visual.py');expect(frame.locator('.source-file:not([hidden])')).to_have_count(1)
            selected=frame.locator('.source-file:not([hidden])');selected.locator('summary').click()
            if selected.locator('pre').text_content()!=(root/'autolex/visual.py').read_text():raise WorkflowError('Guest source mismatch')
            page.screenshot(path=str(proof/'hosted-source.png'))
            record.update(guest_verified=True,hosted_interactions_verified=True,archive_verified=True)
            write_json(journal,record)
        finally:guest.close()
        # The newly written, entertainment-facing contest copy must still be intact.
        open_entry(b,identity)
        for field,value in form_copy.items():expect(b.page.locator('#'+field)).to_have_value(value)
        record.update(status='verified',verified_at=now(),contest_copy_unchanged=True,source_files_verified=len(checked))
        write_json(journal,record)
        print(json.dumps({'status':'verified','url':identity['url'],'version_id':record['version_id'],'guest_verified':True,'contest_copy_unchanged':True,'source_files_verified':len(checked)}),flush=True)
