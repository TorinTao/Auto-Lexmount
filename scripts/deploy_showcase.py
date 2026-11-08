"""Update only the existing Yours showcase; preserve sharing and contest form copy."""
import argparse
import uuid
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
from scripts.resubmit_existing import matching_archive
from scripts.update_self_entry import Sources

parser=argparse.ArgumentParser()
parser.add_argument('--proof',default='runs/autolex-public-refresh')
args=parser.parse_args()
root=Path.cwd();proof=root/args.proof;journal=proof/'deployment.json'
if journal.exists():raise WorkflowError('Deployment already attempted; inspect the saved outcome before retry')
assert read_json(proof/'browser-checks.json')['passed']
build=read_json(proof/'build.json');archive=root/build['archive'];data=archive.read_bytes()
if hashlib.sha256(data).hexdigest()!=build['sha256']:raise WorkflowError('Build archive changed')
identity=read_json(root/'runs/self-entry-current.json')
if identity['url']!='https://yours.lexmount.cn/artifact-site/s/ct83Wy9aja_U' or build['target_url']!=identity['url']:raise WorkflowError('Wrong Auto Lexmount target')
with (root/'runs/.release.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with ReleaseBrowser(read_json(root/'.release-profile.json')) as b:
        b.page.goto(identity['url'],wait_until='domcontentloaded');b.page.locator('iframe.fs-frame').wait_for(timeout=30000)
        write_json(proof/'prepublish-page.json',{'url':b.page.url,'buttons':b.page.get_by_role('button').all_text_contents()})
        for item in (build.get('screenshots') or {}).get('works',{}).values():
            slug=item['url'].rsplit('/',1)[-1]
            live=b.context.request.get(YOURS_URL+'/api/sites/'+slug).json()
            if live['version']['id']!=item['version_id']:raise WorkflowError('A featured work changed after its screenshot; refresh it first')
        old=b.context.request.get(YOURS_URL+'/api/sites/ct83Wy9aja_U').json();version=old['version']['id']
        before=b.context.request.get(YOURS_URL+'/api/sites/ct83Wy9aja_U/export',timeout=30000)
        if before.status!=200:raise WorkflowError('Cannot back up previous version')
        (proof/'before.zip').write_bytes(before.body())
        write_json(proof/'before.json',{'version_id':version,'url':identity['url']})
        record={'status':'updating','url':identity['url'],'prior_version':version,'archive_sha256':build['sha256'],'at':now(),'method':'native-tree-upload','scope':'Auto Lexmount self showcase; existing form fields preserved'}
        write_json(journal,record)
        try:
            # Upload a website tree without package metadata. ZIP/package uploads
            # generate a file-directory entry, adding an unnecessary index click.
            key='autolex-showcase-'+str(uuid.uuid4())
            record['idempotency_key']=key;write_json(journal,record)
            headers={'Origin':'https://yours.lexmount.cn','idempotency-key':key+'-start'}
            started=b.context.request.post(YOURS_URL+'/api/uploads',headers=headers,data={'slug':'ct83Wy9aja_U'})
            if started.status!=201:raise WorkflowError('Could not stage website tree: '+str(started.status))
            upload_id=started.json()['versionId'];record['upload_id']=upload_id;write_json(journal,record)
            with zipfile.ZipFile(io.BytesIO(data)) as content:
                for name in content.namelist():
                    if name.endswith('/'):continue
                    response=b.context.request.put(YOURS_URL+'/api/uploads/'+upload_id+'/files/'+name,
                        headers={'Origin':'https://yours.lexmount.cn','content-type':'application/octet-stream'},data=content.read(name))
                    if response.status not in (200,201,204):raise WorkflowError('Failed to stage '+name)
            record['status']='committing';write_json(journal,record)
            response=b.context.request.post(YOURS_URL+'/api/uploads/'+upload_id+'/commit?expected_version='+version,
                headers={'Origin':'https://yours.lexmount.cn','idempotency-key':key},data={'official':False},timeout=60000)
            if response.status!=201:raise WorkflowError('Website commit returned '+str(response.status))
            current=b.context.request.get(YOURS_URL+'/api/sites/ct83Wy9aja_U').json()
            if current['version']['id']!=response.json()['versionId']:raise WorkflowError('Published version changed')
            if current['version']['entry']!='index.html':raise WorkflowError('Website must open its homepage directly')
            record.update(status='published',version_id=current['version']['id']);write_json(journal,record)
        except Exception:
            if record['status'] in ('updating','committing'):record['status']='unknown';write_json(journal,record)
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
            # A fresh guest must see the homepage without opening a directory item.
            expect(frame.locator('h1')).to_have_text('你动动手指，它跑完流程。')
            expect(frame.locator('.hero-body')).to_contain_text('Auto Lexmount')
            expect(frame.locator('.experiment')).to_contain_text('后续测试提交会按约定加上标记')
            # Native model-explanation demo must work inside the hosted sandbox too.
            frame.locator('#step-4').click();expect(frame.locator('#step-title')).to_have_text('做出来，也得让人看得懂。')
            frame.locator('#step-5').click();expect(frame.locator('#step-title')).to_have_text('材料准备好，获得授权后交作业。')
            frame.locator('#step-0').click()
            for button in frame.locator('[data-preview]').all():
                button.click();expect(frame.locator('#preview-dialog')).to_be_visible()
                assert frame.locator('#preview-image').evaluate('(e)=>e.complete&&e.naturalWidth===1440&&e.naturalHeight===1050')
                frame.locator('#close-preview').click()
            frame.locator('#works-title').evaluate('(e)=>e.scrollIntoView({behavior:"instant"})')
            page.screenshot(path=str(proof/'hosted-work-gallery.png'))
            for label,width,height in [('desktop',1440,1050),('mobile',390,844),('narrow',320,760)]:
                page.set_viewport_size({'width':width,'height':height})
                frame.locator('body').evaluate('()=>window.scrollTo({top:0,behavior:"instant"})')
                assert not frame.locator('html').evaluate('(e)=>e.scrollWidth>innerWidth'),label
                page.screenshot(path=str(proof/('hosted-'+label+'.png')))
            page.set_viewport_size({'width':1440,'height':1050})
            frame.locator('.nav-proof').click()
            expect(frame.locator('h1')).to_have_text('想看它有没有吹牛？记录都在这里。')
            frame.locator('#source-search').fill('autolex/visual.py');expect(frame.locator('.source-file:not([hidden])')).to_have_count(1)
            selected=frame.locator('.source-file:not([hidden])');selected.locator('summary').click()
            if selected.locator('pre').text_content()!=(root/'autolex/visual.py').read_text():raise WorkflowError('Guest source mismatch')
            page.screenshot(path=str(proof/'hosted-source.png'))
            record.update(guest_verified=True,hosted_interactions_verified=True,archive_verified=True)
            write_json(journal,record)
        finally:guest.close()
        record.update(status='verified',verified_at=now(),direct_home=True,contest_form_written=False,source_files_verified=len(checked))
        write_json(journal,record)
        identity.update(showcase_version=record['version_id'],showcase_proof=str(journal.relative_to(root)),
            showcase_archive=build['archive'],showcase_verified_at=record['verified_at'],showcase_entry='index.html')
        write_json(root/'runs/self-entry-current.json',identity)
        print(json.dumps({'status':'verified','url':identity['url'],'version_id':record['version_id'],'guest_verified':True,'direct_home':True,'source_files_verified':len(checked)}),flush=True)
