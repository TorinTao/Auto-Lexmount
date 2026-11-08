"""Verify final artifact integrity and all seven original numeric/source contracts."""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import urldefrag

def read(path):return json.loads(path.read_text())
def main():
    p=argparse.ArgumentParser();p.add_argument('--lab',default='runs/batch7-lab');p.add_argument('--round',default='refined');p.add_argument('--selection');p.add_argument('--visual-round');args=p.parse_args()
    lab=Path(args.lab);cases=read(lab/'cases.json');records=[]
    selection=read(Path(args.selection)) if args.selection else {}
    for case in cases:
        chosen=selection.get(case['id'],{'run':f'b7-{args.round}-{case["id"]}','audit_round':args.round})
        root=Path('runs')/chosen['run'];state=read(root/'state.json');out=read(root/'output.json')
        assert state['status']=='ready' and not state['demo'],root
        for name,digest in state['hashes'].items():
            path=root/name
            assert not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==digest,(root,name)
        points=sum(len(i.get('points',[])) for i in out['items']);conclusions=len(out['conclusions'])
        assert case['points'][0]<=points<=case['points'][1] and case['conclusions'][0]<=conclusions<=case['conclusions'][1],root
        expected={urldefrag(u.rstrip('。，.;'))[0] for u in re.findall(r'https?://[^\s]+',case['brief'])}
        assert {i['url'] for i in out['items']}==expected,root
        for name in ['tests.json','quality.json','citations.json','review.json']:
            assert read(root/name)['passed'],(root,name)
        assert read(root/'quality.json')['version']>=3
        audit=read(lab/('audit-'+chosen['audit_round'])/root.name/'audit.json');assert audit['passed'],root
        manifest=read(root/'manifest.json')
        assert 'citations.json' in manifest
        with zipfile.ZipFile(root/'submission.zip') as archive:
            assert set(archive.namelist())==set(manifest)|{'manifest.json'}
            for name,digest in manifest.items():assert hashlib.sha256(archive.read(name)).hexdigest()==digest,(root,name)
        assert not (root/'submission-state.json').exists(),root
        records.append({'run':root.name,'points':points,'conclusions':conclusions,'workflow_checks':len(read(root/'quality.json')['checks']),
                        'independent_checks':len(audit['checks']),'files_in_manifest':len(manifest),'archive_sha256':hashlib.sha256((root/'submission.zip').read_bytes()).hexdigest()})
    visual=read(lab/('visual-'+(args.visual_round or args.round))/'browser-checks.json')
    assert visual['passed'] and {r['run'] for r in visual['runs']}=={r['run'] for r in records}
    report={'passed':True,'works':records,'workflow_checks':sum(r['workflow_checks'] for r in records),'independent_checks':sum(r['independent_checks'] for r in records),
            'browser_runs':len(visual['runs']),'scope':'Numeric/source contracts, recorded gates, immutable hashes, package contents and browser checks. Semantic quality is separately recorded by the reviewer; not an official score.'}
    (lab/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
