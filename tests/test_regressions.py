import json,sys,copy
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import Mock
import pytest,yaml
from parser.deadline import extract
from crawlers.generic import GenericCrawler,canonical
from crawlers.custom.nju import NjuCrawler
from crawlers.base import HttpClient
from monitor_clock import MonitorClock
from database.state import notice_key

ROOT=Path(__file__).resolve().parents[1]
def config():return yaml.safe_load((ROOT/'config/settings.yaml').read_text(encoding='utf-8'))
def test_whitespace_dates():
    r=extract('报名截止 202 6 年 9 月 15 日 17 : 00','2026-08-01')
    assert r['registration_deadline']=='2026-09-15T17:00:00+08:00'
def test_real_nju_date_sentence():
    r=extract('“南京大学接收推荐免试研究生预报名系统”已于2026年8月3日12:00开放。南京大学建筑与城市规划学院接收推免生预报名自2026年8月3日12:00开始至2026年9月4日17:00截止。','2026-08-03')
    assert r['registration_start']=='2026-08-03T12:00:00+08:00'
    assert r['registration_deadline']=='2026-09-04T17:00:00+08:00'
def test_webplus_cross_category_duplicate():
    assert notice_key('https://yzb.nju.edu.cn/ab/cd/c47863a1234/page.htm')==notice_key('https://yzb.nju.edu.cn/ab/cd/c47865a1234/page.htm')
def test_vsb_duplicate():
    assert canonical('https://sud.whu.edu.cn/content.jsp?urltype=news.NewsContentUrl&wbtreeid=1521&wbnewsid=51211')=='https://sud.whu.edu.cn/info/1521/51211.htm'
def test_nju_embedded_data():
    cfg=config();site=next(s for s in yaml.safe_load((ROOT/'config/sites.yaml').read_text(encoding='utf-8'))['sites'] if s['id']=='nju-1')
    c=NjuCrawler(site,HttpClient(cfg,MonitorClock(cfg)))
    data=[{'infolist':[{'title':'2027年接收推免生通知','url':'http://arch.nju.edu.cn/rcpy/yjs/pyfa/20260909/i416044.html','daytime':'2026-09-09'},{'title':'外部不监控','url':'https://other.example/a','daytime':'2026-09-09'}]}]
    rows,_=c.parse('<script>var dataList='+json.dumps(data)+';var next=2;</script>',site['list_url'])
    assert len(rows)==1;assert rows[0]['publish_date']=='2026-09-09'
def test_inline_span_date_is_not_split():
    cfg=config();site=yaml.safe_load((ROOT/'config/sites.yaml').read_text(encoding='utf-8'))['sites'][0]
    client=HttpClient(cfg,MonitorClock(cfg));response=Mock();response.headers={'Content-Type':'text/html'}
    response.text='<meta name="PubDate" content="2026-09-01"><div class="wp_articlecontent"><p>报名<span>截止</span><strong>9月15日17:00</strong></p></div>'
    client.get=Mock(return_value=response)
    r=GenericCrawler(site,client).detail({'url':'https://www.ccea.zju.edu.cn/2026/0901/c123a456/page.htm'})
    assert extract(r['text'],r['publish_date'])['registration_deadline']=='2026-09-15T17:00:00+08:00'
def test_main_26_september_no_clients(monkeypatch,capsys):
    import main,requests,smtplib
    cfg=config();clock=MonitorClock(cfg,datetime(2026,9,26,tzinfo=ZoneInfo('Asia/Shanghai')))
    monkeypatch.setattr(main,'MonitorClock',lambda _:clock);monkeypatch.setattr(sys,'argv',['main.py','--run-once'])
    spy=Mock(side_effect=AssertionError('Network forbidden'))
    monkeypatch.setattr(requests,'Session',spy);monkeypatch.setattr(smtplib,'SMTP_SSL',spy)
    assert main.main()==0;spy.assert_not_called()
    assert capsys.readouterr().out.strip()=='Monitoring period has ended.'
