"""Browser QA for the public showcase, using a local static preview."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright,expect
from autolex.common import write_json
parser=argparse.ArgumentParser()
parser.add_argument('--site',default='dist/submission-site-v7')
parser.add_argument('--proof',default='runs/autolex-public-refresh')
parser.add_argument('--url',default='http://127.0.0.1:8768')
args=parser.parse_args()
out=Path(args.proof);out.mkdir(parents=True,exist_ok=True)
checks=[];errors=[];posts=[]
with sync_playwright() as p:
    browser=p.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1050},permissions=['clipboard-read','clipboard-write'])
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:posts.append(r.url) if r.method not in ('GET','HEAD') else None)
    response=page.goto(args.url,wait_until='networkidle');assert response.status==200
    expect(page.locator('h1')).to_have_text('你动动手指，它跑完流程。')
    expect(page.locator('.experiment')).to_contain_text('后续测试提交会按约定加上标记')
    assert page.locator('.work-card').count()==5
    expect(page.locator('.hero-body')).to_contain_text('Auto Lexmount')
    expect(page.locator('#works-title')).to_contain_text('Auto Lexmount')
    assert '浅拷贝' not in page.locator('.hero').inner_text()
    assert 'token' not in page.locator('.hero').inner_text()
    assert 'Auto Lexmount' in page.title()
    for label,width,height in [('desktop',1440,1050),('tablet',820,1180),('mobile',390,844),('narrow',320,760)]:
        page.set_viewport_size({'width':width,'height':height});page.evaluate('scrollTo(0,0)');page.screenshot(path=str(out/(label+'-home.png')),full_page=True)
        metrics=page.evaluate('''()=>({overflow:document.documentElement.scrollWidth>innerWidth,
          missingAnchors:[...document.querySelectorAll('a[href^="#"]')].filter(a=>!document.getElementById(decodeURIComponent(a.hash.slice(1)))).length,
          duplicateIds:document.querySelectorAll('[id]').length-new Set([...document.querySelectorAll('[id]')].map(e=>e.id)).size})''')
        checks.append({'page':'home','viewport':label,**metrics});assert not any(metrics.values()),(label,metrics)
    page.set_viewport_size({'width':1440,'height':1050})
    for i in range(6):
        page.locator('#step-'+str(i)).click();expect(page.locator('#step-progress')).to_have_text('第 '+str(i+1)+' 步 / 共 6 步')
        expect(page.locator('#step-'+str(i))).to_have_attribute('aria-selected','true')
    page.locator('#step-5').press('Home');expect(page.locator('#step-0')).to_be_focused()
    page.locator('#step-0').press('ArrowRight');expect(page.locator('#step-1')).to_be_focused()
    page.locator('#play-demo').click();expect(page.locator('#play-demo')).to_have_attribute('aria-pressed','true')
    page.wait_for_timeout(2500);expect(page.locator('#step-2')).to_have_attribute('aria-selected','true')
    page.locator('#play-demo').click();expect(page.locator('#play-demo')).to_have_attribute('aria-pressed','false')
    for button in page.locator('[data-preview]').all():
        button.click();expect(page.locator('#preview-dialog')).to_be_visible()
        assert page.locator('#preview-image').evaluate('(e)=>e.complete&&e.naturalWidth>0')
        page.locator('#close-preview').click();expect(page.locator('#preview-dialog')).not_to_be_visible()
    button=page.locator('[data-copy]').first;code=button.get_attribute('data-copy');button.click()
    expect(page.locator('#toast')).to_contain_text('访问码已复制')
    assert page.evaluate('navigator.clipboard.readText()')==code
    page.locator('.faq details').last.locator('summary').click();assert page.locator('.faq details').last.get_attribute('open') is not None
    assert not posts,'Flow demo unexpectedly wrote to a server'
    repo='https://github.com/TorinTao/Auto-Lexmount'
    for label,url in [('GitHub 源码',repo),('在线演示','https://39.106.14.223:8766')]:
        action=page.locator('.hero .actions').get_by_role('link',name=label)
        expect(action).to_have_attribute('href',url)
        expect(action).to_have_attribute('target','_blank')
        expect(action).to_have_attribute('rel','noopener noreferrer')
    expect(page.locator('.site-header .github-link')).to_have_attribute('href',repo)
    expect(page.locator('.site-header .github-link')).to_have_attribute('target','_blank')
    assert page.get_by_text('想看细节',exact=True).count()==0
    assert page.locator('a[href*="materials.html"]').count()==0
    assert not (Path(args.site)/'materials.html').exists()
    assert not (Path(args.site)/'source.zip').exists()
    response=page.goto(args.url+'/materials.html');assert response.status==404
    assert not errors,errors
    write_json(out/'browser-checks.json',{'passed':True,'views':checks,'flow_tabs_and_keyboard':True,'autoplay_and_pause':True,'five_screenshot_dialogs':True,'passcode_copy':True,'faq':True,'github_link':True,'hero_github_and_demo_links':True,'details_page_removed':True,'demo_sends_no_posts':True,'page_errors':errors})
    print(json.dumps({'passed':True,'views':len(checks),'page_errors':errors}))
    context.close();browser.close()
