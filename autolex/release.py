"""Publish and submit the generated run, never the agent's repository.

Remote writes are journaled before being attempted. Unknown outcomes are not retried.
"""
import fcntl
import hashlib
import html
import json
import re
import zipfile
from pathlib import Path

from .common import WorkflowError, now, read_json, write_json
from .submission import preflight

CONTEST_URL = 'https://browser.lexmount.cn/events/real-task-challenge/submit'
YOURS_URL = 'https://yours.lexmount.cn/artifact-site'


def release_config(profile):
    return {'url': CONTEST_URL, 'authors': [profile.get('authors', '')],
            'artifact_links': [YOURS_URL], 'fields': {'title': '#workTitle'},
            'submit_selector': 'form button[type=submit]', 'success_selector': '[data-receipt]'}


def verify_profile(profile):
    for field in ('authors', 'contact_email', 'context_id'):
        if not isinstance(profile.get(field), str) or not profile[field].strip():
            raise WorkflowError('Release profile requires ' + field)
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', profile['contact_email']):
        raise WorkflowError('Release profile requires a contact email')


def prepare_release(root, profile):
    root = Path(root).resolve()
    verify_profile(profile)
    preflight(root, release_config(profile))
    record_path=root/'release-state.json'
    if record_path.exists():
        record=read_json(record_path)
        if record.get('archive_sha256'):
            # A resumed publication must use the exact bundle already uploaded,
            # even if the agent's report template has changed since that upload.
            draft=read_json(root/'release/draft.json')
            if hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()!=record.get('source_manifest_sha256'):
                raise WorkflowError('Published work changed; do not reuse its release state')
            if hashlib.sha256((root/'release/site.zip').read_bytes()).hexdigest()!=record['archive_sha256'] or draft.get('archive_sha256')!=record['archive_sha256']:
                raise WorkflowError('Published archive changed; inspect the existing publication')
            return draft
    specification = read_json(root/'spec.json')
    spec = specification['selected']
    output = read_json(root/'output.json')
    state = read_json(root/'state.json')
    points = sum(len(i.get('points', [])) for i in output['items'])
    conclusions = len(output.get('conclusions', []))
    quality = read_json(root/'quality.json')
    if not quality.get('passed') or quality.get('version', 0)<2:
        raise WorkflowError('Release requires the current evidence checks; create and verify a new revision')
    # Only this generated work's files are published; no repository or other run is traversed.
    files = ['main.py','input.json','output.json','tests.json','quality.json','review.json']
    files += [name for name in ('design.json','citations.json','visual-review.json','visual-history.json','visual-theme.json') if (root/name).exists()]
    sections = []
    for name in files:
        content=(root/name).read_text()
        sections.append('<details><summary>'+html.escape(name)+'</summary><pre>'+html.escape(content)+'</pre></details>')
    title = spec['title']
    source_hash=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()
    visual_note = '已通过 DeepSeek 真实截图评审与桌面/手机布局检查，问题按有限轮次自动调整并复验；这是模型辅助视觉验收。' if state.get('visual_enabled') else '视觉质量未纳入自动验收。'
    design_note = 'DeepSeek 为作品选择视觉风格、撰写导读并安排阅读顺序，原有结论与引用保留。' if (root/'design.json').exists() else '网页采用固定报告模板。'
    fields = {
        'workTitle':title,
        'taskProblem':specification.get('brief') or spec['description'],
        'cloudRole':'本作品由 Auto Lexmount Agent 接入 DeepSeek 自动构建。Lexmount WebFetch 抓取所列公开来源；DeepSeek 生成 Python 程序并辅助检查内容；程序在无网络 Docker 容器中执行，生成带引用的中文报告。Auto Lexmount 是制作工具，本次投稿对象是“'+title+'”这件独立成果。',
        'taskResult':f'已完成 {len(output["items"])} 个来源、{points} 条引用要点、{conclusions} 条结论，形成可访问网页及可阅读源码/证据。通过 {len(quality.get("checks", []))} 项输入变化检查。当前运行模型调用 {state.get("model_calls",0)} 次。人工提供任务方向与配置环境，Agent 完成代码生成和测试；{design_note}{visual_note}模型辅助验收不等于人工事实审查。',
        'authors':profile['authors'], 'contactEmail':profile['contact_email'],
        'evidenceLink':'', 'evidenceAccessNote':''}
    dest=root/'release';dest.mkdir(exist_ok=True)
    about='<section><h2>这件作品如何完成</h2><p>'+html.escape(fields['cloudRole'])+'</p><p>'+html.escape(fields['taskResult'])+'</p><p><a href="materials.html">阅读本作品源码与运行证据 →</a></p><small>作品标识：'+html.escape(root.name)+' · 来源清单 SHA-256：'+source_hash+'</small></section>'
    index=(root/'index.html').read_text().replace('</main>',about+'</main>')
    from .presentation import report_style
    report_theme=html.escape(read_json(root/'design.json')['theme'],quote=True) if (root/'design.json').exists() else 'classic'
    materials='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+' · 源码与证据</title><style>'+report_style()+'details{border-top:1px solid var(--line);padding:20px 0}h1{font-size:clamp(28px,5vw,48px)}</style><body class="'+report_theme+'"><main><a href="index.html">← 返回本作品</a><h1>'+html.escape(title)+' · 源码与证据</h1><p>这些文件只属于当前作品，不包含 Agent 仓库、作者联系方式或凭据。</p>'+''.join(sections)+'</main></body></html>'
    if state.get('visual_enabled'):
        from .visual import capture
        layout=capture(index,dest/'layout-check')
        write_json(dest/'layout-check.json',layout)
        if not layout['passed']:raise WorkflowError('Final Yours layout failed browser checks; publication blocked')
    (dest/'index.html').write_text(index)
    (dest/'materials.html').write_text(materials)
    archive=dest/'site.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name,content in [('index.html',index),('materials.html',materials)]:
            info=zipfile.ZipInfo(name);info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,content)
    draft={'run':root.name,'title':title,'source_manifest_sha256':source_hash,
           'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(), 'fields':fields,
           'identity':hashlib.sha256(json.dumps({'title':title,'sources':sorted(spec['source_urls'])},ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
    # This draft contains contact information and remains local.
    write_json(dest/'draft.json',draft);(dest/'draft.json').chmod(0o600)
    return draft


def release(root, profile, send=False, backend=None):
    root=Path(root).resolve()
    if backend is None:
        from .release_browser import ReleaseBrowser
        backend=ReleaseBrowser
    # One remote release at a time; the ledger also prevents re-submitting revisions.
    with (root.parent/'.release.lock').open('a') as guard, (root/'.lock').open('a') as run_lock:
        for lock in (guard,run_lock):
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise WorkflowError('A workflow or publication is already active') from None
        record_path=root/'release-state.json'
        record=read_json(record_path) if record_path.exists() else {}
        if record.get('status')=='submitted':return record
        if record.get('status') in {'publishing','submitting','unknown'}:
            raise WorkflowError('Remote outcome is uncertain; inspect the website before any retry')
        draft=prepare_release(root,profile)
        if record.get('source_manifest_sha256') and record['source_manifest_sha256']!=draft['source_manifest_sha256']:
            raise WorkflowError('Published work changed; do not reuse its release state')
        if not send:return {'status':'prepared','run':draft['run'],'title':draft['title'],'archive':str(root/'release/site.zip')}
        ledger_path=root.parent/'.release-ledger.json'
        ledger=read_json(ledger_path) if ledger_path.exists() else {}
        previous=ledger.get(draft['identity'])
        if previous and previous['run']!=root.name:
            raise WorkflowError('This task already has a release: '+previous['run']+'; inspect or update that work instead')
        def save(status, **values):
            if status!='unknown':record.pop('phase',None)
            record.update(status=status,run=root.name,title=draft['title'],source_manifest_sha256=draft['source_manifest_sha256'],archive_sha256=draft['archive_sha256'],at=now(),**values)
            write_json(record_path,record)
            ledger[draft['identity']]={'run':root.name,'status':status}
            write_json(ledger_path,ledger)
        with backend(profile) as browser:
            if not record.get('url'):
                browser.prepare_upload(root/'release/site.zip',draft['title'])
                browser.capture(root/'release/01-upload-preview.png')
                save('publishing')
                try:published=browser.publish()
                except Exception:
                    save('unknown',phase='publish')
                    raise WorkflowError('Publish outcome unknown; automatic retry disabled') from None
                if not re.fullmatch(r'https://yours\.lexmount\.cn/artifact-site/s/[A-Za-z0-9_-]+',published.get('url','')):
                    save('unknown',phase='publish')
                    raise WorkflowError('Publisher did not return a canonical work URL')
                save('published',**published)
            # Sharing can safely be retried against this known URL; never create a duplicate work.
            access=browser.share_and_verify(record['url'],draft['title'],root/'release')
            save('published',**access)
            fields={**draft['fields'],'evidenceLink':record['url'],'evidenceAccessNote':record.get('passcode','')}
            browser.fill_contest(fields)
            browser.capture(root/'release/03-before-submit.png')
            save('submitting')
            try:receipt=browser.submit_contest()
            except Exception:
                save('unknown',phase='submit')
                raise WorkflowError('Submission outcome unknown; automatic retry disabled') from None
            if not receipt.get('id'):
                save('unknown',phase='submit')
                raise WorkflowError('Submission confirmation has no receipt ID')
            save('submitted',receipt=receipt)
            write_json(root/'submission-state.json',{'status':'submitted','at':now(),'title':draft['title'],'artifact_url':record['url'],'receipt':receipt})
            try:browser.capture(root/'release/04-receipt.png')
            except Exception:pass
            return record


def recover_publication(root, profile, url, backend=None):
    """Adopt a known, independently inspected URL after an uncertain publish.

    This verifies the exact generated source in a guest session; it never uploads again.
    A possibly sent contest form cannot be recovered through this operation.
    """
    if not re.fullmatch(r'https://yours\.lexmount\.cn/artifact-site/s/[A-Za-z0-9_-]+',url):
        raise WorkflowError('Recovery requires a canonical Yours work URL')
    root=Path(root).resolve()
    with (root.parent/'.release.lock').open('a') as guard,(root/'.lock').open('a') as lock:
        for handle in (guard,lock):
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise WorkflowError('Release is active') from None
        state=read_json(root/'release-state.json')
        if state.get('status')!='unknown' or state.get('phase')!='publish':
            raise WorkflowError('Only an uncertain publication can use URL recovery')
        draft=prepare_release(root,profile)
        if state.get('source_manifest_sha256')!=draft['source_manifest_sha256']:
            raise WorkflowError('Work changed since the uncertain publication')
        if backend is None:
            from .release_browser import ReleaseBrowser
            backend=ReleaseBrowser
        with backend(profile) as browser:
            access=browser.share_and_verify(url,draft['title'],root/'release')
        state.update(status='published',url=url,**access,recovered_at=now(),recovery='Existing URL verified against the exact generated source; no new upload')
        state.pop('phase',None)
        write_json(root/'release-state.json',state)
        return state
