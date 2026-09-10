from abc import ABC, abstractmethod
from urllib.parse import urlsplit, urljoin
from urllib.robotparser import RobotFileParser
import time
import requests

class CrawlError(Exception):
    pass

class HttpClient:
    def __init__(self, settings, clock):
        self.cfg = settings['crawler']; self.clock = clock
        self.session = requests.Session()
        self.session.headers['User-Agent'] = self.cfg['user_agent']
        self.robots = {}; self.last = {}; self.requests_count = 0
    def allowed_url(self, url):
        p = urlsplit(url)
        return p.scheme in ('http','https') and (p.hostname or '').endswith('.edu.cn') and not p.username and p.port in (None,80,443)
    def _request(self, url):
        for attempt in range(self.cfg['retries'] + 1):
            self.clock.guard()
            if not self.allowed_url(url):
                raise CrawlError('Non-official URL or port rejected')
            host = urlsplit(url).netloc
            delay = self.cfg['interval_seconds'] - (time.monotonic() - self.last.get(host,0))
            if delay > 0: time.sleep(delay)
            self.clock.guard()
            self.last[host] = time.monotonic(); self.requests_count += 1
            try:
                r = self.session.get(url, timeout=self.cfg['timeout_seconds'], allow_redirects=False, stream=True)
                if r.status_code in (429,500,502,503,504) and attempt < self.cfg['retries']:
                    backoff=min(2 ** attempt,8)
                    retry_after=r.headers.get('Retry-After','')
                    if retry_after:
                        try:
                            if retry_after.isdigit():backoff=max(backoff,int(retry_after))
                            else:
                                from email.utils import parsedate_to_datetime
                                backoff=max(backoff,(parsedate_to_datetime(retry_after)-self.clock.now()).total_seconds())
                        except (ValueError,TypeError):pass
                    r.close()
                    if backoff>30:raise CrawlError('Server Retry-After exceeds this run retry budget; will retry next hour')
                    time.sleep(backoff); continue
                chunks=[]; size=0
                for chunk in r.iter_content(65536):
                    size += len(chunk)
                    if size > self.cfg['max_response_bytes']:
                        r.close(); raise CrawlError('Response exceeds size limit')
                    chunks.append(chunk)
                r._content = b''.join(chunks); r._content_consumed=True; r.close()
                r.encoding = r.apparent_encoding
                return r
            except (requests.Timeout, requests.ConnectionError):
                if attempt == self.cfg['retries']: raise
                time.sleep(min(2 ** attempt,8))
        raise CrawlError('Retry budget exhausted')
    def check_robots(self, url):
        p = urlsplit(url); origin = f'{p.scheme}://{p.netloc}'
        if origin not in self.robots:
            robot_url = origin + '/robots.txt'
            r = self._request(robot_url)
            for _ in range(3):
                if r.is_redirect:
                    robot_url = urljoin(robot_url,r.headers['Location']); r = self._request(robot_url)
                else: break
            if r.status_code == 404:
                lines = []
            elif r.status_code != 200:
                raise CrawlError(f'robots.txt unavailable: HTTP {r.status_code}; conservative stop')
            else:
                # Some official CMSs serve their home page for every missing path.
                # RobotFileParser ignores non-directive lines, per robots parsing semantics.
                lines = r.text.splitlines()
            rp = RobotFileParser(); rp.parse(lines); self.robots[origin] = rp
        rp=self.robots[origin]
        if not rp.can_fetch(self.cfg['user_agent'],url): raise CrawlError('robots.txt disallows crawling')
        delay=rp.crawl_delay(self.cfg['user_agent']) or rp.crawl_delay('*')
        if delay: self.cfg['interval_seconds']=max(self.cfg['interval_seconds'],delay)
    def get(self, url):
        for _ in range(6):
            self.clock.guard(); self.check_robots(url)
            r = self._request(url)
            if r.is_redirect:
                url = urljoin(url,r.headers['Location']); continue
            r.raise_for_status()
            if len(r.content)<80: raise CrawlError('Empty or truncated page')
            return r
        raise CrawlError('Too many redirects')

class BaseCrawler(ABC):
    def __init__(self, site, client): self.site=site; self.client=client
    @abstractmethod
    def crawl(self): pass
