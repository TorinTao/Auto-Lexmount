"""Independent checks of visual revisions, including fresh Docker executions."""
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autolex.common import read_json,write_json
from autolex.runner import execute,validate_output
from playwright.sync_api import sync_playwright

root=Path.cwd();lab=root/'runs/visual-retrospective';records=[]
with sync_playwright() as p:
    browser=p.chromium.launch();ctx=browser.new_context();ctx.route('**/*',lambda route:route.abort())
    page=ctx.new_page()
    for key,choice in read_json(root/'runs/batch7-lab/final-runs.json').items():
        original=root/'runs'/choice['run'];child=root/'runs'/('visual-final-'+key)
        state=read_json(child/'state.json');assert state['status']=='ready' and state['visual_enabled']
        for directory in [original,child]:
            for filename,sha in read_json(directory/'state.json')['hashes'].items():
                assert hashlib.sha256((directory/filename).read_bytes()).hexdigest()==sha,(directory,filename)
        assert not (child/'submission-state.json').exists() and not (child/'release-state.json').exists()
        for name in ['main.py','input.json','output.json','tests.json','quality.json','citations.json','review.json']:
            assert (original/name).read_bytes()==(child/name).read_bytes(),(key,name)
        visual=read_json(child/'visual-review.json');assert visual['passed']
        assert visual['last']['html_sha256']==hashlib.sha256((child/'index.html').read_bytes()).hexdigest()
        for row in read_json(child/'visual-history.json'):
            for filename,sha in row['images'].items():assert hashlib.sha256((child/filename).read_bytes()).hexdigest()==sha
        manifest=read_json(child/'manifest.json')
        with zipfile.ZipFile(child/'submission.zip') as z:
            assert set(z.namelist())==set(manifest)|{'manifest.json'}
            for name,sha in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==sha
        work=lab/'rerun'/key/'work';work.mkdir(parents=True,exist_ok=False)
        for name in ['main.py','input.json']:shutil.copyfile(child/name,work/name)
        result=execute(work);assert result['returncode']==0 and not result['timeout'],key
        assert not validate_output(work,read_json(child/'input.json')),key
        assert read_json(work/'output.json')==read_json(child/'output.json'),key
        views=[]
        for label,width,height in [('desktop',1440,1050),('mobile',390,844)]:
            page.set_viewport_size({'width':width,'height':height})
            page.set_content((child/'index.html').read_text());page.locator('#implementation').evaluate('(e)=>e.open=true')
            assert page.locator('pre code').text_content()==(child/'main.py').read_text(),key
            metrics=page.evaluate('''()=>({overflow:document.documentElement.scrollWidth>innerWidth,
              codeOverflow:document.querySelector('pre').scrollWidth>document.querySelector('pre').clientWidth+1,
              codeWrap:getComputedStyle(document.querySelector('pre')).whiteSpace,
              byteWrap:getComputedStyle(document.querySelector('#implementation td:last-child')).whiteSpace,
              missingAnchors:[...document.querySelectorAll('a[href^="#"]')].filter(a=>!document.getElementById(decodeURIComponent(a.hash.slice(1)))).length,
              duplicateIds:document.querySelectorAll('[id]').length-new Set([...document.querySelectorAll('[id]')].map(e=>e.id)).size})''')
            assert not metrics['overflow'] and not metrics['codeOverflow'] and not metrics['missingAnchors'] and not metrics['duplicateIds'],(key,metrics)
            assert metrics['codeWrap']=='pre-wrap' and metrics['byteWrap']=='nowrap',key
            views.append({'viewport':label,**metrics})
        record={'case':key,'original':original.name,'final':child.name,'original_and_final_hashes_valid':True,
                'program_and_content_unchanged':True,'docker_rerun_matches':True,'visual_passed':True,'viewports':views,
                'remaining_issues':visual['last']['review']['issues']}
        records.append(record);write_json(lab/'verification.json',{'passed':len(records)==7,'records':records,'fresh_container_runs':len(records),'viewports_checked':len(records)*2})
        print('VERIFIED',key,flush=True)
    ctx.close();browser.close()
