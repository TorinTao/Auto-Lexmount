"""Update known existing materials/entries with durable journals; never add a work."""
import argparse
import fcntl
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import expect
from autolex.common import read_json,write_json,now,WorkflowError
from autolex.release_browser import ReleaseBrowser,CONTEST_URL,YOURS_URL
from scripts.update_self_entry import Sources


def validate_target(record):
    if not isinstance(record.get('title'),str) or not record['title'].strip():raise WorkflowError('Missing existing title')
    if not re.fullmatch(r'https://yours\.lexmount\.cn/artifact-site/s/[A-Za-z0-9_-]+',record.get('url','')):raise WorkflowError('Invalid existing work URL')
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',record.get('receipt','')):raise WorkflowError('Invalid original receipt')
    return record['url'].rsplit('/',1)[1]


def matching_archive(actual,expected):
    with zipfile.ZipFile(io.BytesIO(actual)) as remote,zipfile.ZipFile(io.BytesIO(expected)) as local:
        if set(remote.namelist())!=set(local.namelist()) or any(remote.read(n)!=local.read(n) for n in local.namelist()):
            raise WorkflowError('Hosted archive differs from the prepared materials')


def check_resume(record,digest):
    if record.get('archive_sha256')!=digest:raise WorkflowError('Archive changed since this update started')
    if record.get('status') not in ('prepared','materials_updated','guest_verified','entry_saved','complete'):
        raise WorkflowError('Remote outcome uncertain; inspect before attempting another write')


def open_entry(b,target):
    b.page.goto(CONTEST_URL,wait_until='domcontentloaded');expect(b.page.locator('#campus-work')).to_be_enabled(timeout=30000)
    b.page.locator('#campus-work').click()
    option=b.page.get_by_role('option',name=re.compile('^'+re.escape(target['title'])+r'(?: · 第 \d+ 版)?$'))
    if option.count()!=1:raise WorkflowError('Expected exactly one existing entry with the full title')
    option.click();b.page.get_by_role('button',name='查看／修改作品',exact=True).click()
    expect(b.page.locator('#workTitle')).to_have_value(target['title'])
    expect(b.page.locator('#evidenceLink')).to_have_value(target['url'])
    return b.page.locator('form').filter(has=b.page.locator('#workTitle'))


def update_one(b,target,proof):
    slug=validate_target(target);archive=Path(target['archive']);data=archive.read_bytes();digest=hashlib.sha256(data).hexdigest()
    if digest!=target['archive_sha256']:raise WorkflowError('Prepared archive hash mismatch')
    proof.mkdir(parents=True,exist_ok=True);proof.chmod(0o700);journal=proof/'state.json'
    record=read_json(journal) if journal.exists() else {'status':'prepared','at':now(),'archive_sha256':digest,
        'title':target['title'],'url':target['url'],'receipt':target['receipt'],'revision':target.get('revision')}
    check_resume(record,digest)
    if record['status']=='complete':return record
    def save(status,**values):record.update(status=status,updated_at=now(),**values);write_json(journal,record)
    if record['status']=='prepared':
        # Verify identity on the actual contest form before modifying its material URL.
        open_entry(b,target);b.capture(proof/'00-original-entry.png')
        b.page.goto(target['url'],wait_until='domcontentloaded');b.page.locator('iframe.fs-frame').wait_for(timeout=30000)
        write_json(proof/'page-snapshot.json',{'url':b.page.url,'buttons':b.page.get_by_role('button').all_text_contents()})
        old=b.context.request.get(YOURS_URL+'/api/sites/'+slug).json();version=old['version']['id']
        old_export=b.context.request.get(YOURS_URL+'/api/sites/'+slug+'/export',timeout=30000)
        if old_export.status!=200:raise WorkflowError('Cannot read original published archive')
        (proof/'prior-materials.zip').write_bytes(old_export.body())
        if target.get('kind')!='agent':
            with zipfile.ZipFile(io.BytesIO(old_export.body())) as z:
                parser=Sources();parser.feed(z.read('materials.html').decode())
                if parser.files.get('main.py')!=Path(target['source_file']).read_text():raise WorkflowError('Existing URL source differs from the submitted work')
        save('updating_materials',prior_version=version)
        try:
            response=b.context.request.post(YOURS_URL+'/api/sites/'+slug+'/versions?expected_version='+version,
                headers={'Origin':'https://yours.lexmount.cn'},multipart={'mode':'zip','file':{'name':archive.name,'mimeType':'application/zip','buffer':data}},timeout=60000)
            if response.status not in (200,201):raise WorkflowError('Version update returned HTTP '+str(response.status))
            current=b.context.request.get(YOURS_URL+'/api/sites/'+slug).json()
            if current['version']['id']==version:raise WorkflowError('New material version not observed')
            save('materials_updated',version_id=current['version']['id'])
        except Exception:
            if record['status']=='updating_materials':save('unknown_materials')
            raise
    if record['status']=='materials_updated':
        exported=b.context.request.get(YOURS_URL+'/api/sites/'+slug+'/export',timeout=30000)
        if exported.status!=200:raise WorkflowError('Cannot verify hosted materials')
        matching_archive(exported.body(),data)
        with zipfile.ZipFile(io.BytesIO(exported.body())) as z:
            parser=Sources();parser.feed(z.read('materials.html').decode())
        if target.get('kind')=='agent':
            checked=[]
            for folder in ['autolex','tests','scripts']:
                for p in sorted(Path(folder).rglob('*')):
                    if not p.is_file() or '__pycache__' in p.parts or p.suffix not in ('.py','.js','.cjs','.css','.html','.svg','.sh'):continue
                    if parser.files.get(str(p))!=p.read_text():raise WorkflowError('Hosted Agent source differs: '+str(p))
                    checked.append(str(p))
            write_json(proof/'source-verification.json',{'passed':True,'files':checked,'version_id':record['version_id']})
        guest=b.browser.new_context(viewport={'width':1440,'height':1050})
        try:
            page=guest.new_page();page.set_default_timeout(30000);page.goto(target['url'],wait_until='domcontentloaded')
            page.locator('#main-passcode').fill(target['passcode']);page.get_by_role('button',name='Open work',exact=True).click()
            frame=page.frame_locator('iframe.fs-frame');heading=target.get('heading',target['title'])
            try:expect(frame.locator('h1')).to_have_text(heading,timeout=3000)
            except Exception:frame.get_by_text('index.html',exact=True).click()
            expect(frame.locator('h1')).to_have_text(heading)
            page.screenshot(path=str(proof/'01-guest-report.png'),full_page=True)
            frame.get_by_role('link',name=target.get('source_link','阅读本作品源码与运行证据 →'),exact=True).click()
            name='autolex/visual.py' if target.get('kind')=='agent' else 'main.py'
            source=frame.locator('details').filter(has=frame.get_by_text(name,exact=True));source.locator('summary').click()
            if source.locator('pre').text_content()!=Path(target['source_file']).read_text():raise WorkflowError('Guest source content mismatch')
            page.screenshot(path=str(proof/'02-guest-source.png'),full_page=True)
            save('guest_verified',guest_verified=True,archive_verified=True)
        finally:guest.close()
    if record['status']=='guest_verified':
        form=open_entry(b,target)
        for field in ['taskResult','cloudRole']:
            value=target[field];element=b.page.locator('#'+field);maximum=element.get_attribute('maxlength')
            if maximum and len(value)>int(maximum):raise WorkflowError('Form text exceeds maximum')
            element.fill(value)
        if not form.evaluate('(f)=>f.checkValidity()'):raise WorkflowError('Contest form validation failed')
        b.capture(proof/'03-before-save.png');save('saving_entry')
        try:
            form.get_by_role('button',name='保存修改',exact=True).click()
            b.page.get_by_text('作品已收到',exact=True).wait_for(timeout=30000)
            body=b.page.locator('body').inner_text()
            if target['receipt'] not in body:raise WorkflowError('Original receipt not present after update')
            save('entry_saved',receipt_preserved=True)
        except Exception:
            save('unknown_entry');raise
    if record['status']=='entry_saved':
        # Screenshots and reloads may be retried without sending the form again.
        b.capture(proof/'04-saved-receipt.png')
        open_entry(b,target)
        for field in ['taskResult','cloudRole']:expect(b.page.locator('#'+field)).to_have_value(target[field])
        save('complete',reloaded_content_matches=True)
    return record


def main():
    p=argparse.ArgumentParser();p.add_argument('--targets',required=True);p.add_argument('--send',action='store_true');args=p.parse_args()
    targets=read_json(args.targets)
    if not args.send:print(json.dumps({'prepared':len(targets),'existing_entries_only':True}));return
    lab=Path('runs/resubmission-lab');done=[]
    with Path('runs/.release.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise WorkflowError('Another release is active') from None
        with ReleaseBrowser(read_json('.release-profile.json')) as b:
            for target in targets:
                print('UPDATE',target['id'],flush=True)
                result=update_one(b,target,lab/'updates'/target['id']);done.append(result)
                write_json(lab/(Path(args.targets).stem+'-results.json'),done)
                print('COMPLETE',target['id'],result['receipt'],flush=True)
if __name__=='__main__':main()
