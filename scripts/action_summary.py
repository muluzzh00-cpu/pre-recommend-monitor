import json
from pathlib import Path
p=Path('logs/latest.json')
if not p.exists():
    print('没有生成抓取报告。请检查前面失败步骤（邮箱 Secrets、依赖、时间门禁或状态恢复）。')
else:
    r=json.loads(p.read_text(encoding='utf-8'))
    print('检查时间：'+r['checked_at'])
    print('\n| 页面 | 状态 | 抓取 | 匹配 | 错误 |\n|---|---|---:|---:|---|')
    for key,v in r['health'].items():print('|'+key+'|'+('✅' if v['ok'] else '❌')+'|'+str(v['fetched'])+'|'+str(v['matched'])+'|'+v.get('error','').replace('|','/')+'|')
    print('\n新发现/重要更新：'+str(r['new_or_updated'])+'；待核实邮件状态：'+str(r['unresolved_deliveries']))
