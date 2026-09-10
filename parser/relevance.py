import re
from datetime import date, timedelta

def classify(title, text, site, settings, publish_date, now):
    kw=settings['keywords']; both=title+'\n'+text
    strong=any(k in both for k in kw['strong']); action=any(k in both for k in kw['action'])
    admission=any(k in both for k in kw['admission']); subject=any(k in both for k in kw['subject'])
    college=site['source_level']=='college'; year=str(settings['monitoring']['target_year'])
    score=(5 if college else 1)+(5 if strong else 0)+(4 if year in both or '接收推荐免试' in both or '直接攻读博士' in both else 0)+(3 if action else 0)+(2 if subject else 0)+(1 if admission else 0)
    relevant=strong or admission or (college and action and ('研究生' in both or year in title or '接收优秀应届本科毕业生' in both))
    if any(k in title for k in kw['exclude']):relevant=False
    years=re.findall(r'(20\d{2})\s*[年级届]',title)
    # A current publication concerning next-year admission may mention current-year procedures.
    stale=False
    if publish_date:
        try:stale=date.fromisoformat(publish_date)<now.date()-timedelta(days=settings['monitoring']['initial_lookback_days'])
        except ValueError:pass
    if year not in title and years and max(map(int,years))<int(year) and (stale or not publish_date):relevant=False
    if stale and year not in title:relevant=False
    if re.search(r'20\d{2}[—～~-]20\d{2}',title) and year not in title:relevant=False
    if not college:
        # Do not select a different named college's standalone notice from a school-level page.
        named=re.findall(r'[\u4e00-\u9fff]{2,20}(?:学院|学部|研究院)',title)
        if named and site['college'] not in title and not any(k in title for k in kw['subject']) and not any(k in title for k in ['各学院','各招生','汇总','各院']):relevant=False
    priority=5 if college and strong else 5 if score>=16 else 4 if score>=11 else 3 if score>=7 else 2 if score>=4 else 1
    return {'matched':relevant,'relevance_score':score,'priority':priority,'category':'直博' if any(k in both for k in ['直博','直接攻读博士','直接攻博']) else '推免/预推免' if strong else '博士招生' if '博士' in both else '研究生招生/疑似相关','is_direct_phd':any(k in both for k in ['直博','直接攻读博士','直接攻博'])}
