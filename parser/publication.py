"""Publication precision and rolling windows. Date-only values never become midnight."""
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

DATE = re.compile(r'(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})日?')
TIME = re.compile(r'^[T\s]+(\d{1,2})\s*[:：]\s*(\d{2})(?:\s*[:：]\s*(\d{2})(?:\.(\d+))?)?\s*(Z|[+-]\d{2}:?\d{2})?')

def publication(text, timezone='Asia/Shanghai'):
    result={'publish_date':None,'publish_time':None}
    match=DATE.search(str(text or ''))
    if not match:return result
    try:day=date(*map(int,match.groups()))
    except ValueError:return result
    result['publish_date']=day.isoformat()
    clock=TIME.match(str(text)[match.end():])
    if clock:
        hour,minute,second,fraction,offset=clock.groups()
        try:
            value=datetime.combine(day,datetime.min.time()).replace(hour=int(hour),minute=int(minute),second=int(second or 0),microsecond=int((fraction or '').ljust(6,'0')[:6]))
            value=datetime.fromisoformat(value.isoformat()+offset.replace('Z','+00:00')) if offset else value.replace(tzinfo=ZoneInfo(timezone))
            value=value.astimezone(ZoneInfo(timezone))
            result.update(publish_date=value.date().isoformat(),publish_time=value.isoformat())
        except ValueError:pass
    return result

def publication_window(row, now, settings, baseline=False):
    now=now.astimezone(ZoneInfo(settings['monitoring']['timezone']))
    value=row.get('publish_time')
    if value:
        try:
            stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
            if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=now.tzinfo)
            stamp=stamp.astimezone(now.tzinfo)
            if stamp>now:return False,'future_publication'
            if not baseline:
                return (stamp>=now-timedelta(minutes=settings['monitoring']['lookback_minutes']),'precise_window')
        except ValueError:return False,'invalid_publication_time'
    try:day=date.fromisoformat(row.get('publish_date') or '')
    except ValueError:return False,'unknown_publication'
    if baseline:
        cutoff=date.fromisoformat(settings['monitoring']['baseline_notify_since'])
        return cutoff<=day<=now.date(),'baseline_recent'
    return day==now.date(),'today_first_seen'

def baseline_relevant(title, text, info, settings):
    both=title+'\n'+text
    return info['matched'] and info['priority']>=4 and str(settings['monitoring']['target_year']) in both and any(k in both for k in settings['keywords']['strong'])
