import json, sys
from pathlib import Path
p=Path('logs/latest.json')
if not p.exists():
    print('没有生成抓取报告。请检查前面失败步骤（邮箱 Secrets、依赖、时间门禁或状态恢复）。')
else:
    r=json.loads(p.read_text(encoding='utf-8'))
    print('检查时间：'+r['checked_at'])
    print('滚动窗口：'+str(r.get('lookback_minutes',75))+' 分钟；跳过已知通知：'+str(r.get('known_skipped',0))+'；详情页请求：'+str(r.get('details_requested',0)))
    print('\n| 页面 | 状态 | 抓取 | 匹配 | 错误 |\n|---|---|---:|---:|---|')
    for key,v in r['health'].items():print('|'+key+'|'+('✅' if v['ok'] else '❌')+'|'+str(v['fetched'])+'|'+str(v['matched'])+'|'+v.get('error','').replace('|','/')+'|')
    print('\n新发现/重要更新：'+str(r['new_or_updated'])+'；待核实邮件状态：'+str(r['unresolved_deliveries']))
    failures=r.get('failed_sources',[k for k,v in r['health'].items() if not v['ok']])
    if failures:
        print('::error title=官网抓取部分失败::失败来源：'+', '.join(failures)+'。其他来源及邮件仍独立处理；详情见报告。',file=sys.stderr)
    if r.get('recovered_sources'):
        print('::warning title=临时连接故障已恢复::延后补抓成功：'+', '.join(r['recovered_sources']),file=sys.stderr)
    if not r['email_ok'] or r['unresolved_deliveries']:
        print('::error title=邮件发送待核实::请核对邮件与投递状态；不要清空数据库重发。',file=sys.stderr)
