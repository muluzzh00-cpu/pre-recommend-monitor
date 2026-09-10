import re
from bs4 import NavigableString
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from bs4 import BeautifulSoup
from .base import BaseCrawler, CrawlError
from parser.publication import publication

DATE = re.compile(r'(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})日?')
def find_date(text):
    from datetime import date
    m=DATE.search(text or '')
    if m:
        try:return date(*map(int,m.groups())).isoformat()
        except ValueError:pass
    return None

def canonical(url):
    p=urlsplit(url)
    params=dict(parse_qsl(p.query))
    if p.path.endswith('/content.jsp') and params.get('wbtreeid','').isdigit() and params.get('wbnewsid','').isdigit():
        return urlunsplit((p.scheme,p.netloc.lower(),'/info/'+params['wbtreeid']+'/'+params['wbnewsid']+'.htm','',''))
    q=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in ('from','spm')]
    return urlunsplit((p.scheme,p.netloc.lower(),p.path or '/',urlencode(sorted(q)),''))

class GenericCrawler(BaseCrawler):
    def parse(self, html, url):
        soup=BeautifulSoup(html,'html.parser')
        anchors=soup.select(self.site['link_selector'])
        rows=[]; seen=set(); self.warnings=[]
        for a in anchors:
            href=a.get('href',''); full=canonical(urljoin(url,href))
            if not self.client.allowed_url(full):continue
            # Keep only this university; list navigation must never become a notice.
            host=urlsplit(full).hostname or ''; base=self.site['university_domain']
            if host!=base and not host.endswith('.'+base):continue
            if not re.search(self.site['article_url_pattern'],full):continue
            title_node=a.select_one(self.site['title_selector']) if self.site['title_selector'] != 'self' else a
            title=(a.get('title') or (title_node.get_text(' ',strip=True) if title_node else '')).strip()
            title=re.sub(r'^\s*20\d{2}[-./]\d{1,2}[-./]\d{1,2}\s*','',title)
            if len(title)<6 or full in seen:continue
            seen.add(full)
            row=a.find_parent(self.site.get('row_tag','li')) or a.parent
            dn=row.select_one(self.site['date_selector']) if self.site['date_selector'] else None
            dn=row.select_one('time[datetime]') or dn
            pub=publication((dn.get('datetime') or dn.get('content') or dn.get_text(' ',strip=True)) if dn else '')
            if not pub['publish_date']:pub=publication(row.get_text(' ',strip=True))
            rows.append({'title':title,'url':full,**pub})
            if len(rows)>=self.site.get('max_notices',self.client.cfg.get('max_notices_per_source',40)):break
        if not rows:raise CrawlError('No article links: selector invalid, structure changed, or page blocked')
        return rows,soup
    def crawl(self):
        url=self.site['list_url']; rows=[]; visited=set()
        limit=self.site.get('max_notices',self.client.cfg.get('max_notices_per_source',40))
        for _ in range(self.client.cfg['max_list_pages']):
            if url in visited:break
            visited.add(url)
            parsed,soup=self.parse(self.client.get(url).text,url); rows.extend(parsed)
            rows=list({canonical(r['url']):r for r in rows}.values())
            if len(rows)>=limit:break
            next_link=next((a for a in soup.select('a[href]') if re.search(r'下一页|下页|Next',a.get_text(' ',strip=True),re.I)),None)
            if not next_link:break
            next_url=urljoin(url,next_link['href'])
            if urlsplit(next_url).netloc != urlsplit(url).netloc:break
            url=next_url
        return list({canonical(r['url']):r for r in rows}.values())[:limit]
    def detail(self, item):
        r=self.client.get(item['url'])
        if 'pdf' in r.headers.get('Content-Type','').lower() or item['url'].lower().endswith('.pdf'):
            return {'text':'','publish_date':None,'publish_time':None,'notes':['PDF原文，需人工查看截止日期'],'attachments':[item['url']]}
        soup=BeautifulSoup(r.text,'html.parser')
        meta=soup.select_one('meta[name="PubDate"],meta[name="publishdate"],meta[name="DC.date.issued"],meta[property="article:published_time"]')
        published=publication(meta.get('content','')) if meta else publication('')
        pub=published['publish_date']
        header_date=soup.select_one('.entry-date, .arti_update, .article-date, time[datetime]')
        if header_date:
            header_pub=publication(header_date.get('datetime') or header_date.get_text(' ',strip=True))
            if header_pub['publish_time'] or not pub:published=header_pub;pub=published['publish_date']
        content=soup.select_one(self.site.get('content_selector','.wp_articlecontent, .v_news_content, #vsb_content, article'))
        notes=[]
        if content is None:
            notes.append('正文选择器未命中，使用正文候选区域；日期需人工核实')
            content=soup.select_one('main') or soup.body or soup
        for node in content.select('script,style,nav,header,footer'):node.decompose()
        # Preserve paragraph boundaries, not every inline span/strong boundary.
        for node in list(content.find_all(string=True)):
            if not node.strip():node.extract()
        for node in content.select('p,li,tr,br,h1,h2,h3'):node.insert_after(NavigableString('\n'))
        text=content.get_text(' ',strip=False)
        text=re.sub(r'[^\S\n]+',' ',text).strip()
        if not published['publish_time']:
            match=re.search(r'(?:发布时间|发布日期|发布于)\s*[:：]?\s*(20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?(?:[T\s]+\d{1,2}[:：]\d{2}(?:[:：]\d{2})?)?)',soup.get_text(' ',strip=True))
            if match:
                labeled=publication(match.group(1))
                if labeled['publish_time'] or not pub:published=labeled;pub=published['publish_date']
        if not pub:
            m=re.search(r'/(20\d{2})/(\d{2})(\d{2})/',item['url'])
            if m:pub=find_date('-'.join(m.groups()))
            m=re.search(r'/(20\d{2})(\d{2})(\d{2})/',item['url'])
            if m and not pub:pub=find_date('-'.join(m.groups()))
        if not pub:
            heading=soup.find(['h1','h2','h3'])
            if heading:
                # Only the publication header vicinity, never dates in the article body.
                next_text=[]
                for sibling in heading.next_siblings:
                    if sibling==content or len(''.join(next_text))>220:break
                    next_text.append(sibling.get_text(' ',strip=True) if hasattr(sibling,'get_text') else str(sibling))
                published=publication(' '.join(next_text)[:220]);pub=published['publish_date']
        attachments=[urljoin(item['url'],a['href']) for a in content.select('a[href]') if re.search(r'\.pdf|\.docx?|DownloadAttach',a['href'],re.I)]
        if attachments:notes.append('原文含附件；附件/扫描件中的日期未自动确认，请打开原文核查')
        if len(text)<60:notes.append('正文过短或图片通知，需人工查看原文')
        return {'text':text,'publish_date':pub,'publish_time':published['publish_time'],'notes':notes,'attachments':attachments}
