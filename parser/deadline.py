"""Conservative rule extraction: missing year/clock time or multiple batches remain uncertain."""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TOKEN=re.compile(r'(?:(20\d{2})\s*[年./-]\s*)?(\d{1,2})\s*[月./-]\s*(\d{1,2})日?(?:\s*(上午|下午|晚上|中午)?\s*(\d{1,2})\s*[:：时点]\s*(\d{1,2})?(?:分)?)?')
FIELDS=['registration_start','registration_deadline','material_deadline','interview_date']
def extract(text, publish_date=None, timezone='Asia/Shanghai'):
    text='\n'.join(re.sub(r'[ \t\u3000\xa0]+','',line) for line in text.splitlines())
    result={k:None for k in FIELDS}; evidence=[]; values={k:[] for k in FIELDS}; uncertain=False
    # Only explicit publication date supplies an omitted calendar year; admission year never does.
    pub_year=int(publish_date[:4]) if publish_date else None
    for line in re.split(r'[。；;\n]',text):
        if not re.search(r'报名|申请|提交|材料|复试|面试|截止|系统.*(?:开闭|开放)',line):continue
        tokens=list(TOKEN.finditer(line))
        if not tokens:continue
        evidence.append(line.strip())
        parsed=[]
        for t in tokens:
            y,m,d,period,h,minute=t.groups(); y=int(y) if y else pub_year
            if y is None or h is None:
                parsed.append(None); uncertain=True; continue
            h=int(h); minute=int(minute or 0)
            if period in ('下午','晚上') and h<12:h+=12
            if period=='中午' and h<11:uncertain=True; parsed.append(None); continue
            try:
                base=datetime(y,int(m),int(d),tzinfo=ZoneInfo(timezone))
                if h==24 and minute==0:dt=base+timedelta(days=1)
                else:dt=base.replace(hour=h,minute=minute)
                parsed.append(dt.isoformat())
            except ValueError:parsed.append(None); uncertain=True
        material=bool(re.search(r'材料.{0,12}(提交|报送|截止)|提交.{0,8}材料',line))
        interview=bool(re.search(r'复试|面试',line)) and not re.search('报名|申请|材料',line)
        field='material_deadline' if material else 'interview_date' if interview else 'registration_deadline'
        if len(tokens)==2 and re.search(r'至|到|—|―|～|~|-',line[tokens[0].end():tokens[1].start()]):
            if not material and not interview:values['registration_start'].append(parsed[0])
            values[field].append(parsed[1])
        elif len(tokens)==1:
            if interview:values[field].append(parsed[0])
            elif re.search(r'截止|截至|之前|前|不晚于',line):values[field].append(parsed[0])
            elif re.search(r'开始|开启|开通|开放|起',line):values['registration_start'].append(parsed[0])
            else:uncertain=True
        else:uncertain=True
    for field,vals in values.items():
        unique=set(vals)
        if len(unique)==1 and None not in unique:result[field]=vals[0]
        elif vals:uncertain=True
    result['deadline_parse_status']='uncertain' if uncertain or not any(result.values()) else 'parsed'
    result['deadline_evidence']=evidence
    return result

def effective_deadline(item):
    values=[item.get(k) for k in ('registration_deadline','material_deadline') if item.get(k)]
    return min(values) if values else None

def urgency(item, now):
    deadline=effective_deadline(item)
    if not deadline:return '⚪ 截止日期未知',None
    hours=(datetime.fromisoformat(deadline)-now).total_seconds()/3600
    return ('已截止' if hours<=0 else '🔴 极其紧急' if hours<24 else '🟠 紧急' if hours<72 else '🟡 需要关注' if hours<168 else '🟢 正常'),hours
