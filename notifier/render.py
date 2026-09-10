from html import escape as e
from parser.deadline import urgency

def render_notices(items,now):
    body=['<html><meta charset="utf-8"><body style="font:15px Arial;line-height:1.7;color:#173047"><h1>2027 推免 / 直博监控</h1><p>时间均为北京时间。日期无法确认时请核对官方原文。</p>']
    for x in items:
        label,hours=urgency(x,now)
        suggestion='🔴 立即查看' if hours is not None and 0<hours<24 else '🟠 尽快处理' if hours is not None and 0<hours<72 else '🟡 重点关注' if x['priority']>=4 else '🟢 一般关注'
        body.append('<section style="border:1px solid #ccd9e2;padding:20px;margin:18px 0"><h2>'+e(x['title'])+'</h2><table>')
        fields=[('学校',x['university']),('学院',x['college']),('来源','学院官网' if x['source_level']=='college' else '学校官网'),('发布时间',x.get('publish_time') or x.get('publish_date')),('发现时间',x['first_seen_time']),('通知类型',x['category']),('相关度','★'*x['priority']+f" ({x['relevance_score']}分)"),('是否涉及直博','是' if x['is_direct_phd'] else '未识别到'),('报名开始',x.get('registration_start')),('报名截止',x.get('registration_deadline')),('距离截止',label+(f' / {hours:.1f}小时' if hours is not None else '')),('材料截止',x.get('material_deadline')),('复试/面试',x.get('interview_date')),('解析状态',x.get('deadline_parse_status')),('建议',suggestion)]
        body.extend('<tr><th style="text-align:left;padding-right:20px">'+e(k)+'</th><td>'+e(str(v or '未知 / 待人工核实'))+'</td></tr>' for k,v in fields)
        body.append('</table><p><a href="'+e(x['url'],quote=True)+'">官方原文：'+e(x['url'])+'</a></p>')
        body.extend('<p>'+e(n)+'</p>' for n in x.get('notes',[]))
        body.extend('<blockquote>'+e(n)+'</blockquote>' for n in x.get('deadline_evidence',[]))
        body.append('</section>')
    return ''.join(body)+'</body></html>'

def render_health(health,sites,state,now,settings):
    from datetime import datetime
    colleges=list(dict.fromkeys(s['university']+s['college'] for s in sites))
    body=['<html><meta charset="utf-8"><h1>2027推免监控日报 '+now.date().isoformat()+'</h1>']; success=0
    for name in colleges:
        pages=[health.get(s['id'],{}) for s in sites if s['university']+s['college']==name and s['enabled']]
        core=[health.get(s['id'],{}) for s in sites if s['university']+s['college']==name and s['source_level']=='college' and s['enabled']]
        good=sum(p.get('ok',False) for p in pages)
        if any(p.get('ok') for p in core):success+=1
        icon='✅' if good==len(pages) and good and not any(p.get('warnings') for p in pages) else '⚠️' if good else '❌'
        body.append('<p>'+e(name)+'：'+icon+'</p>')
    from zoneinfo import ZoneInfo
    tz=ZoneInfo(settings['monitoring']['timezone']);now=now.astimezone(tz)
    notices=list(state['notices'].values())
    def found_today(x):
        stamp=datetime.fromisoformat(x['first_seen_time'])
        return (stamp.replace(tzinfo=tz) if stamp.tzinfo is None else stamp.astimezone(tz)).date()==now.date()
    today=[x for x in notices if x.get('matched') and not x.get('baseline_suppressed') and found_today(x)]
    daily=state.get('daily_stats',{}).get(now.date().isoformat(),{})
    failures=daily.get('failures',{})
    ending=datetime.fromisoformat(settings['monitoring']['end_date']).date()
    pending=[k for k,v in state['deliveries'].items() if v['status'] in ('sending','uncertain')]
    for label,value in [('成功检查学院',f'{success} / 7'),('监控页面',len(health)),('今日运行次数',daily.get('runs',0)),('今日新通知',len(today)),('今日高优先级通知',sum(x['priority']>=4 for x in today)),('即将截止',sum(0<(urgency(x,now)[1] or -1)<72 for x in notices if x.get('matched'))),('本轮失败页面',sum(not p.get('ok') for p in health.values())),('今日曾失败页面',len(failures)),('今日失败次数',sum(f['count'] for f in failures.values())),('距离结束天数',(ending-now.date()).days),('待核实邮件投递',len(pending))]:body.append('<p>'+label+'：'+str(value)+'</p>')
    if failures:
        body.append('<h2>今日失败记录（恢复后仍保留）</h2>')
        by_id={s['id']:s for s in sites}
        for key,failure in failures.items():
            source=by_id.get(key,{});url=source.get('list_url','')
            body.append('<p><a href="'+e(url,quote=True)+'">'+e(source.get('university',key)+' '+source.get('page_name',''))+'</a>：'+e(str(failure['count']))+' 次；最后失败 '+e(failure['last_failed_at'])+'；'+e(failure.get('error',''))+'</p>')
    review=[x for x in notices if x.get('needs_manual_review') and found_today(x)]
    if review:
        body.append('<h2>今日发布时间待核实（未发送普通新通知）</h2>')
        for x in review:body.append('<p><a href="'+e(x['url'],quote=True)+'">'+e(x['title'])+'</a></p>')
    for s in sites:
        p=health.get(s['id'],{})
        if not p.get('ok') or p.get('warnings'):
            body.append('<p>'+e(s['university']+s['college'])+' <a href="'+e(s['list_url'],quote=True)+'">'+e(s['list_url'])+'</a> '+e(p.get('error','；'.join(p.get('warnings',[]))))+'</p>')
    if pending:body.append('<p>存在 SMTP 结果不确定的邮件，已暂停自动重发以免重复，请检查收件箱和状态分支 deliveries。</p>')
    return ''.join(body)+'</html>'
