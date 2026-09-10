from pathlib import Path
from urllib.parse import urlsplit
import yaml

ROOT=Path(__file__).resolve().parents[1]
def test_all_seven_schools_have_core_and_university_sources():
    sites=yaml.safe_load((ROOT/'config/sites.yaml').read_text(encoding='utf-8'))['sites']
    assert len({s['id'] for s in sites})==len(sites)
    universities={s['university'] for s in sites};assert len(universities)==7
    required={'university','college','page_name','list_url','domain','page_type','title_selector','date_selector','link_selector','crawler_type','enabled','source_level'}
    for s in sites:
        assert required<=s.keys()
        assert urlsplit(s['list_url']).hostname==s['domain']
        assert s['domain'].endswith('.'+s['university_domain'])
        assert s['source_level'] in ('college','university')
    for u in universities:
        assert {s['source_level'] for s in sites if s['university']==u and s['enabled']}=={'college','university'}
def test_hourly_workflow_and_state_concurrency():
    # YAML 1.1 treats on as a boolean; BaseLoader preserves GitHub's YAML key.
    workflow=yaml.load((ROOT/'.github/workflows/monitor.yml').read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
    assert workflow['on']['schedule'][0]['cron']=='17 * * * *'
    assert 'workflow_dispatch' in workflow['on']
    assert workflow['concurrency']['cancel-in-progress']=='false'
    assert workflow['permissions']['contents']=='write'
    assert any('main.py --run-once --git-state' in s.get('run','') for s in workflow['jobs']['monitor']['steps'])
