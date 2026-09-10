from ..generic import GenericCrawler, find_date, canonical
from ..base import CrawlError
import re, json
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from parser.publication import publication

class NjuCrawler(GenericCrawler):
    """Read the official CMS's embedded dataList JSON, without executing page JavaScript."""
    def parse(self, html, url):
        match=re.search(r'\bvar\s+dataList\s*=\s*',html)
        if match:
            pages,_=json.JSONDecoder().raw_decode(html[match.end():])
            rows=[]
            for page in pages[:self.client.cfg['max_list_pages']]:
                for x in page.get('infolist',[]):
                    full=canonical(urljoin(url,x.get('url','')))
                    host=urlsplit(full).hostname or '';base=self.site['university_domain']
                    if not self.client.allowed_url(full) or (host!=base and not host.endswith('.'+base)):continue
                    title=BeautifulSoup(x.get('title',''),'html.parser').get_text(' ',strip=True)
                    if len(title)<6:continue
                    rows.append({'title':title,'url':full,**publication(x.get('daytime',''))})
                    if len(rows)>=self.site.get('max_notices',self.client.cfg.get('max_notices_per_source',40)):
                        return rows,BeautifulSoup(html,'html.parser')
            if rows:return rows,BeautifulSoup(html,'html.parser')
            raise CrawlError('NJU embedded dataList has no official notice links')
        rows,soup=super().parse(html,url)
        for row in rows:
            if not row['publish_date']:
                for a in soup.select('a[href]'):
                    if a.get_text(' ',strip=True).endswith(row['title']):
                        parent=a.parent
                        for _ in range(3):
                            if parent is None:break
                            value=publication(parent.get_text(' ',strip=True))
                            if value['publish_date']:row.update(value); break
                            parent=parent.parent
                        break
        return rows,soup
