import json, logging
from pathlib import Path
from datetime import datetime
from crawlers.generic import GenericCrawler, canonical
from crawlers.custom import CUSTOM
from monitor_clock import PeriodEnded
from parser.relevance import classify
from parser.deadline import extract, urgency, effective_deadline
from database.state import digest, notice_key
from notifier.render import render_notices, render_health

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
    clock.guard(); now=clock.now(); health={}; new=[]; detail_cache={}; discovered=0
    for site in sites:
        if not site['enabled']:continue
        clock.guard()
        crawler=CUSTOM.get(site['crawler_type'],GenericCrawler)(site,client)
        stats={'ok':False,'fetched':0,'matched':0,'warnings':[],'checked_at':now.isoformat(),'latest':None}
        try:
            rows=crawler.crawl(); stats['fetched']=len(rows)
            for row in rows:
                clock.guard(); row['url']=canonical(row['url'])
                old=store.data['notices'].get(notice_key(row['url']))
                candidate=classify(row['title'],'',site,settings,row.get('publish_date'),now)
                detail={'text':'','notes':[],'publish_date':None}
                if candidate['matched']:
                    try:
                        if row['url'] not in detail_cache:detail_cache[row['url']]=crawler.detail(row)
                        detail={**detail_cache[row['url']],'notes':list(detail_cache[row['url']]['notes'])}
                    except PeriodEnded:raise
                    except Exception as exc:
                        detail['notes']=['详情页读取失败：'+type(exc).__name__]
                        stats['warnings'].append(row['url']+' 详情页读取失败 '+type(exc).__name__)
                row['publish_date']=detail.get('publish_date') or row.get('publish_date') or (old.get('publish_date') if old else None)
                if not row['publish_date']:detail['notes'].append('发布时间缺失；保留疑似通知，避免漏报')
                info=classify(row['title'],detail['text'],site,settings,row['publish_date'],now)
                item={**row,**info,**{k:site[k] for k in ('university','college','source_level')},'notes':detail['notes'],'content_hash':digest(detail['text']) if detail['text'] else None}
                if old and old.get('source_level')=='college' and item['source_level']=='university':
                    for k in ('source_level','college','priority','relevance_score'):item[k]=old[k]
                dates=extract(detail['text'],row['publish_date'],settings['monitoring']['timezone'])
                if not detail['text'] and old:
                    for k in ('registration_start','registration_deadline','material_deadline','interview_date','deadline_evidence'):dates[k]=old.get(k)
                if detail['notes']:dates['deadline_parse_status']='uncertain'
                item.update(dates)
                if item['matched']:
                    stats['matched']+=1
                    if not stats['latest'] or (item['publish_date'] or '')>(stats['latest'].get('publish_date') or ''):stats['latest']={k:item[k] for k in ('title','url','publish_date')}
                key,changed=store.upsert(item,now)
                if changed and item['matched']:discovered+=1
                if item['matched']:new.append(key)
            stats['ok']=True
            missing=sum(not row.get('publish_date') for row in rows)
            if missing:stats['warnings'].append(f'{missing}条缺少可确认的发布时间')
        except PeriodEnded:store.save(); raise
        except Exception as exc:
            # Do not print arbitrary remote response bodies or credentials.
            stats['error']=type(exc).__name__+': '+str(exc)[:350]
            logging.warning('%s: %s',site['id'],stats['error'])
        health[site['id']]=stats
        logging.info('%s fetched=%s matched=%s ok=%s',site['id'],stats['fetched'],stats['matched'],stats['ok'])
    store.data['health']=health; store.save(); clock.guard()
    notices=store.data['notices']; pending=[]
    # Include previous unsent records even if a list temporarily loses them.
    for key,x in notices.items():
        if not x.get('matched'):continue
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
    report={'checked_at':now.isoformat(),'new_or_updated':discovered,'pending_new_events':len(pending),'http_requests':client.requests_count,'email_ok':mail_ok,'unresolved_deliveries':unresolved,'health':health}
    out=Path(report_dir);out.mkdir(parents=True,exist_ok=True)
    (out/'latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'health.html').write_text(render_health(health,sites,store.data,now,settings),encoding='utf-8')
    store.save(); print(json.dumps({k:v for k,v in report.items() if k!='health'},ensure_ascii=False))
    return 0 if all(x['ok'] for x in health.values()) and mail_ok and not unresolved else 2
