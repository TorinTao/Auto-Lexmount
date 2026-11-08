"""Exercise the actual dashboard demo/revision/preview flow in an existing CDP browser."""
import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cdp', default='http://127.0.0.1:9229')
    parser.add_argument('--out', default='runs/dashboard-qa')
    args = parser.parse_args()
    target = Path(args.out); target.mkdir(parents=True, exist_ok=True)
    base = 'http://127.0.0.1:8765'
    def get(path):
        with urllib.request.urlopen(base+path, timeout=15) as response:
            return json.load(response)
    def relay(route):
        req = route.request
        headers = {k:v for k,v in req.headers.items() if k.lower() not in ('host','content-length','accept-encoding','connection')}
        request = urllib.request.Request(req.url, data=req.post_data_buffer, headers=headers, method=req.method)
        try:
            response = urllib.request.urlopen(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            route.fulfill(status=response.status, headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','transfer-encoding','connection')}, body=response.read())
    def ready(page, run_id):
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            detail=get('/api/runs/'+run_id)
            if detail['state']['status']=='ready':
                expect(page.locator('#run-status')).to_have_text('已完成')
                return detail
            if detail['state']['status']=='blocked':
                raise AssertionError(detail['state'].get('error'))
            page.wait_for_timeout(250)
        raise AssertionError('Demo did not finish')
    report={'kind':'browser interaction, DEMO only','checks':[]}
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(args.cdp)
        context=browser.new_context(viewport={'width':1440,'height':1050})
        context.route(base+'/**',relay)
        errors=[]
        context.on('page',lambda page:page.on('pageerror',lambda e:errors.append(str(e))))
        page=context.new_page();page.goto(base,wait_until='domcontentloaded')
        expect(page.locator('#quick-demo')).to_be_enabled(timeout=15000)
        with page.expect_response(lambda r:r.url==base+'/api/runs' and r.request.method=='POST') as response:
            page.locator('#quick-demo').click()
        parent=response.value.json()['id'];ready(page,parent)
        parent_hash=hashlib.sha256((Path('runs')/parent/'submission.zip').read_bytes()).hexdigest()
        report['parent']=parent
        with page.expect_popup() as popup:
            page.locator('#open-preview').click()
        preview=popup.value;preview.wait_for_load_state()
        expect(preview.locator('h1')).to_be_visible()
        assert preview.url==base+'/api/runs/'+parent+'/preview'
        assert preview.locator('body').evaluate('(e)=>getComputedStyle(e).fontFamily')!='"Times New Roman"'
        report['checks'].append('Actual preview button opens a styled report')
        preview.close()
        page.locator('#revise-task').click()
        expect(page.locator('#revision-of')).to_have_value(parent)
        assert page.locator('#task-url').evaluate('(e)=>e.readOnly')
        page.locator('#task-feedback').fill('保留当前主题，检查新版本和父版本的关联。此处是离线界面流程测试。')
        page.screenshot(path=str(target/'revision-desktop.png'))
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(target/'revision-mobile.png'))
        assert not page.evaluate('()=>document.documentElement.scrollWidth>innerWidth')
        submit_bounds=page.locator('#submit-task').bounding_box()
        assert 0 <= submit_bounds['y'] and submit_bounds['y']+submit_bounds['height']<=844
        with page.expect_response(lambda r:r.url==base+'/api/runs' and r.request.method=='POST') as response:
            page.locator('#submit-task').click()
        child=response.value.json()['id'];detail=ready(page,child)
        assert child!=parent and detail['summary']['parent']==parent and detail['state']['demo']
        assert hashlib.sha256((Path('runs')/parent/'submission.zip').read_bytes()).hexdigest()==parent_hash
        report['child']=child
        report['checks'].append('Feedback creates a separate DEMO child and preserves parent archive')
        expect(page.locator('#run-overview')).to_contain_text(parent)
        page.screenshot(path=str(target/'overview-mobile.png'),full_page=True)
        assert not page.evaluate('()=>document.documentElement.scrollWidth>innerWidth')
        page.set_viewport_size({'width':1440,'height':1050})
        page.screenshot(path=str(target/'overview-desktop.png'),full_page=True)
        report['checks'].append('Desktop and mobile overview and revision dialog fit viewport')
        report['page_errors']=errors;report['passed']=not errors
        (target/'browser-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False))
        context.close();browser.close()
        return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
