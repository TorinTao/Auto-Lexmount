"""Capture the currently published examples, with version and image provenance."""
import argparse
import hashlib
import io
import json
import sys
import time
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import expect
from autolex.common import read_json, write_json, now, WorkflowError
from autolex.release_browser import ReleaseBrowser, YOURS_URL

parser = argparse.ArgumentParser()
parser.add_argument('--proof', default='runs/showcase-screenshots-refresh')
args = parser.parse_args()
root = Path.cwd(); proof = root / args.proof; proof.mkdir(parents=True, exist_ok=True)
records = read_json(root / 'runs/resubmission-lab/prepared.json')
manifest = read_json(proof/'screenshots.json') if (proof/'screenshots.json').exists() else {'captured_at': now(), 'source': 'live-yours-guest', 'works': {}}
with ReleaseBrowser(read_json(root / '.release-profile.json')) as b:
    for record in records:
        slug = record['url'].rsplit('/', 1)[-1]
        response = b.context.request.get(YOURS_URL + '/api/sites/' + slug)
        if response.status != 200: raise WorkflowError('Cannot inspect published work: ' + record['run'])
        meta = response.json(); version = meta['version']['id']
        previous=manifest['works'].get(record['run'])
        if previous and previous.get('capture_mode')=='content-only' and previous['version_id']==version and hashlib.sha256((root/previous['image']).read_bytes()).hexdigest()==previous['sha256']:
            print('Verified existing capture: '+record['run'],flush=True);continue
        if previous and previous['version_id']==version:
            index_hash=previous['index_sha256']
        else:
            for attempt in range(3):
                exported = b.context.request.get(YOURS_URL + '/api/sites/' + slug + '/export')
                if exported.status==200:break
                if exported.status not in (429,500,502,503,504):break
                time.sleep(5*(attempt+1))
            if exported.status != 200: raise WorkflowError('Cannot read published files: HTTP '+str(exported.status))
            with zipfile.ZipFile(io.BytesIO(exported.body())) as archive:
                index_hash=hashlib.sha256(archive.read('index.html')).hexdigest()
        guest = b.browser.new_context(viewport={'width':1440, 'height':1110})
        try:
            page = guest.new_page(); page.set_default_timeout(30000)
            page.goto(record['url'], wait_until='domcontentloaded')
            page.locator('#main-passcode').fill(record['passcode'])
            page.get_by_role('button', name='Open work', exact=True).click()
            frame = page.frame_locator('iframe.fs-frame')
            frame.locator('h1').wait_for()
            if meta['version']['entry'].endswith('directory.html'):
                frame.get_by_text('index.html', exact=True).click()
            expect(frame.locator('h1')).not_to_contain_text('.zip')
            heading = frame.locator('h1').inner_text()
            if not heading.strip(): raise WorkflowError('Missing work heading')
            # Open the authorized preview in a separate tab so platform buttons
            # cannot cover the work. Never persist its temporary signed URL.
            preview_url=page.locator('iframe.fs-frame').element_handle().content_frame().url
            preview=guest.new_page();preview.set_viewport_size({'width':1440,'height':1050})
            preview.goto(preview_url,wait_until='domcontentloaded')
            expect(preview.locator('h1')).to_have_text(heading)
            preview.locator('html').evaluate('(e)=>e.style.scrollBehavior="auto"')
            preview.locator('body').evaluate('async()=>{await document.fonts.ready;scrollTo({top:0,behavior:"instant"});await Promise.all([...document.images].map(i=>i.decode().catch(()=>{})))}')
            path = proof / (record['run'] + '.png')
            preview.screenshot(path=str(path))
            after = b.context.request.get(YOURS_URL + '/api/sites/' + slug).json()
            if after['version']['id'] != version: raise WorkflowError('Work changed during capture')
            dimensions = preview.locator('html').evaluate('()=>({width:innerWidth,height:innerHeight})')
            item = {'url':record['url'], 'version_id':version, 'title':heading,
                    'index_sha256':index_hash, 'capture_mode':'content-only',
                    'image':str(path.relative_to(root)), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'viewport':dimensions, 'captured_at':now()}
            manifest['works'][record['run']] = item
            write_json(proof/'screenshots.json',manifest)
            print(json.dumps({'run':record['run'],'version':version,'title':heading,'viewport':dimensions},ensure_ascii=False),flush=True)
        finally: guest.close()
assert len(manifest['works']) == 5
write_json(root/'runs/showcase-screenshots-current.json',manifest)
print('All five published work screenshots refreshed.',flush=True)
