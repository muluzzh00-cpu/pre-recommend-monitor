import copy, json
from collections import Counter
from pathlib import Path
from unittest.mock import Mock
import pytest, requests, yaml
from tests.test_hourly_window import at, row
from crawlers.base import HttpClient
from crawlers.generic import GenericCrawler
from monitor_clock import MonitorClock, PeriodEnded
from database.state import StateStore
from engine import run

ROOT=Path(__file__).resolve().parents[1]

def setup(tmp_path,monkeypatch,error,recover):
    cfg=yaml.safe_load((ROOT/'config/settings.yaml').read_text(encoding='utf-8'))
    cfg['crawler']['recovery_delay_seconds']=0
    site=yaml.safe_load((ROOT/'config/sites.yaml').read_text(encoding='utf-8'))['sites'][0]
    second={**site,'id':'healthy'};calls=[];counts=Counter()
    def crawl(self):
        name=self.site['id'];calls.append(name);counts[name]+=1
        if name==site['id'] and (not recover or counts[name]==1):raise error
        return [row()]
    monkeypatch.setattr(GenericCrawler,'crawl',crawl)
    detail=Mock(return_value={'text':'2027年接收推免研究生，报名截止2026年9月20日17:00','publish_date':'2026-09-11','notes':[]})
    monkeypatch.setattr(GenericCrawler,'detail',lambda self,item:detail(item))
    clock=MonitorClock(cfg,at());client=HttpClient(cfg,clock);store=StateStore(tmp_path/'state');sender=Mock()
    return cfg,[site,second],clock,client,store,sender,calls,detail

def test_recovers_failed_source_only_without_duplicate_email(tmp_path,monkeypatch):
    cfg,sites,clock,client,store,sender,calls,detail=setup(tmp_path,monkeypatch,requests.ConnectionError('Network is unreachable'),True)
    assert run(cfg,sites,clock,client,store,sender,tmp_path/'r')==0
    assert calls==[sites[0]['id'],'healthy',sites[0]['id']]
    assert detail.call_count==1 and sender.send.call_count==1
    r=json.loads((tmp_path/'r/latest.json').read_text(encoding='utf-8'))
    assert r['recovered_sources']==[sites[0]['id']] and not r['failed_sources']
    failure=store.data['daily_stats']['2026-09-11']['failures'][sites[0]['id']]
    assert failure['count']==1 and failure['recovered']

def test_persistent_failure_stays_red_and_other_source_sends(tmp_path,monkeypatch):
    cfg,sites,clock,client,store,sender,calls,detail=setup(tmp_path,monkeypatch,requests.Timeout('network timeout'),False)
    assert run(cfg,sites,clock,client,store,sender,tmp_path/'r')==2
    assert len(calls)==3;assert sender.send.call_count==1
    assert store.data['health'][sites[0]['id']]['recovery_attempted']
    assert not store.data['health'][sites[0]['id']]['ok']

@pytest.mark.parametrize('error',[requests.exceptions.SSLError('certificate failed'),requests.HTTPError('403'),ValueError('selector failed')])
def test_no_late_retry_for_certificate_http_or_parser_failures(tmp_path,monkeypatch,error):
    cfg,sites,clock,client,store,sender,calls,detail=setup(tmp_path,monkeypatch,error,False)
    assert run(cfg,sites,clock,client,store,sender,tmp_path/'r')==2
    assert len(calls)==2

def test_end_guard_before_recovery_request(tmp_path,monkeypatch):
    cfg,sites,clock,client,store,sender,calls,detail=setup(tmp_path,monkeypatch,requests.ConnectionError(),True)
    def end_during_wait(seconds):clock._now=at('2026-09-26T00:00:00')
    monkeypatch.setattr('engine.time.sleep',end_during_wait)
    with pytest.raises(PeriodEnded):run(cfg,sites,clock,client,store,sender,tmp_path/'r')
    assert calls==[sites[0]['id'],'healthy'];sender.send.assert_not_called()

def test_all_workflows_use_node24_action_versions():
    expected={'actions/checkout@v5','actions/setup-python@v6','actions/upload-artifact@v6'}
    for path in (ROOT/'.github/workflows').glob('*.yml'):
        data=yaml.load(path.read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
        uses={s['uses'] for j in data['jobs'].values() for s in j['steps'] if 'uses' in s}
        assert uses==expected
