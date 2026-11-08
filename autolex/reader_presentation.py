"""Public-facing reading view with technical evidence progressively disclosed."""
from .common import read_json
from .reader import verified_reader


def render_reader_report(root,files,design,output,tests,quality):
    from .presentation import esc,link,headline_markup,report_style
    reader=verified_reader(root,output)
    points={p['id']:p for item in output['items'] for p in item.get('points',[])}
    anchors={c['point_id']:f'point-{n}' for n,c in enumerate(reader['cards'],1)}
    cards=[];nav=[]
    for n,card in enumerate(reader['cards'],1):
        point=points[card['point_id']];anchor=anchors[card['point_id']]
        nav.append(f'<li><a href="#{anchor}"><i>{n:02d}</i><strong>{esc(card["title"])}</strong></a></li>')
        cards.append(f'''<li id="{anchor}" class="reader-card">
<div class="point-top"><span class="point-no">{n:02d}</span><h3>{esc(card['title'])}</h3></div>
<p class="reader-explanation">{esc(card['text'])}</p>
<div class="everyday-example"><span>打个比方</span><p>{esc(card['analogy'])}</p></div>
<details data-evidence><summary>想知道专业说法？展开看</summary><p>{esc(point['summary'])}</p><blockquote>{esc(point['quote'])}</blockquote><div class="source-link">{link(point['url'],'查看这段话的出处 ↗')}</div></details></li>''')
    source_parts=[]
    for item in output['items']:
        missing='<p>资料未说明：'+esc('、'.join(item['not_mentioned']))+'</p>' if item.get('not_mentioned') else ''
        source_parts.append(f'<article><h3>{link(item["url"],item["title"])}</h3><p>{esc(item["summary"])}</p>{missing}</article>')
    conclusions=''.join('<li><p>'+esc(c['text'])+'</p><small>'+' · '.join(f'<a href="#{anchors[ref]}">回到对应例子</a>' for ref in c['point_refs'] if ref in anchors)+'</small></li>' for c in output.get('conclusions',[]))
    inventory=''.join(f'<tr><td>{esc(name)}</td><td>{(root/name).stat().st_size:,} B</td></tr>' for name in files if (root/name).is_file())
    mode='离线固定演示' if tests.get('demo') else '实验作品'
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(reader['headline'])}</title><meta name="description" content="{esc(reader['intro'])}"><style>{report_style()}</style></head><body class="{design['theme']} reader-page"><main>
<div class="masthead"><div class="brand"><b>A</b> 小事说明书</div><nav aria-label="页内导航"><a href="#reading">看例子</a><a href="#findings">记重点</a><a href="#sources">查出处</a></nav></div>
<header class="hero"><div class="hero-copy"><div class="eyebrow">先看懂，再记名字</div><h1>{headline_markup(reader['headline'])}</h1><p>{esc(reader['intro'])}</p><div class="hero-actions"><a class="button" href="#reading">看个生活里的比方 ↓</a><a href="#findings">先看一句话解释</a></div></div></header>
<section id="findings" class="reader-takeaway"><span class="section-number">先记住这一点</span><p>{esc(reader['takeaway']['text'])}</p></section>
<section id="reading"><div class="section-head"><div><h2>换个熟悉的东西，就好懂了</h2><p>下面是帮助理解的比方。专业说法和原文，想看时再展开。</p></div></div>
<aside class="atlas reader-nav" aria-label="阅读路线"><ol>{''.join(nav)}</ol></aside>
<ol class="points">{''.join(cards)}</ol></section>
<section id="sources" class="reader-sources"><details><summary>这些解释从哪里来？</summary><p>依据公开资料整理。这里保留技术说明和出处，方便进一步核对。</p>{''.join(source_parts)}<h3>完整的技术结论</h3><ol>{conclusions}</ol></details></section>
<details id="implementation"><summary>想研究它怎么做出来的？看代码和文件</summary><p>这里是生成本页所用的程序、资料与检查记录。</p><h2>main.py</h2><pre><code>{esc((root/'main.py').read_text())}</code></pre><h2>文件目录</h2><table><tbody>{inventory}</tbody></table></details>
<footer>{mode} · Auto Lexmount 辅助整理 · 生活比方用于帮助理解，具体条件以原文为准</footer></main></body></html>'''
