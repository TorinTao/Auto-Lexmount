"""Publish the self showcase as a direct-entry website and verify the guest UI."""
import argparse
import base64
import fcntl
import hashlib
import json
import sys
import time
import uuid
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import expect
from autolex.common import read_json,write_json,WorkflowError,now
from autolex.release_browser import ReleaseBrowser

parser=argparse.ArgumentParser()
parser.add_argument('--proof',default='runs/showcase-github-only')
args=parser.parse_args();root=Path.cwd();proof=root/args.proof;journal=proof/'deployment.json'
if journal.exists():raise WorkflowError('Publication already attempted; inspect the saved outcome before retrying')
build=read_json(proof/'build.json');identity=read_json(root/'runs/self-entry-current.json')
assert read_json(proof/'browser-checks.json')['passed']
assert build['details_page_removed']
assert identity['url']==build['target_url']=='https://yours.lexmount.cn/artifact-site/s/ct83Wy9aja_U'
archive=root/build['archive'];assert hashlib.sha256(archive.read_bytes()).hexdigest()==build['sha256']
repo=build['github_url'];key='autolex-showcase-'+str(uuid.uuid4())
with (root/'runs/.release.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with ReleaseBrowser(read_json(root/'.release-profile.json')) as b:
        p=b.page;p.goto(identity['url'],wait_until='domcontentloaded');p.locator('iframe.fs-frame').wait_for()
        def request(path,method='GET',body=None,binary=None,idempotency=None):
            for attempt in range(3):
                response=p.evaluate('''async(a)=>{const headers={};let body;
                    if(a.binary!==null){headers['Content-Type']='application/octet-stream';body=Uint8Array.from(atob(a.binary),c=>c.charCodeAt(0))}
                    else if(a.body!==null){headers['Content-Type']='application/json';body=JSON.stringify(a.body)}
                    if(a.key)headers['idempotency-key']=a.key;
                    const r=await fetch('/artifact-site/api'+a.path,{method:a.method,headers,body});
                    return {status:r.status,retryAfter:r.headers.get('retry-after'),body:await r.json().catch(()=>({}))}}''',
                    {'path':path,'method':method,'body':body,'binary':base64.b64encode(binary).decode() if binary is not None else None,'key':idempotency})
                if response['status']!=429:return response
                if attempt<2:
                    delay=max(45,int(response['retryAfter'])) if (response['retryAfter'] or '').isdigit() else 45
                    if delay>60:raise WorkflowError('Rate limit requires a longer pause; inspect journal before resuming')
                    print('Rate limited; waiting before retrying the same operation.',flush=True);time.sleep(delay)
            raise WorkflowError('Rate limit persists; inspect journal before resuming')
        meta=request('/sites/ct83Wy9aja_U');assert meta['status']==200
        prior=meta['body']['version']['id']
        assert prior==identity['showcase_version'],'Remote version changed since last verified update'
        write_json(proof/'before.json',{'version_id':prior,'archive':identity['showcase_archive']})
        record={'status':'staging','url':identity['url'],'prior_version':prior,'archive':build['archive'],
                'archive_sha256':build['sha256'],'idempotency_key':key,'at':now(),'method':'native-tree-upload'}
        write_json(journal,record)
        started=request('/uploads','POST',{'slug':'ct83Wy9aja_U'},idempotency=key+'-start')
        if started['status']!=201:raise WorkflowError('Staging returned HTTP '+str(started['status']))
        upload=started['body']['versionId'];record['upload_id']=upload;write_json(journal,record)
        with zipfile.ZipFile(archive) as z:
            assert set(z.namelist())==set(build['file_hashes'])
            assert 'materials.html' not in z.namelist() and 'source.zip' not in z.namelist()
            for name in z.namelist():
                r=request('/uploads/'+upload+'/files/'+name,'PUT',binary=z.read(name))
                if r['status'] not in (200,201,204):raise WorkflowError('File staging failed: '+name)
        record['status']='committing';write_json(journal,record)
        r=request('/uploads/'+upload+'/commit?expected_version='+prior,'POST',{'official':False},idempotency=key)
        if r['status']!=201:raise WorkflowError('Commit returned HTTP '+str(r['status']))
        record.update(status='published',version_id=r['body']['versionId']);write_json(journal,record)
        print('Published; verifying the live page.',flush=True)
        meta=request('/sites/ct83Wy9aja_U');assert meta['status']==200;meta=meta['body']
        assert meta['version']['id']==record['version_id'] and meta['version']['entry']=='index.html'
        paths={item if isinstance(item,str) else item.get('path',item.get('name')) for item in meta['files']}
        assert paths==set(build['file_hashes']), 'Hosted file inventory differs'
        # Editor metadata returns the original entry; preview rendering rewrites asset URLs.
        assert hashlib.sha256(meta['content'].encode()).hexdigest()==build['file_hashes']['index.html']
        guest=b.browser.new_context(viewport={'width':1440,'height':1050})
        try:
            page=guest.new_page();page.set_default_timeout(30000)
            page.goto(identity['url'],wait_until='domcontentloaded')
            page.locator('#main-passcode').fill('NH8EPP');page.get_by_role('button',name='Open work',exact=True).click()
            frame=page.frame_locator('iframe.fs-frame');expect(frame.locator('h1')).to_have_text('你动动手指，它跑完流程。')
            link=frame.locator('.site-header .github-link');expect(link).to_have_attribute('href',repo)
            expect(link).to_have_attribute('target','_blank');expect(frame.locator('.nav-proof')).to_have_count(0)
            for label,url in [('GitHub 源码',repo),('在线演示',build['demo_url'])]:
                action=frame.locator('.hero .actions').get_by_role('link',name=label)
                expect(action).to_have_attribute('href',url)
                expect(action).to_have_attribute('target','_blank')
                expect(action).to_have_attribute('rel','noopener noreferrer')

            expect(frame.get_by_text('想看细节',exact=True)).to_have_count(0)
            assert frame.locator('a[href*="materials.html"]').count()==0
            for label,w,h in [('desktop',1440,1050),('mobile',390,844),('narrow',320,760)]:
                page.set_viewport_size({'width':w,'height':h});expect(link).to_be_visible()
                assert not frame.locator('html').evaluate('(e)=>e.scrollWidth>innerWidth')
                assert link.evaluate('(e)=>e.getBoundingClientRect().height')>=44
                page.screenshot(path=str(proof/('hosted-'+label+'.png')))
            page.set_viewport_size({'width':1440,'height':1050})
            frame.locator('#step-4').click();expect(frame.locator('#step-title')).to_have_text('做出来，也得让人看得懂。')
            for button in frame.locator('[data-preview]').all():
                button.click();expect(frame.locator('#preview-dialog')).to_be_visible();frame.locator('#close-preview').click()
            hashes=frame.locator('body').evaluate('''async()=>{
                const urls=new Set([...document.querySelectorAll('script[src],link[href],img[src]')].map(e=>e.src||e.href).filter(Boolean));const out={};
                for(const url of urls){const name=decodeURIComponent(new URL(url).pathname.split('/').pop());
                  if(!/\\.(png|svg|css|js)$/.test(name))continue;
                  const r=await fetch(url);if(!r.ok)throw Error('Asset unavailable');
                  const hash=await crypto.subtle.digest('SHA-256',await r.arrayBuffer());out[name]=[...new Uint8Array(hash)].map(b=>b.toString(16).padStart(2,'0')).join('');}
                return out;}''')
            expected={name:sha for name,sha in build['file_hashes'].items() if name!='index.html'}
            assert hashes==expected,'Live assets differ from build'
            record.update(status='verified',verified_at=now(),direct_home=True,details_page_removed=True,
                          github_link_verified=True,hero_github_and_demo_links_verified=True,responsive_views=3,all_files_verified=True,verified_files=len(build['file_hashes']))
            write_json(journal,record)
        finally:guest.close()
        identity.update(showcase_version=record['version_id'],showcase_proof=str(journal.relative_to(root)),
                        showcase_archive=build['archive'],showcase_verified_at=record['verified_at'],showcase_entry='index.html')
        write_json(root/'runs/self-entry-current.json',identity)
        print(json.dumps({'status':'verified','url':identity['url'],'version':record['version_id']}),flush=True)
