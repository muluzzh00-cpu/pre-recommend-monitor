"""Stdlib-only gate before pip/git/SMTP. Parse the small quoted YAML date settings."""
from pathlib import Path
import re
from datetime import datetime
from zoneinfo import ZoneInfo
text=Path('config/settings.yaml').read_text(encoding='utf-8')
def value(key):
    match=re.search(r'^\s*'+key+r':\s*([^#\r\n]+)',text,re.M)
    if not match:raise ValueError('Missing setting '+key)
    return match[1].strip().strip('\"\'')
tz=ZoneInfo(value('timezone')); now=datetime.now(tz)
start=datetime.fromisoformat(value('start_date')).replace(tzinfo=tz)
end=datetime.fromisoformat(value('end_date')).replace(tzinfo=tz)
print('active='+str(start<=now<=end).lower())
if now>end:
    import sys
    print('Monitoring period has ended.',file=sys.stderr)
