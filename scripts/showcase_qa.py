"""Browser QA for the public showcase, using a local static preview."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright,expect
from autolex.common import write_json
out=Path('runs/yours-redesign');out.mkdir(exist_ok=True)
checks=[];errors=[];posts=[]
with sync_playwright() as p:
    browser=p.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1050},permissions=['clipboard-read','clipboard-write'])
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:posts.append(r.url) if r.method not in ('GET','HEAD') else None)
    response=page.goto('http://127.0.0.1:8768',wait_until='networkidle');assert response.status==200
    expect(page.locator('h1')).to_have_text('你动动手指，它跑完流程。')
    expect(page.locator('.experiment')).to_contain_text('后续测试提交会按约定加上标记')
    assert page.locator('.work-card').count()==5
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
    response=page.goto('http://127.0.0.1:8768/materials.html',wait_until='networkidle');assert response.status==200
    for label,width,height in [('desktop',1440,1050),('mobile',390,844),('narrow',320,760)]:
        page.set_viewport_size({'width':width,'height':height});page.screenshot(path=str(out/(label+'-evidence.png')))
        overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth');checks.append({'page':'evidence','viewport':label,'overflow':overflow});assert not overflow
    page.locator('#source-search').fill('autolex/visual.py');expect(page.locator('.source-file:not([hidden])')).to_have_count(1)
    file=page.locator('.source-file:not([hidden])');file.locator('summary').click()
    assert file.locator('pre').text_content()==Path('autolex/visual.py').read_text()
    page.locator('#source-search').fill('missing-file-example');expect(page.locator('#source-count')).to_have_text('找到 0 个文件')
    page.locator('#source-search').fill('');assert page.locator('.source-file:not([hidden])').count()>60
    with page.expect_download() as info:page.get_by_role('link',name='下载源码与记录 ↓').click()
    download=info.value;assert download.suggested_filename=='source.zip';download.save_as(str(out/'downloaded-source.zip'))
    assert (out/'downloaded-source.zip').read_bytes()==Path('dist/submission-site-v6/source.zip').read_bytes()
    assert not errors,errors
    write_json(out/'browser-checks.json',{'passed':True,'views':checks,'flow_tabs_and_keyboard':True,'autoplay_and_pause':True,'five_screenshot_dialogs':True,'passcode_copy':True,'faq':True,'source_search':True,'source_text_matches':True,'source_download_matches':True,'demo_sends_no_posts':True,'page_errors':errors})
    print(json.dumps({'passed':True,'views':len(checks),'page_errors':errors}))
    context.close();browser.close()
