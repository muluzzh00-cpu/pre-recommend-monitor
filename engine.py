import json, logging, time
from collections import deque
import requests
from pathlib import Path
from datetime import datetime
from crawlers.generic import GenericCrawler, canonical
from crawlers.custom import CUSTOM
from monitor_clock import PeriodEnded
from parser.relevance import classify
from parser.deadline import extract, urgency, effective_deadline
from database.state import digest, notice_key
from notifier.render import render_notices, render_health
from parser.publication import publication_window, baseline_relevant

def title_identity(university,title):
    return university,''.join(title.split())

def initialize_policy(store,sites,now):
    if 'monitoring_policy' not in store.data:
        # Existing production records become the baseline without resetting delivery/reminder flags.
        existing=bool(store.data['notices'])
        store.data['monitoring_policy']={'version':2,'activated_at':now.isoformat(),
            'baseline_sources':[s['id'] for s in sites] if existing else []}
        for item in store.data['notices'].values():
            item.setdefault('publish_time',None)
            item.setdefault('new_notification_eligible',False)
    return store.data['monitoring_policy']

def record_daily_health(store,health,now):
    day=now.date().isoformat()
    daily=store.data.setdefault('daily_stats',{}).setdefault(day,{'runs':0,'failures':{}})
    daily['runs']+=1;daily['last_run_at']=now.isoformat()
    for key,stats in health.items():
        if not stats['ok'] or stats.get('initial_error'):
            failure=daily['failures'].setdefault(key,{'count':0,'first_failed_at':now.isoformat()})
            failure.update(count=failure['count']+1,last_failed_at=now.isoformat(),error=stats.get('error') or stats.get('initial_error','未知故障'),recovered=stats['ok'])

def delivery(store,sender,key,subject,html,on_success):
    existing=store.data['deliveries'].get(key)
    if existing:
        if existing['status']=='sent':on_success(); store.save(); return True
        logging.error('Delivery awaiting manual verification: %s',key); return False
    # Durable reservation BEFORE SMTP; a lost acknowledgement must not trigger duplicates.
    store.data['deliveries'][key]={'status':'sending','subject':subject}
    store.save()
    try:sender.send(subject,html,key)
    except Exception as exc:
        store.data['deliveries'][key]['status']='uncertain'
        store.data['deliveries'][key]['error_type']=type(exc).__name__
        store.save(); logging.error('Email delivery failed or uncertain: %s',type(exc).__name__); return False
    store.data['deliveries'][key]['status']='sent'; on_success(); store.save(); return True

def run(settings,sites,clock,client,store,sender,report_dir):
    clock.guard(); now=clock.now(); health={}; detail_cache={}; discovered=0
    if settings['monitoring']['initial_scan_mode']!='baseline':raise ValueError('initial_scan_mode must be baseline')
    policy=initialize_policy(store,sites,now)
    titles={title_identity(x['university'],x['title']):k for k,x in store.data['notices'].items()}
    queue=deque((site,False) for site in sites)
    while queue:
        site,recovery=queue.popleft()
        if not site['enabled']:continue
        clock.guard()
        previous=health.get(site['id'],{}) if recovery else {}
        if recovery:
            # One late recovery pass for connection failures only; never replay successful sources.
            time.sleep(settings['crawler'].get('recovery_delay_seconds',10));clock.guard()
        crawler=CUSTOM.get(site['crawler_type'],GenericCrawler)(site,client)
        baseline=site['id'] not in policy['baseline_sources']
        stats={'ok':False,'fetched':0,'matched':0,'known_skipped':0,'outside_window':0,'details_requested':0,
               'baseline':baseline,'warnings':[],'checked_at':now.isoformat(),'latest':None}
        if recovery:
            stats['initial_error']=previous['error'];stats['recovery_attempted']=True
        try:
            rows=crawler.crawl()[:site.get('max_notices',settings['crawler']['max_notices_per_source'])]; stats['fetched']=len(rows)
            for row in rows:
                clock.guard(); row['url']=canonical(row['url'])
                old=store.data['notices'].get(notice_key(row['url']))
                identity=title_identity(site['university'],row['title'])
                known=old if old and title_identity(old['university'],old['title'])==identity else store.data['notices'].get(titles.get(identity))
                if known:
                    known['last_seen_time']=now.isoformat();known.setdefault('publish_time',None)
                    if not known.get('publish_time') and row.get('publish_time'):
                        known['publish_time']=row['publish_time'];known['publish_date']=row['publish_date']
                    elif not known.get('publish_date') and row.get('publish_date'):known['publish_date']=row['publish_date']
                    if known['url']!=row['url'] and row['url'] not in known.setdefault('aliases',[]):known['aliases'].append(row['url'])
                    stats['known_skipped']+=1
                    if known.get('matched'):
                        stats['matched']+=1
                        if not stats['latest'] or (known.get('publish_date') or '')>(stats['latest'].get('publish_date') or ''):
                            stats['latest']={k:known.get(k) for k in ('title','url','publish_date','publish_time')}
                    continue
                row.setdefault('publish_time',None);row.setdefault('publish_date',None)
                allowed,reason=publication_window(row,now,settings,baseline)
                empty_info={'matched':False,'relevance_score':0,'priority':1,'category':'未分析','is_direct_phd':False}
                candidate=classify(row['title'],'',site,settings,row['publish_date'],now) if allowed or reason=='unknown_publication' else empty_info
                detail={'text':'','notes':[],'publish_date':None,'publish_time':None}
                inspect=candidate['matched'] and (allowed or reason=='unknown_publication')
                if baseline:inspect=inspect and baseline_relevant(row['title'],'',candidate,settings)
                if inspect:
                    try:
                        if row['url'] not in detail_cache:
                            stats['details_requested']+=1
                            detail_cache[row['url']]=crawler.detail(row)
                        detail={**detail_cache[row['url']],'notes':list(detail_cache[row['url']]['notes'])}
                    except PeriodEnded:raise
                    except Exception as exc:
                        detail['notes']=['详情页读取失败：'+type(exc).__name__]
                        stats['warnings'].append(row['url']+' 详情页读取失败 '+type(exc).__name__)
                # Prefer precise publication metadata; a date-only detail must not erase list precision.
                if detail.get('publish_time'):
                    row['publish_time']=detail['publish_time'];row['publish_date']=detail['publish_date']
                elif detail.get('publish_date') and not row['publish_time']:row['publish_date']=detail['publish_date']
                allowed,reason=publication_window(row,now,settings,baseline)
                if not allowed:stats['outside_window']+=1
                if not row['publish_date']:detail['notes'].append('发布时间无法确认，列入日报待核实；不发送普通新通知')
                info=classify(row['title'],detail['text'],site,settings,row['publish_date'],now) if inspect else candidate
                eligible=allowed and info['matched'] and (not baseline or baseline_relevant(row['title'],detail['text'],info,settings))
                item={**row,**info,**{k:site[k] for k in ('university','college','source_level')},'notes':detail['notes'],'content_hash':digest(detail['text']) if detail['text'] else None,
                      'new_notification_eligible':eligible,'potential_new_notice':allowed and not row['publish_time'] and not baseline,
                      'publication_window_reason':reason,'baseline_suppressed':baseline and not eligible,
                      'needs_manual_review':info['matched'] and reason=='unknown_publication',
                      'analysis_status':'analyzed' if inspect else 'baseline' if baseline else 'outside_window' if not allowed else 'irrelevant'}
                if old and old.get('source_level')=='college' and item['source_level']=='university':
                    for k in ('source_level','college','priority','relevance_score'):item[k]=old[k]
                if old and not inspect and old.get('matched'):
                    # A renamed historical row must not cancel an already-saved deadline reminder.
                    for k in ('matched','priority','relevance_score','category','is_direct_phd'):item[k]=old[k]
                dates=extract(detail['text'],row['publish_date'],settings['monitoring']['timezone'])
                if not detail['text'] and old:
                    for k in ('registration_start','registration_deadline','material_deadline','interview_date','deadline_evidence'):dates[k]=old.get(k)
                if detail['notes']:dates['deadline_parse_status']='uncertain'
                item.update(dates)
                if item['matched']:
                    stats['matched']+=1
                    if not stats['latest'] or (item['publish_date'] or '')>(stats['latest'].get('publish_date') or ''):stats['latest']={k:item[k] for k in ('title','url','publish_date')}
                key,changed=store.upsert(item,now)
                titles[identity]=key
                if changed and eligible:discovered+=1
            stats['ok']=True
            if baseline:policy['baseline_sources'].append(site['id'])
            missing=sum(not row.get('publish_date') for row in rows)
            if missing:stats['warnings'].append(f'{missing}条缺少可确认的发布时间')
        except PeriodEnded:store.save(); raise
        except Exception as exc:
            # Do not print arbitrary remote response bodies or credentials.
            stats['error']=type(exc).__name__+': '+str(exc)[:350]
            logging.warning('%s: %s',site['id'],stats['error'])
            if (not recovery and settings['crawler'].get('recover_connection_failures',True)
                    and isinstance(exc,(requests.ConnectionError,requests.Timeout))
                    and not isinstance(exc,requests.exceptions.SSLError)):
                queue.append((site,True))
        if recovery and stats['ok']:
            stats['recovered']=True
            stats['warnings'].append('本轮首次连接失败，延后补抓已恢复；故障保留在当天记录')
            logging.info('%s recovered after temporary connection failure',site['id'])
        health[site['id']]=stats
        logging.info('%s fetched=%s matched=%s ok=%s',site['id'],stats['fetched'],stats['matched'],stats['ok'])
    store.data['health']=health;record_daily_health(store,health,now); store.save(); clock.guard()
    notices=store.data['notices']; pending=[]
    # Include previous unsent records even if a list temporarily loses them.
    for key,x in notices.items():
        if not x.get('matched') or not x.get('new_notification_eligible'):continue
        event=f'new:{key}:{x["revision"]}'
        if event not in store.data['deliveries']:pending.append((key,event))
    mail_ok=True
    if pending:
        items=[notices[k] for k,_ in pending]; items.sort(key=lambda x:(-x['priority'],x.get('publish_date') or ''))
        top=items[0]; label,hours=urgency(top,now)
        timed=[urgency(x,now)[1] for x in items]; active=[h for h in timed if h is not None and h>0]
        if active:
            top=min((x for x in items if urgency(x,now)[1] is not None and urgency(x,now)[1]>0),key=lambda x:urgency(x,now)[1])
        subject=(f'【非常紧急】【2027推免监控】{top["university"]}{top["college"]}距截止不足24小时' if active and min(active)<24 else f'【紧急】【2027推免监控】{top["university"]}{top["college"]}报名即将截止' if active and min(active)<72 else f'【重要】【2027推免监控】{top["university"]}{top["college"]}发现新通知' if top['priority']>=4 else f'【2027推免监控】发现 {len(items)} 条新通知')
        batch=digest('|'.join(sorted(e for _,e in pending)))
        # Reserve per-event keys in the same checkpoint so changed batch composition cannot resend.
        for _,event in pending:store.data['deliveries'][event]={'status':'sending','batch':batch}
        def mark():
            for key,event in pending:
                store.data['deliveries'][event]['status']='sent'; notices[key]['notified']=True
                h=urgency(notices[key],now)[1]
                if h is not None and h>0:
                    for threshold in (72,24,6):
                        if h<=threshold:notices[key][f'reminded_{threshold}h']=True
        mail_ok=delivery(store,sender,batch,subject,render_notices(items,now),mark)
    reminders=[]
    for key,x in notices.items():
        if not x.get('matched') or not x.get('notified') or x['priority']<4:continue
        h=urgency(x,now)[1]
        if h is None or h<=0:continue
        eligible=[v for v in (72,24,6) if h<=v and not x.get(f'reminded_{v}h')]
        if not eligible:continue
        threshold=min(eligible)
        event=digest(f'remind:{key}:{effective_deadline(x)}:{threshold}')
        if event in store.data['deliveries']:continue
        reminders.append((key,event,threshold))
    if reminders:
        items=[notices[k] for k,_,_ in reminders]; batch=digest('|'.join(sorted(v for _,v,_ in reminders)))
        for _,event,_ in reminders:store.data['deliveries'][event]={'status':'sending','batch':batch}
        def mark_reminders():
            for key,event,threshold in reminders:
                store.data['deliveries'][event]['status']='sent'
                for t in (72,24,6):
                    if t>=threshold:notices[key][f'reminded_{t}h']=True
        prefix='【非常紧急】' if min(t for _,_,t in reminders)<=24 else '【紧急】'
        mail_ok=delivery(store,sender,batch,prefix+'【2027推免监控】报名/材料即将截止',render_notices(items,now),mark_reminders) and mail_ok
    day=now.date().isoformat()
    if now.hour>=settings['monitoring']['daily_report_hour'] and day not in store.data['daily_reports']:
        def mark_daily():store.data['daily_reports'][day]=True
        mail_ok=delivery(store,sender,'daily-'+day,'【2027推免监控日报】'+day,render_health(health,sites,store.data,now,settings),mark_daily) and mail_ok
    unresolved=sum(v['status'] in ('sending','uncertain') for v in store.data['deliveries'].values())
    report={'checked_at':now.isoformat(),'lookback_minutes':settings['monitoring']['lookback_minutes'],
            'details_requested':sum(s['details_requested'] for s in health.values()),
            'known_skipped':sum(s['known_skipped'] for s in health.values()),
            'new_or_updated':discovered,'pending_new_events':len(pending),'http_requests':client.requests_count,'email_ok':mail_ok,'unresolved_deliveries':unresolved,
            'recovered_sources':[key for key,value in health.items() if value.get('recovered')],
            'failed_sources':[key for key,value in health.items() if not value['ok']],'health':health}
    out=Path(report_dir);out.mkdir(parents=True,exist_ok=True)
    (out/'latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'health.html').write_text(render_health(health,sites,store.data,now,settings),encoding='utf-8')
    store.save(); print(json.dumps({k:v for k,v in report.items() if k!='health'},ensure_ascii=False))
    return 0 if all(x['ok'] for x in health.values()) and mail_ok and not unresolved else 2
