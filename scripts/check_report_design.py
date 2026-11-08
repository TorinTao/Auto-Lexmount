"""Exercise all design variants, disclosures, anchors and released materials locally."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from autolex.common import read_json,write_json
from autolex.design import THEMES


def main():
    p=argparse.ArgumentParser();p.add_argument('run');p.add_argument('proof');args=p.parse_args()
    root=Path(args.run);proof=Path(args.proof);proof.mkdir(exist_ok=True,parents=True)
    output=read_json(root/'output.json');rows=[];errors=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch();page=browser.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        for theme in THEMES:
            for width in (1440,820,390,320):
                page.set_viewport_size({'width':width,'height':1050 if width>820 else 844})
                page.set_content((root/'release/index.html').read_text())
                page.locator('body').evaluate('(e,theme)=>e.className=theme',theme)
                page.add_style_tag(content='html{scroll-behavior:auto}')
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),(theme,width)
                links=page.locator('a[href^="#"]')
                for i in range(links.count()):
                    target=links.nth(i).get_attribute('href')
                    assert page.locator(target).count()==1,target
                page.locator('.atlas a').first.click()
                for n in range(page.locator('.points details').count()):page.locator('.points summary').nth(n).click()
                for item in output['items']:
                    for point in item.get('points',[]):assert point['quote'] in page.locator('.points').inner_text()
                page.locator('#implementation summary').click()
                assert page.locator('pre').inner_text()==(root/'main.py').read_text()
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),(theme,width,'expanded')
                page.locator('#implementation summary').click()
                page.evaluate('scrollTo(0,0)')
                if width in (1440,390):page.screenshot(path=str(proof/f'{theme}-{width}.png'),full_page=True)
                rows.append({'theme':theme,'width':width,'passed':True})
        for width in (1440,390,320):
            page.set_viewport_size({'width':width,'height':900})
            page.set_content((root/'release/materials.html').read_text())
            source=page.locator('details').filter(has=page.get_by_text('main.py',exact=True));source.locator('summary').click()
            assert source.locator('pre').text_content()==(root/'main.py').read_text()
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            rows.append({'view':'materials','width':width,'passed':True})
        browser.close()
    assert not errors,errors
    write_json(proof/'browser-checks.json',{'passed':True,'views':rows,'page_errors':errors})
    print(json.dumps({'passed':True,'views':len(rows)}))
if __name__=='__main__':main()
