import copy, json, smtplib, subprocess
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo
import pytest, requests, yaml
from monitor_clock import MonitorClock, PeriodEnded
from crawlers.base import HttpClient, CrawlError
from crawlers.generic import GenericCrawler
from parser.deadline import extract, urgency
from parser.relevance import classify
from database.state import StateStore, digest
from engine import run, delivery

ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture
def cfg():return yaml.safe_load((ROOT/'config/settings.yaml').read_text(encoding='utf-8'))
@pytest.fixture
def site():return yaml.safe_load((ROOT/'config/sites.yaml').read_text(encoding='utf-8'))['sites'][0]
def now(day=11,hour=12):return datetime(2026,9,day,hour,tzinfo=ZoneInfo('Asia/Shanghai'))
def notice(**kw):
    x={'url':'http://www.ccea.zju.edu.cn/2026/0910/c18473a123/page.htm','title':'2027年接收推荐免试研究生实施细则','publish_date':'2026-09-10','university':'浙江大学','college':'建筑工程学院','source_level':'college','matched':True,'priority':5,'relevance_score':17,'category':'推免','is_direct_phd':False,'registration_deadline':'2026-09-15T12:00:00+08:00','material_deadline':None,'interview_date':None,'notes':[]}
    x.update(kw);return x

@pytest.mark.parametrize('title',['2027年接收推荐免试研究生工作实施细则','2027年研究生预报名通知','2027年直博生招生办法','2027年研究生招生工作实施细则','接收优秀应届本科毕业生通知'])
def test_loose_keywords(cfg,site,title):assert classify(title,'',site,cfg,'2026-09-10',now())['matched']
def test_college_strong_is_highest(cfg,site):assert classify('接收推免生','',site,cfg,None,now())['priority']==5
def test_other_college(cfg,site):
    site['source_level']='university'
    assert not classify('2027年医学院接收推免生','',site,cfg,None,now())['matched']
def test_old_pinned(cfg,site):assert not classify('2025年接收推免生','',site,cfg,'2024-09-12',now())['matched']
def test_deadline_year_from_publication():
    r=extract('报名截止至9月15日17:00','2026-09-01')
    assert r['registration_deadline']=='2026-09-15T17:00:00+08:00';assert r['deadline_parse_status']=='parsed'
@pytest.mark.parametrize('text,pub',[('报名截止9月15日17:00',None),('报名截止9月15日','2026-09-01'),('报名截止2026年2月30日17:00','2026-09-01')])
def test_uncertain(text,pub):
    r=extract(text,pub);assert r['registration_deadline'] is None; assert r['deadline_parse_status']=='uncertain';assert r['deadline_evidence']
def test_range_and_material():
    r=extract('报名时间2026年9月10日10:00至2026年9月15日17:00。材料提交截止9月16日18:00。面试时间9月18日上午9:00','2026-09-01')
    assert r['registration_start']=='2026-09-10T10:00:00+08:00'
    assert r['registration_deadline']=='2026-09-15T17:00:00+08:00'
    assert r['material_deadline']=='2026-09-16T18:00:00+08:00'
    assert r['interview_date']=='2026-09-18T09:00:00+08:00'
def test_multiple_batches():
    r=extract('第一批报名截止9月12日17:00；第二批报名截止9月18日17:00','2026-09-01')
    assert r['registration_deadline'] is None; assert r['deadline_parse_status']=='uncertain'
def test_midnight():assert extract('报名截止9月12日24:00','2026-09-01')['registration_deadline']=='2026-09-13T00:00:00+08:00'
@pytest.mark.parametrize('hours,label',[(10,'🔴'),(48,'🟠'),(100,'🟡'),(200,'🟢'),(-1,'已截止')])
def test_urgency(hours,label):assert urgency(notice(registration_deadline=(now()+timedelta(hours=hours)).isoformat()),now())[0].startswith(label)

def test_date_missing_and_selector(cfg,site):
    c=GenericCrawler(site,HttpClient(cfg,MonitorClock(cfg,now())))
    html='<li><a href="/2026/0910/c18473a123/page.htm">2027年接收推免生通知</a></li>'
    rows,_=c.parse(html,site['list_url']); assert rows[0]['publish_date'] is None
    site['link_selector']='#missing a'
    with pytest.raises(CrawlError):c.parse(html,site['list_url'])

@pytest.mark.parametrize('status',[403,404,429,500])
def test_http_failures(cfg,monkeypatch,status):
    cfg['crawler'].update(retries=0,interval_seconds=0)
    c=HttpClient(cfg,MonitorClock(cfg,now())); monkeypatch.setattr(c,'check_robots',lambda u:None)
    response=requests.Response();response.status_code=status;response._content=b'x'*100
    monkeypatch.setattr(c,'_request',lambda u:response)
    with pytest.raises(requests.HTTPError):c.get('https://a.zju.edu.cn/a')
@pytest.mark.parametrize('error',[requests.Timeout,requests.ConnectionError,requests.exceptions.SSLError])
def test_network_failures(cfg,monkeypatch,error):
    cfg['crawler'].update(retries=0,interval_seconds=0)
    c=HttpClient(cfg,MonitorClock(cfg,now()));monkeypatch.setattr(c,'check_robots',lambda u:None)
    monkeypatch.setattr(c.session,'get',Mock(side_effect=error('test')))
    with pytest.raises(error):c.get('https://a.zju.edu.cn/a')

def test_persistence_and_alias(tmp_path):
    s=StateStore(tmp_path);k,changed=s.upsert(notice(content_hash='same'),now());assert changed;s.save()
    s=StateStore(tmp_path);assert not s.upsert(notice(content_hash='same'),now())[1]
    assert not s.upsert(notice(url='https://a.zju.edu.cn/other',content_hash='same'),now())[1]
    assert s.upsert(notice(url='https://a.zju.edu.cn/different',content_hash='different'),now())[1]
    assert s.upsert(notice(title='2027年接收推免通知（报名延期）',content_hash='changed'),now())[1]
def test_corrupt_state_refuses_reset(tmp_path):
    (tmp_path/'state.json').write_text('broken')
    with pytest.raises(json.JSONDecodeError):StateStore(tmp_path)
def test_save_failure_no_mail(tmp_path,monkeypatch):
    s=StateStore(tmp_path);sender=Mock();monkeypatch.setattr(s,'save',Mock(side_effect=OSError('disk failure')))
    with pytest.raises(OSError):delivery(s,sender,'k','subject','html',lambda:None)
    sender.send.assert_not_called()
def test_smtp_uncertain_no_duplicate(tmp_path):
    s=StateStore(tmp_path);sender=Mock();sender.send.side_effect=TimeoutError()
    assert not delivery(s,sender,'k','subject','html',lambda:None)
    s=StateStore(tmp_path);assert not delivery(s,sender,'k','subject','html',lambda:None)
    assert sender.send.call_count==1
def test_smtp_configuration_and_tls(monkeypatch):
    for k,v in {'EMAIL_HOST':'smtp.gmail.com','EMAIL_PORT':'465','EMAIL_USER':'sender@example.com','EMAIL_PASSWORD':'test-only','EMAIL_TO':'muluzzh00@gmail.com'}.items():monkeypatch.setenv(k,v)
    server=Mock();server.__enter__=Mock(return_value=server);server.__exit__=Mock(return_value=False);server.send_message.return_value={}
    monkeypatch.setattr(smtplib,'SMTP_SSL',Mock(return_value=server))
    from notifier.email import EmailSender
    EmailSender().send('测试','<p>测试</p>','id')
    msg=server.send_message.call_args[0][0]
    assert msg['To']=='muluzzh00@gmail.com';assert msg.get_content_type()=='multipart/alternative';server.login.assert_called_once()

def setup_engine(cfg,site,monkeypatch,rows=None):
    rows=rows if rows is not None else [{'title':notice()['title'],'url':notice()['url'],'publish_date':'2026-09-10'}]
    monkeypatch.setattr(GenericCrawler,'crawl',lambda self:copy.deepcopy(rows))
    monkeypatch.setattr(GenericCrawler,'detail',lambda self,item:{'text':'2027年接收推荐免试研究生。报名截止2026年9月15日12:00','publish_date':'2026-09-10','notes':[]})
    return HttpClient(cfg,MonitorClock(cfg,now()))
def test_two_complete_runs(tmp_path,cfg,site,monkeypatch):
    c=setup_engine(cfg,site,monkeypatch);sender=Mock();s=StateStore(tmp_path/'state')
    assert run(cfg,[site],c.clock,c,s,sender,tmp_path/'report')==0
    assert sender.send.call_count==1
    s=StateStore(tmp_path/'state')
    assert run(cfg,[site],c.clock,c,s,sender,tmp_path/'report')==0
    assert sender.send.call_count==1
    assert json.loads((tmp_path/'report/latest.json').read_text())['new_or_updated']==0

def test_three_reminders_and_daily(tmp_path,cfg,site,monkeypatch):
    c=setup_engine(cfg,site,monkeypatch,[]);sender=Mock();s=StateStore(tmp_path/'state')
    key,_=s.upsert(notice(),now());s.data['deliveries'][f'new:{key}:1']={'status':'sent'};s.data['notices'][key]['notified']=True;s.save()
    deadline=datetime.fromisoformat(notice()['registration_deadline'])
    for hours,threshold in [(71,72),(23,24),(5,6)]:
        clock=MonitorClock(cfg,deadline-timedelta(hours=hours));c.clock=clock
        run(cfg,[site],clock,c,s,sender,tmp_path/'report')
        before=sender.send.call_count
        run(cfg,[site],clock,c,StateStore(tmp_path/'state'),sender,tmp_path/'report')
        assert sender.send.call_count==before
        assert s.data['notices'][key][f'reminded_{threshold}h']
    assert sender.send.call_count==3
    c.clock=MonitorClock(cfg,now(16,22))
    run(cfg,[site],c.clock,c,s,sender,tmp_path/'report'); count=sender.send.call_count
    run(cfg,[site],c.clock,c,StateStore(tmp_path/'state'),sender,tmp_path/'report')
    assert sender.send.call_count==count==4
    assert s.data['daily_reports']['2026-09-16']
def test_single_source_failure_continues(tmp_path,cfg,site,monkeypatch):
    c=setup_engine(cfg,site,monkeypatch);bad=copy.deepcopy(site);bad['id']='bad'
    def crawl(self):
        if self.site['id']=='bad':raise requests.Timeout('simulated timeout')
        return []
    monkeypatch.setattr(GenericCrawler,'crawl',crawl)
    s=StateStore(tmp_path/'s');run(cfg,[bad,site],c.clock,c,s,Mock(),tmp_path/'r')
    assert s.data['health'][site['id']]['ok'];assert not s.data['health']['bad']['ok']
def test_after_end_no_http(tmp_path,cfg,site,monkeypatch):
    clock=MonitorClock(cfg,now(26));client=HttpClient(cfg,clock)
    spy=Mock(side_effect=AssertionError('No HTTP allowed'));monkeypatch.setattr(client.session,'get',spy)
    with pytest.raises(PeriodEnded,match='Monitoring period has ended.'):
        run(cfg,[site],clock,client,StateStore(tmp_path/'s'),Mock(),tmp_path/'r')
    with pytest.raises(PeriodEnded):client.get(site['list_url'])
    spy.assert_not_called();assert client.requests_count==0
def test_clock_window(cfg):
    assert MonitorClock(cfg,now(9)).status()=='before'
    assert MonitorClock(cfg,now(25,23)).status()=='active'
    assert MonitorClock(cfg,now(26)).status()=='ended'
def test_git_roundtrip(tmp_path):
    remote=tmp_path/'remote.git';subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
    d=tmp_path/'state';d.mkdir()
    def g(*args):subprocess.run(['git','-C',str(d),*args],check=True,capture_output=True)
    g('init');g('config','user.name','Monitor Test');g('config','user.email','test@example.com');g('remote','add','origin',str(remote))
    s=StateStore(d,True);s.upsert(notice(),now());s.save()
    clone=tmp_path/'restored';subprocess.run(['git','clone','--branch','monitor-state',str(remote),str(clone)],check=True,capture_output=True)
    restored=StateStore(clone);assert len(restored.data['notices'])==1
    assert not restored.upsert(notice(),now())[1]
