"""Render an evidence-linked comparison without turning model reviews into scores."""
import argparse
import html
import json
import re
from pathlib import Path
from urllib.parse import urldefrag


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--lab',default='runs/batch7-lab');args=parser.parse_args()
    lab=Path(args.lab);cases=read(lab/'cases.json');rows=[];rounds={}
    for name in ['baseline','improved','refined','polished','touchup']:
        summary=read(lab/name/'summary.json',{'records':[]})
        records=[]
        for original in summary['records']:
            record=dict(original);run=Path('runs')/record['run'];out=read(run/'output.json',{})
            case=next(c for c in cases if c['id']==record['case'])
            expected={urldefrag(u.rstrip('。，.;'))[0] for u in re.findall(r'https?://[^\s]+',case['brief'])}
            actual={i['url'] for i in out.get('items',[])}
            record['complete_source_corpus']=actual==expected
            record['original_contract_passed']=record['original_brief_passed'] and actual==expected
            telemetry=read(lab/name/(record['case']+'-telemetry.json'),{})
            model=sorted(telemetry.get('model',[]),key=lambda c:(c['calls_before'],-c['calls_after']))
            end=-1;model_seconds=0
            for c in model:
                if c['calls_before']>=end:model_seconds+=c['seconds'];end=c['calls_after']
            record['model_seconds']=model_seconds
            record['fetch_seconds']=sum(c['seconds'] for c in telemetry.get('fetch',[]))
            record['cached_fetches']=sum(c['cached'] for c in telemetry.get('fetch',[]))
            audit=read(lab/('audit-'+name)/record['run']/'audit.json')
            record['independent_audit']=audit
            record['citation_review']=read(run/'citations.json') or read(lab/'citation-audit-improved'/(record['run']+'.json'))
            record['code_inventory']=(read(run/'quality.json',{}) or {}).get('code',{})
            records.append(record)
        rounds[name]={'records':records,'ready':sum(r['status']=='ready' for r in records),
            'original_contract_passed':sum(r['original_contract_passed'] for r in records),
            'calls':sum(r['model_calls'] for r in records),'tokens_reported':sum(r['tokens_reported'] for r in records),
            'seconds':sum(r['seconds'] for r in records),'model_seconds':sum(r['model_seconds'] for r in records),
            'fetch_seconds':sum(r['fetch_seconds'] for r in records),
            'first_attempt_ready':sum(r['status']=='ready' and r['attempts']==1 for r in records),
            'citation_tested_works':sum(r['citation_review'] is not None for r in records),
            'audit_tested_works':sum(r['independent_audit'] is not None for r in records),
            'citation_passed_works':sum(bool(r['citation_review'] and r['citation_review']['passed']) for r in records),
            'audit_passed_works':sum(bool(r['independent_audit'] and r['independent_audit']['passed']) for r in records),
            'audit_checks_passed':sum(c['passed'] for r in records if r['independent_audit'] for c in r['independent_audit']['checks']),
            'audit_checks_total':sum(len(r['independent_audit']['checks']) for r in records if r['independent_audit'])}
    review_before=read(lab/'reviewer-baseline.json',{})
    review_after=read(lab/'reviewer-final.json') or read(lab/'reviewer-refined.json',{})
    selection=read(lab/'final-runs.json',{})
    report={'interruption':read(lab/'interruption.json'),'experiment':read(lab/'experiment.json'), 'rounds':rounds,'review_before':review_before,'review_after':review_after,'review_intermediate':read(lab/'reviewer-improved.json',{}),'review_refined':read(lab/'reviewer-refined.json',{}),'final_selection':selection,
        'limitations':['7 tasks are public documentation research tools, not seven arbitrary app categories.',
          'DeepSeek performs generation, repair and model-assisted review. Independent Codex review is separate; neither is an official score.',
          'The improved round reuses captured evidence where available. Compare model calls and model time separately; total wall time is not a controlled speedup metric.',
          'Small stochastic sample; no statistical claim. Baseline failures remain recorded. No competition submission in this experiment.']}
    (lab/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    esc=lambda s:html.escape(str(s),quote=True)
    def metric(name,key):
        data=rounds[name]
        if key in {'citation_passed_works','audit_passed_works'}:
            tested=data[key.replace('passed','tested')]
            return str(data[key])+'/'+str(tested) if tested else '未执行'
        if key in {'ready','original_contract_passed','first_attempt_ready'}:
            return str(data[key])+'/'+str(len(data['records']))
        return round(data[key],1) if isinstance(data[key],float) else data[key]
    metrics=[]
    for label,key in [('工作流 ready','ready'),('原任务数量与来源通过','original_contract_passed'),('首次代码即通过','first_attempt_ready'),('隔离摘录支撑检查通过','citation_passed_works'),('模型调用','calls'),('API 报告 tokens','tokens_reported'),('模型耗时（秒）','model_seconds'),('资料获取耗时（秒）','fetch_seconds'),('总耗时（秒）','seconds'),('独立压力测试全过作品','audit_passed_works')]:
        metrics.append(f'<tr><th>{label}</th><td>{metric("baseline",key)}</td><td>{metric("improved",key)}</td><td>{metric("refined",key)}</td><td>{metric("polished",key)}</td><td>{metric("touchup",key)}</td></tr>')
    cards=[]
    for case in cases:
        before=next((r for r in rounds['baseline']['records'] if r['case']==case['id']),{})
        after=next((r for r in rounds['refined']['records'] if r['case']==case['id']),{})
        chosen=selection.get(case['id'],{'run':after.get('run',''),'audit_round':'refined'})
        after=next((r for r in rounds[chosen['audit_round']]['records'] if r['case']==case['id']),after)
        notes=review_before.get('cases',{}).get(case['id'],{}).get('findings',[])
        final_notes=review_after.get('cases',{}).get(case['id'],{}).get('findings',[])
        run=after.get('run','');before_run=before.get('run','')
        links=f'<a href="../{esc(run)}/index.html">打开新版作品</a> <a href="../{esc(run)}/submission.zip">下载成果包</a> <a href="../{esc(run)}/main.py">生成源码</a>' if after.get('status')=='ready' else '<span>新版尚未完成</span>'
        cards.append(f'<section><h2>{esc(case["id"])}</h2><p>{esc(case["brief"])}</p><p>{links}</p><p>首轮：{esc(before.get("status"))}，{before.get("model_calls",0)} 次调用；最终版本的这次运行：{esc(after.get("status"))}，{after.get("model_calls",0)} 次调用（不含前序修订）。</p><h3>独立复核发现</h3><ul>'+''.join('<li>'+esc(n)+'</li>' for n in notes)+'</ul><h3>新版复核</h3><ul>'+''.join('<li>'+esc(n)+'</li>' for n in final_notes)+f'</ul><p><a href="visual-final/{esc(run)}-desktop.png">桌面截图</a> · <a href="visual-final/{esc(run)}-mobile.png">手机截图</a> · <a href="visual-final/{esc(run)}-code.png">代码界面</a> · <a href="visual-final/{esc(run)}-directory.png">文件目录</a> · <a href="visual-final/{esc(run)}-tests.png">测试过程</a></p><p><a href="../{esc(before_run)}/tests.json">首轮测试记录</a> · <a href="audit-{esc(chosen["audit_round"])}/{esc(run)}/audit.json">新版独立压力测试</a></p></section>')
    doc='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Auto Lexmount · 七作品迭代实验</title><style>*{box-sizing:border-box}table{font-size:13px}body{font:16px/1.8 system-ui;margin:0;background:#f5f4fa;color:#292735}main{max-width:1050px;margin:auto;padding:32px 20px}section,table{background:white;border:1px solid #e3dfee;border-radius:12px;padding:22px;margin:24px 0;width:100%}th,td{text-align:left;padding:10px;border-bottom:1px solid #eee}a{color:#5842a5;overflow-wrap:anywhere}p,li{overflow-wrap:anywhere}h1{line-height:1.3}small{color:#716b80}</style><main><h1>七作品生成 → 检查 → 改进 → 复跑</h1><p>DeepSeek 自动构建的公开文档资料工具。保留首轮失败，不把模型自评当作事实准确率。</p><table><tr><th>指标</th><th>冻结首轮</th><th>改进复跑</th><th>引用反馈修订</th><th>局部打磨</th><th>最终补检</th></tr>'''+''.join(metrics)+'''</table><p>新版复用原始来源快照；总耗时不可直接解释成性能提升。第三轮集合任务发生过一次调度重启并从检查点恢复，其总耗时包含中断时间，未返回请求的 token 用量未知。第三轮保留第二轮源码并通过反馈修订，不与从零生成的调用次数直接比较。七个主题属于同一种资料整理工作流，不能代表任意软件开发能力。</p><p><a href="comparison.json">完整指标与复核记录</a> · <a href="http://127.0.0.1:8765">打开 Agent 工作台</a></p>'''+''.join(cards)+'''<footer>局部打磨只对仍有问题的作品运行，列中的样本数不等于七件。模型评审仍存在漏报和误报，独立读稿记录一并保留。本轮未投稿。每件作品保留来源、源码、修复记录、隔离执行日志与网页。</footer></main></html>'''
    verification=read(lab/'verification.json',{})
    if verification.get('passed'):
        final_note=f"<p><strong>最终保留 {len(verification['works'])} 件作品：原始数量与来源要求全部通过；{verification['workflow_checks']} 项工作流输入变化检查、{verification['independent_checks']} 项独立复验全部通过。</strong></p>"
        doc=doc.replace('<p>DeepSeek 自动构建',final_note+'<p>DeepSeek 自动构建')
    doc=doc.replace('<table><tr>','<div style="overflow-x:auto"><table style="min-width:720px"><tr>',1).replace('</table><p>新版','</table></div><p>新版',1)
    (lab/'report.html').write_text(doc)
    print(json.dumps({name:{k:v for k,v in data.items() if k!='records'} for name,data in rounds.items()},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
