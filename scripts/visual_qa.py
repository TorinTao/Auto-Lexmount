"""Capture real Chromium screenshots using an existing CDP browser (no model claims)."""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cdp', default='http://127.0.0.1:9229')
    parser.add_argument('--runs', nargs='+', required=True)
    parser.add_argument('--out', default='runs/quality-lab/visual')
    args = parser.parse_args()
    target = Path(args.out); target.mkdir(parents=True, exist_ok=True)
    base = 'http://127.0.0.1:8765'
    def relay(route):
        req = route.request
        headers = {k:v for k,v in req.headers.items() if k.lower() not in ('host','content-length','accept-encoding','connection')}
        request = urllib.request.Request(req.url, data=req.post_data_buffer, headers=headers, method=req.method)
        try:
            response = urllib.request.urlopen(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read()
            headers = {k:v for k,v in response.headers.items() if k.lower() not in ('content-length','transfer-encoding','connection')}
            route.fulfill(status=response.status, headers=headers, body=body)
    report = {'browser': None, 'runs': [], 'visual_review': 'Screenshots captured; visual judgment must be recorded after inspecting images.'}
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp)
        report['browser'] = browser.version
        context = browser.new_context(viewport={'width':1440,'height':1050})
        context.route(base+'/**',relay)
        page = context.new_page(); errors = []
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base,wait_until='domcontentloaded');page.wait_for_selector('#connection.online')
        for name in args.runs:
            with urllib.request.urlopen(base+'/api/runs/'+name) as response:
                detail = json.load(response)
            page.locator(f'[data-run="{name}"]').click()
            expect(page.locator('#run-title')).to_have_text(detail['spec']['selected']['title'])
            page.screenshot(path=str(target/(name+'-overview.png')),full_page=True)
            page.locator('#tab-code').click();page.wait_for_selector('.code-block')
            page.screenshot(path=str(target/(name+'-code.png')),full_page=True)
            page.locator('#tab-tests').click();page.wait_for_selector('.test-heading')
            page.screenshot(path=str(target/(name+'-tests.png')),full_page=True)
            preview = Path('runs')/name/'index.html'
            record = {'run':name,'viewports':[], 'preview':preview.exists()}
            if detail.get('citations'):
                expect(page.locator('#result-content')).to_contain_text('引用支撑检查')
                record['citation_panel'] = True
            if preview.exists():
                work = context.new_page()
                work.on('pageerror',lambda e:errors.append(str(e)))
                response = work.goto(base+'/api/runs/'+name+'/preview',wait_until='load')
                record['preview_http_status'] = response.status
                record['preview_csp'] = response.headers.get('content-security-policy','')
                for label,width,height in [('desktop',1440,1050),('mobile',390,844)]:
                    work.set_viewport_size({'width':width,'height':height})
                    work.screenshot(path=str(target/(name+'-'+label+'.png')),full_page=True)
                    layout = work.evaluate('''() => ({overflow:document.documentElement.scrollWidth>innerWidth, brokenImages:[...document.images].filter(i=>!i.complete||!i.naturalWidth).length, headings:document.querySelectorAll('h1').length, pointCards:document.querySelectorAll('.points li').length, missingAnchors:[...document.querySelectorAll('a[href^="#"]')].filter(a=>!document.getElementById(decodeURIComponent(a.hash.slice(1)))).length, duplicateIds:document.querySelectorAll('[id]').length-new Set([...document.querySelectorAll('[id]')].map(n=>n.id)).size})''')
                    record['viewports'].append({'name':label,**layout})
                work.set_viewport_size({'width':1440,'height':1050})
                work.locator('#implementation summary').click()
                work.locator('#implementation').screenshot(path=str(target/(name+'-directory.png')))
                work.close()
            report['runs'].append(record)
        if page.locator('#new-task').is_enabled():
            page.locator('#new-task').click();page.wait_for_selector('#task-brief')
            page.screenshot(path=str(target/'new-task.png'))
            report['task_dialog'] = 'checked'
        else:
            report['task_dialog'] = 'disabled during active workflow'
        report['page_errors']=errors
        report['passed']=not errors and len(report['runs'])==len(args.runs) and all(r['preview'] and r.get('preview_http_status')==200 and len(r['viewports'])==2 and all(not v['overflow'] and not v['brokenImages'] and v['headings']==1 and not v['missingAnchors'] and not v['duplicateIds'] for v in r['viewports']) for r in report['runs'])
        (target/'browser-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False))
        context.close();browser.close()
        return 0 if report['passed'] else 1


if __name__=='__main__':sys.exit(main())
