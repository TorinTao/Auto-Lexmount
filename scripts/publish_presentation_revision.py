"""Replace a known work's Yours materials after inspecting its source; no contest submission."""
import argparse
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
from scripts.resubmit_existing import matching_archive,validate_target
from scripts.update_self_entry import Sources


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--target',required=True);parser.add_argument('--run',required=True);parser.add_argument('--proof',required=True);args=parser.parse_args()
    target=read_json(args.target);root=Path(args.run);proof=Path(args.proof);proof.mkdir(exist_ok=True,parents=True)
    if not read_json(proof/'browser-checks.json')['passed']:raise WorkflowError('Browser checks required')
    slug=validate_target(target);journal=proof/'publication.json'
    if journal.exists():raise WorkflowError('Existing publication journal; inspect before retrying')
    archive=(root/'release/site.zip').read_bytes();draft=read_json(root/'release/draft.json')
    if draft['archive_sha256']!=hashlib.sha256(archive).hexdigest():raise WorkflowError('Archive changed')
    if draft['title']!=target['title']:raise WorkflowError('Work identity changed')
    headline=read_json(root/('reader.json' if (root/'reader.json').exists() else 'design.json'))['headline']
    with Path('runs/.release.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with ReleaseBrowser(read_json('.release-profile.json')) as b:
            b.page.goto(target['url'],wait_until='domcontentloaded');b.page.locator('iframe.fs-frame').wait_for(timeout=30000)
            write_json(proof/'prior-page.json',{'url':b.page.url,'buttons':b.page.get_by_role('button').all_text_contents()})
            old=b.context.request.get(YOURS_URL+'/api/sites/'+slug).json();version=old['version']['id']
            export=b.context.request.get(YOURS_URL+'/api/sites/'+slug+'/export')
            if export.status!=200:raise WorkflowError('Cannot back up original')
            (proof/'prior-site.zip').write_bytes(export.body())
            with zipfile.ZipFile(io.BytesIO(export.body())) as z:
                source=Sources();source.feed(z.read('materials.html').decode())
            if source.files.get('main.py')!=(root/'main.py').read_text():raise WorkflowError('Different published work source')
            record={'status':'updating','prior_version':version,'url':target['url'],'archive_sha256':draft['archive_sha256'],'at':now(),'scope':'Existing test work presentation only; no contest form submission'}
            write_json(journal,record)
            response=b.context.request.post(YOURS_URL+'/api/sites/'+slug+'/versions?expected_version='+version,headers={'Origin':'https://yours.lexmount.cn'},multipart={'mode':'zip','file':{'name':root.name+'.zip','mimeType':'application/zip','buffer':archive}},timeout=60000)
            if response.status not in (200,201):
                record.update(status='rate_limited' if response.status==429 else 'update_rejected',http_status=response.status,
                              retry_after=response.headers.get('retry-after'))
                try:
                    error=response.json()
                    # Response text is retained locally for diagnosing quotas, never as an instruction.
                    record['server_error']=error.get('message') or error.get('error') or error.get('code') if isinstance(error,dict) else None
                except Exception:pass
                write_json(journal,record)
                raise WorkflowError('Yours update HTTP '+str(response.status))
            current=b.context.request.get(YOURS_URL+'/api/sites/'+slug).json()
            if current['version']['id']==version:raise WorkflowError('New version not observed')
            record.update(status='published',version_id=current['version']['id']);write_json(journal,record)
            hosted=b.context.request.get(YOURS_URL+'/api/sites/'+slug+'/export')
            if hosted.status!=200:raise WorkflowError('Cannot verify export')
            matching_archive(hosted.body(),archive)
            guest=b.browser.new_context(viewport={'width':1440,'height':1050})
            try:
                page=guest.new_page();page.set_default_timeout(30000);page.goto(target['url'],wait_until='domcontentloaded')
                page.locator('#main-passcode').fill(target['passcode']);page.get_by_role('button',name='Open work',exact=True).click()
                frame=page.frame_locator('iframe.fs-frame')
                try:expect(frame.locator('h1')).to_have_text(headline,timeout=4000)
                except Exception:frame.get_by_text('index.html',exact=True).click()
                expect(frame.locator('h1')).to_have_text(headline)
                for label,width,height in [('desktop',1440,1050),('mobile',390,844),('narrow',320,844)]:
                    page.set_viewport_size({'width':width,'height':height});frame.locator('body').evaluate('()=>scrollTo(0,0)')
                    assert not frame.locator('html').evaluate('e=>e.scrollWidth>innerWidth')
                    page.screenshot(path=str(proof/('hosted-'+label+'.png')))
                frame.locator('.atlas a').first.click();frame.locator('.points summary').first.click();expect(frame.locator('.points blockquote').first).to_be_visible()
                if frame.locator('.production-notes').count():frame.locator('.production-notes > summary').click()
                frame.locator('a[href="materials.html"]').click()
                detail=frame.locator('details').filter(has=frame.get_by_text('main.py',exact=True));detail.locator('summary').click()
                if detail.locator('pre').text_content()!=(root/'main.py').read_text():raise WorkflowError('Guest source changed')
                record.update(status='verified',guest_verified=True,archive_verified=True,at=now());write_json(journal,record)
                print(json.dumps(record,ensure_ascii=False),flush=True)
            finally:guest.close()
if __name__=='__main__':main()
