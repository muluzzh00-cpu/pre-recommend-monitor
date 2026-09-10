import copy, json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo
import pytest, yaml, requests
from crawlers.base import HttpClient
from crawlers.generic import GenericCrawler
from crawlers.custom.nju import NjuCrawler
from database.state import StateStore, notice_key
from engine import run
from monitor_clock import MonitorClock
from parser.publication import publication, publication_window

ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo('Asia/Shanghai')

@pytest.fixture
def cfg():return yaml.safe_load((ROOT/'config/settings.yaml').read_text(encoding='utf-8'))

@pytest.fixture
def site():return yaml.safe_load((ROOT/'config/sites.yaml').read_text(encoding='utf-8'))['sites'][0]

def at(value='2026-09-11T10:07:00'):return datetime.fromisoformat(value).replace(tzinfo=TZ)

def row(number=1, day='2026-09-11', stamp=None, title=None):
    return {'url':f'https://www.ccea.zju.edu.cn/2026/0911/c18473a{number}/page.htm',
            'title':title or f'2027年接收推荐免试研究生通知 {number}', 'publish_date':day,'publish_time':stamp}

def harness(tmp_path,cfg,site,monkeypatch,rows,baseline=False):
    store=StateStore(tmp_path/'state')
    if not baseline:store.data['monitoring_policy']={'version':2,'baseline_sources':[site['id']]}
    monkeypatch.setattr(GenericCrawler,'crawl',lambda self:copy.deepcopy(rows))
    detail=Mock(side_effect=lambda item:{'text':'2027年接收推荐免试研究生，报名截止2026年9月20日17:00。',
                   'publish_date':item.get('publish_date'),'publish_time':item.get('publish_time'),'notes':[]})
    monkeypatch.setattr(GenericCrawler,'detail',lambda self,item:detail(item))
    sender=Mock()
    def execute(stamp=None):
        clock=MonitorClock(cfg,stamp or at());client=HttpClient(cfg,clock)
        return run(cfg,[site],clock,client,store,sender,tmp_path/'report')
    return store,sender,detail,execute

@pytest.mark.parametrize('text,day,stamp',[
    ('2026-09-11','2026-09-11',None),
    ('2026年9月11日 09:35','2026-09-11','2026-09-11T09:35:00+08:00'),
    ('2026-09-11 09:35:42','2026-09-11','2026-09-11T09:35:42+08:00'),
    ('2026-09-11 09:35:42.123456','2026-09-11','2026-09-11T09:35:42.123456+08:00'),
    ('2026-09-10T17:35:42Z','2026-09-11','2026-09-11T01:35:42+08:00'),
    ('2026-09-11T01:35:42+00:00','2026-09-11','2026-09-11T09:35:42+08:00'),
    ('2026-02-30 09:35',None,None),
])
def test_publication_precision(text,day,stamp):
    assert publication(text)=={'publish_date':day,'publish_time':stamp}

@pytest.mark.parametrize('stamp,allowed',[
    ('2026-09-11T08:51:59+08:00',False),('2026-09-11T08:52:00+08:00',True),
    ('2026-09-11T09:00:00+08:00',True),('2026-09-11T10:07:00+08:00',True),
    ('2026-09-11T10:07:01+08:00',False),('2026-09-11T01:00:00+00:00',True),
])
def test_actual_delayed_start_and_inclusive_75_minutes(cfg,stamp,allowed):
    assert publication_window(row(stamp=stamp),at(),cfg)[0] is allowed

def test_midnight_window_uses_beijing_date(cfg):
    moment=at('2026-09-11T00:20:00')
    assert publication_window(row(day='2026-09-10',stamp='2026-09-10T23:15:00+08:00'),moment,cfg)[0]
    assert not publication_window(row(day='2026-09-10'),moment,cfg)[0]
    assert publication_window(row(),moment,cfg)[0]

def test_today_first_seen_then_known_no_detail_no_repeat(tmp_path,cfg,site,monkeypatch):
    store,sender,detail,execute=harness(tmp_path,cfg,site,monkeypatch,[row()])
    assert execute()==0;assert sender.send.call_count==1;assert detail.call_count==1
    saved=store.data['notices'][notice_key(row()['url'])]
    assert saved['potential_new_notice'];assert saved['publish_time'] is None
    assert saved['first_seen_time']==at().isoformat()
    execute(at()+timedelta(hours=1))
    assert sender.send.call_count==1;assert detail.call_count==1
    restored=StateStore(tmp_path/'state').data['notices'][notice_key(row()['url'])]
    assert restored['first_seen_time']==at().isoformat()
    assert restored['last_seen_time']==(at()+timedelta(hours=1)).isoformat()

def test_old_future_and_outside_window_never_fetch_details(tmp_path,cfg,site,monkeypatch):
    rows=[row(1,day='2026-09-10'),row(2,stamp='2026-09-11T07:00:00+08:00'),row(3,stamp='2026-09-11T11:00:00+08:00')]
    store,sender,detail,execute=harness(tmp_path,cfg,site,monkeypatch,rows)
    execute();execute(at()+timedelta(minutes=10))
    detail.assert_not_called();sender.send.assert_not_called()
    assert len(store.data['notices'])==3

def test_baseline_saves_old_rows_and_only_clear_recent_high_priority_digest(tmp_path,cfg,site,monkeypatch):
    rows=[row(1,day='2026-09-09'),row(2,day='2026-09-10'),
          row(3,title='2027年研究生招生工作通知'),row(4,day='2025-09-11',title='2025年推免通知公告'),
          row(5,day=None)]
    store,sender,detail,execute=harness(tmp_path,cfg,site,monkeypatch,rows,baseline=True)
    execute()
    assert len(store.data['notices'])==5;assert sender.send.call_count==1
    eligible=[n for n in store.data['notices'].values() if n['new_notification_eligible']]
    assert [n['url'] for n in eligible]==[rows[1]['url']]
    assert detail.call_count==2 # one eligible notice; one unknown date verified once
    execute(at()+timedelta(hours=1));assert sender.send.call_count==1;assert detail.call_count==2

def test_empty_history_baseline_sends_no_digest(tmp_path,cfg,site,monkeypatch):
    rows=[row(i,day='2026-08-20') for i in range(1,41)]
    store,sender,detail,execute=harness(tmp_path,cfg,site,monkeypatch,rows,baseline=True)
    execute();sender.send.assert_not_called();detail.assert_not_called()
    assert len(store.data['notices'])==40

def test_detail_precision_rechecks_today_date_and_rejects_old_hour(tmp_path,cfg,site,monkeypatch):
    store,sender,detail,execute=harness(tmp_path,cfg,site,monkeypatch,[row()])
    detail.side_effect=None;detail.return_value={'text':'2027年推免报名通知','publish_date':'2026-09-11','publish_time':'2026-09-11T07:00:00+08:00','notes':[]}
    execute();sender.send.assert_not_called()
    assert store.data['notices'][notice_key(row()['url'])]['publish_time']=='2026-09-11T07:00:00+08:00'

def test_unknown_date_is_checked_once_then_daily_manual_review(tmp_path,cfg,site,monkeypatch):
    store,sender,detail,execute=harness(tmp_path,cfg,site,monkeypatch,[row(day=None)])
    execute();sender.send.assert_not_called();assert detail.call_count==1
    execute(at('2026-09-11T22:17:00'));assert detail.call_count==1;assert sender.send.call_count==1
    assert '今日发布时间待核实' in sender.send.call_args[0][1]

def test_unknown_date_can_be_resolved_from_detail(tmp_path,cfg,site,monkeypatch):
    store,sender,detail,execute=harness(tmp_path,cfg,site,monkeypatch,[row(day=None)])
    detail.side_effect=None;detail.return_value={'text':'2027年推免报名通知','publish_date':'2026-09-11','publish_time':None,'notes':[]}
    execute();assert sender.send.call_count==1

def test_same_school_same_title_different_url_skips_detail(tmp_path,cfg,site,monkeypatch):
    rows=[row(1),row(2,title=row(1)['title'])]
    store,sender,detail,execute=harness(tmp_path,cfg,site,monkeypatch,rows)
    execute();assert detail.call_count==1;assert len(store.data['notices'])==1
    assert rows[1]['url'] in next(iter(store.data['notices'].values()))['aliases']

def test_existing_production_state_migrates_without_replay_or_losing_flags(tmp_path,cfg,site,monkeypatch):
    store,sender,detail,execute=harness(tmp_path,cfg,site,monkeypatch,[row()])
    execute();old=copy.deepcopy(store.data['notices']);deliveries=copy.deepcopy(store.data['deliveries'])
    del store.data['monitoring_policy']
    for n in store.data['notices'].values():n.pop('publish_time');n.pop('new_notification_eligible')
    sender.reset_mock();detail.reset_mock();execute(at()+timedelta(hours=1))
    sender.send.assert_not_called();detail.assert_not_called()
    assert store.data['deliveries']==deliveries
    for k,n in store.data['notices'].items():
        assert n['first_seen_time']==old[k]['first_seen_time'];assert n['notified']==old[k]['notified']
        assert n['reminded_72h']==old[k]['reminded_72h'];assert n['publish_time'] is None

def test_renamed_historical_notice_keeps_known_deadline(tmp_path,cfg,site,monkeypatch):
    rows=[row()]
    store,sender,detail,execute=harness(tmp_path,cfg,site,monkeypatch,rows)
    execute();before=copy.deepcopy(store.data['notices'][notice_key(row()['url'])])
    rows[0].update(title='2027年接收推免生通知（标题修订）',publish_date='2026-09-09')
    execute(at()+timedelta(hours=1))
    after=store.data['notices'][notice_key(row()['url'])]
    assert detail.call_count==1;assert sender.send.call_count==1
    assert after['matched'] and after['notified'] and after['registration_deadline']==before['registration_deadline']

def test_daily_counts_whole_day_and_preserves_recovered_failures(tmp_path,cfg,site,monkeypatch):
    store,sender,detail,execute=harness(tmp_path,cfg,site,monkeypatch,[row()])
    execute(at('2026-09-11T09:00:00'))
    monkeypatch.setattr(GenericCrawler,'crawl',Mock(side_effect=requests.ConnectionError('temporary')))
    assert execute(at('2026-09-11T12:00:00'))==2
    monkeypatch.setattr(GenericCrawler,'crawl',lambda self:[])
    execute(at('2026-09-11T22:17:00'))
    html=sender.send.call_args[0][1]
    assert '今日新通知：1' in html and '今日高优先级通知：1' in html
    assert '本轮失败页面：0' in html and '今日曾失败页面：1' in html and '今日失败次数：1' in html
    assert '今日运行次数：3' in html and '恢复后仍保留' in html

def test_list_limit_stops_pagination_and_preserves_publish_time(cfg,site):
    client=HttpClient(cfg,MonitorClock(cfg,at()))
    def page(start):
        return ''.join(f'<li><a href="/2026/0911/c18473a{i}/page.htm">2027年推免通知 {i}</a><span class="date">2026-09-11 09:30:15</span></li>' for i in range(start,start+20))+'<a href="next.htm">下一页</a>'
    client.get=Mock(side_effect=[Mock(text=page(1)),Mock(text=page(21)),Mock(text=page(41))])
    result=GenericCrawler(site,client).crawl()
    assert len(result)==40;assert client.get.call_count==2
    assert result[0]['publish_time']=='2026-09-11T09:30:15+08:00'

def test_nju_embedded_latest_cap_and_precision(cfg,site):
    data=[{'infolist':[{'title':f'2027年推免通知 {i}','url':row(i)['url'],'daytime':'2026-09-11 09:30'} for i in range(start,start+30)]} for start in (1,31,61)]
    client=HttpClient(cfg,MonitorClock(cfg,at()))
    result,_=NjuCrawler(site,client).parse('<script>var dataList='+json.dumps(data)+';</script>',site['list_url'])
    assert len(result)==40;assert result[0]['publish_time']=='2026-09-11T09:30:00+08:00'

def test_publication_header_time_not_deadline(cfg,site):
    client=HttpClient(cfg,MonitorClock(cfg,at()))
    client.get=Mock(return_value=Mock(headers={'Content-Type':'text/html'},text='<meta name="PubDate" content="2026-09-11 09:35:27"><div class="wp_articlecontent">报名截止2026-09-20 17:00</div>'))
    result=GenericCrawler(site,client).detail(row())
    assert result['publish_time']=='2026-09-11T09:35:27+08:00'

def test_known_notice_can_record_list_precision_without_reanalysis(tmp_path,cfg,site,monkeypatch):
    rows=[row()]
    store,sender,detail,execute=harness(tmp_path,cfg,site,monkeypatch,rows)
    execute();rows[0]['publish_time']='2026-09-11T09:35:00+08:00'
    execute(at()+timedelta(hours=1))
    saved=store.data['notices'][notice_key(row()['url'])]
    assert saved['publish_time']=='2026-09-11T09:35:00+08:00'
    assert detail.call_count==1 and sender.send.call_count==1

def test_html_time_datetime_attribute(cfg,site):
    client=HttpClient(cfg,MonitorClock(cfg,at()))
    rows,_=GenericCrawler(site,client).parse('<li><a href="/2026/0911/c18473a111/page.htm">2027年推免通知公告</a><time datetime="2026-09-11T01:35:00Z">2026-09-11</time></li>',site['list_url'])
    assert rows[0]['publish_time']=='2026-09-11T09:35:00+08:00'
