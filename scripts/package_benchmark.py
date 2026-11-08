"""Package the selected works, experiment records and current agent source, without secrets."""
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autolex.config import load_environment


def main():
    load_environment('.env');lab=Path('runs/batch7-lab')
    verification=json.loads((lab/'verification.json').read_text());assert verification['passed']
    selection=json.loads((lab/'final-runs.json').read_text())
    files={}
    def add(path,name):
        assert path.is_file() and not path.is_symlink(),path
        files[str(name)]=path
    # Keep top-level artifacts from all measured runs, including blocked attempts.
    for root in sorted(Path('runs').glob('b7-*')):
        if not (root/'state.json').is_file():continue
        for p in root.iterdir():
            if p.is_file() and not p.name.startswith('.'):
                add(p,Path(root.name)/p.name)
    for p in lab.glob('*.json'):add(p,Path('batch7-lab')/p.name)
    add(lab/'report.html','batch7-lab/report.html')
    for folder in ['baseline','improved','refined','polished','touchup','citation-audit-improved','visual-final']:
        for p in (lab/folder).glob('*'):
            if p.is_file():add(p,Path('batch7-lab')/folder/p.name)
    for data in selection.values():
        p=lab/('audit-'+data['audit_round'])/data['run']/'audit.json'
        add(p,Path('batch7-lab')/('audit-'+data['audit_round'])/data['run']/'audit.json')
    for folder in ['engine-baseline','engine-improved','engine-refined','engine-polished','engine-touchup']:
        for p in (lab/folder).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts:add(p,Path('batch7-lab')/p.relative_to(lab))
    for folder in ['autolex','scripts','tests']:
        for p in Path(folder).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix in {'.py','.js','.cjs','.html','.css','.svg'}:
                add(p,Path('agent-source')/p)
    for name in ['README.md','pyproject.toml','.env.example']:
        p=Path(name)
        if p.exists():add(p,Path('agent-source')/p)
    for p in lab.glob('*final.log'):add(p,Path('batch7-lab')/p.name)
    secrets=[os.environ.get(k,'').encode() for k in ['MODEL_API_KEY','LEXMOUNT_API_KEY','YOURS_API_KEY'] if len(os.environ.get(k,''))>8]
    out=Path('dist/seven-works-iteration.zip');out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('START_HERE.txt','打开 batch7-lab/report.html 查看七件最终作品、前后对比和截图。\nagent-source 是当前 Agent 源码，不含实际 API 密钥或发布账户配置。\n各最终作品根目录包含 main.py、input.json、output.json 和 submission.zip。复现须在隔离环境中运行。\n包内保留各轮顶层成果与测试记录；完整临时容器目录保留在原工作区，不重复打包。\n本轮没有投稿。\n')
        for name,path in sorted(files.items()):
            data=path.read_bytes()
            assert not any(secret in data for secret in secrets),'Secret found in '+str(path)
            archive.writestr(name,data)
    with zipfile.ZipFile(out) as archive:
        assert archive.testzip() is None
        assert all(name!='.env' and not name.endswith('/.env') and '.release-profile.json' not in name for name in archive.namelist())
    info={'path':str(out),'bytes':out.stat().st_size,'files':len(files)+1,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'secret_scan':'Configured API keys absent; actual .env and release profile excluded'}
    (lab/'bundle.json').write_text(json.dumps(info,ensure_ascii=False,indent=2));print(json.dumps(info,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
