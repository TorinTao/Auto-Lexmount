"""Distinctive model-directed reports; generated code never supplies executable markup."""
import html
import re
from pathlib import Path
from urllib.parse import urlsplit
from .common import read_json, WorkflowError
from .design import fallback_design, validate_plan, fingerprint


def esc(value):
    return html.escape(str(value), quote=True)


def link(url, label=None):
    if urlsplit(str(url)).scheme not in ('https', 'http'):
        return esc(label or url)
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label or url)}</a>'


def headline_markup(text):
    # Keep short punctuation-delimited phrases together without changing the text.
    return ''.join('<span class="title-phrase">'+esc(part)+'</span>' if len(part)<=8 else esc(part)
                   for part in re.findall(r'[^、，,。！？!?：:]+[、，,。！？!?：:]?|[、，,。！？!?：:]',text))


def report_style():
    return Path(__file__).with_name('report.css').read_text()


def render_report(root, files):
    spec=read_json(root/'spec.json');output=read_json(root/'output.json');tests=read_json(root/'tests.json')
    quality=read_json(root/'quality.json') if (root/'quality.json').exists() else None
    if (root/'design.json').exists():
        design=read_json(root/'design.json');validate_plan(design,output)
        if design.get('input_sha256')!=fingerprint(spec,output):raise WorkflowError('Design inputs changed')
    else:design=fallback_design(spec,output)
    classic=design['theme']=='classic'
    points={p['id']:p for item in output['items'] for p in item.get('points',[])}
    # Safe anchors are independent of arbitrary source/model IDs.
    anchors={row['point_id']:f'point-{n}' for n,row in enumerate(design['chapters'],1)}
    labels={row['point_id']:f'依据 {n:02d}' for n,row in enumerate(design['chapters'],1)}
    navigation=[];cards=[]
    for n,row in enumerate(design['chapters'],1):
        p=points[row['point_id']];anchor=anchors[p['id']]
        navigation.append(f'<li><a href="#{anchor}"><i>{n:02d}</i><strong>{esc(row["label"])}</strong><span aria-hidden="true">↗</span></a></li>')
        cards.append(f'<li id="{anchor}"><div class="point-top"><span class="point-no">{n:02d}</span><span class="topic">{esc(row["label"])}</span></div><h3>{esc(p["summary"])}</h3><details><summary>展开原文，核对这个说法</summary><blockquote>{esc(p["quote"])}</blockquote><div class="source-link">{link(p["url"],"去原始资料查看 ↗")} · {labels[p["id"]]}</div></details></li>')
    conclusions=''.join('<li><p>'+esc(c['text'])+'</p><small>原文依据：'+' · '.join(f'<a href="#{anchors[ref]}">{labels[ref]}</a>' for ref in c['point_refs'] if ref in anchors)+'</small></li>' for c in output.get('conclusions',[]))
    sources=[]
    for n,item in enumerate(output['items'],1):
        absent='<p>资料未说明：'+esc('、'.join(item['not_mentioned']))+'</p>' if item.get('not_mentioned') else ''
        sources.append(f'<div class="source-row"><span class="source-id">{n:02d}</span><div><h3>{link(item["url"],item["title"])}</h3><p>{esc(item["summary"])}</p>{absent}</div></div>')
    purpose={'main.py':'生成这份指南的程序','input.json':'保存的原始网页资料','output.json':'程序整理出的结果','tests.json':'程序运行与修复记录','quality.json':'更换输入后的检查','design.json':'AI 选择的版式与阅读顺序','spec.json':'本次任务','citations.json':'原文引用检查'}
    inventory=''.join(f'<tr><td>{esc(name)}</td><td>{esc(purpose.get(name,"作品材料"))}</td><td>{(root/name).stat().st_size:,} B</td></tr>' for name in files if (root/name).is_file())
    quality_note=f'{sum(c["passed"] for c in quality["checks"])}/{len(quality["checks"])} 项输入变化检查通过' if quality else '本版本尚未进行输入变化检查'
    mode='离线固定演示' if tests.get('demo') else '公开资料整理 · 测试作品'
    findings=f'<section id="findings"><div class="section-head"><div><span class="section-number">01 / TAKEAWAYS</span><h2>先带走这几个判断</h2></div><p>每个判断都保留依据。点击编号，就能找到对应的原文。</p></div><ol class="conclusions">{conclusions}</ol></section>' if conclusions else '<section id="findings"><h2>从原始资料开始阅读</h2><p>本作品没有单独生成结论，请查看下方来源摘要。</p></section>'
    route_links="".join(navigation) or '<li><a href="#sources">查看来源摘要 ↗</a></li>'
    atlas=f'<aside class="atlas" aria-label="阅读路线"><div class="atlas-head"><span class="eyebrow">阅读目录</span></div><ol>{route_links}</ol></aside>' if classic else ''
    hero_atlas='' if classic else f'<aside class="atlas" aria-label="阅读路线"><div class="atlas-head"><span class="eyebrow">READING MAP</span><span>阅读路线</span></div><ol>{route_links}</ol><p class="atlas-note">点选一个主题，从你最关心的地方开始。</p></aside>'
    heading_labels=('01 · 先看结论','02 · 逐条核对','03 · 资料来源') if classic else ('01 / TAKEAWAYS','02 / A CLOSER LOOK','03 / SOURCES')
    findings=findings.replace('01 / TAKEAWAYS',heading_labels[0])
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(spec['selected']['title'])}</title><meta name="description" content="{esc(design['intro'])}"><style>{report_style()}</style></head><body class="{design['theme']}"><main>
<div class="masthead"><div class="brand"><b>A</b> AUTOLEX <span class="edition">/ 小型知识图鉴</span></div><nav aria-label="页内导航"><a href="#findings">看结论</a><a href="#sources">查原文</a><a href="#implementation">看代码</a></nav></div>
<header class="hero"><div class="hero-copy"><div class="eyebrow">{esc(design['kicker'])}</div><h1>{headline_markup(design['headline'])}</h1><p>{esc(design['intro'])}</p><div class="hero-actions"><a class="button" href="#findings">开始阅读 ↓</a><a href="#reading">逐条看区别 ↗</a></div></div>{hero_atlas}</header>
<div class="facts"><div><strong>{len(output['items']):02d}</strong>份资料</div><div><strong>{len(points):02d}</strong>条原文依据</div><div><strong>{len(output.get('conclusions',[])):02d}</strong>个判断</div><div>{mode}</div></div>
{findings}<section id="reading"><div class="section-head"><div><span class="section-number">{heading_labels[1]}</span><h2>把区别，一条条看清</h2></div><p>先读中文说明。想确认时，展开下面的原文摘录。</p></div>{atlas}<ol class="points">{''.join(cards)}</ol></section>
<section id="sources"><span class="section-number">{heading_labels[2]}</span><h2>这些说法，从哪里来？</h2>{''.join(sources)}<p class="note">模型辅助整理；引用检查不等于人工事实审查。</p></section>
<details id="implementation"><summary>想进一步研究？查看代码与文件</summary><p>{quality_note}。下方保留生成本页内容的代码和成果文件。</p><h2>main.py</h2><pre><code>{esc((root/'main.py').read_text())}</code></pre><h2>成果文件</h2><table><tbody>{inventory}</tbody></table></details>
<footer>Auto Lexmount 生成 · {mode} · 原始结论与引用保留，可沿编号核对</footer></main></body></html>'''
