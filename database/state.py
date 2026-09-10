"""Atomic JSON state, optionally checkpointed to an independent Git branch before SMTP."""
import hashlib, json, os, subprocess, re
from urllib.parse import urlsplit
from pathlib import Path

def digest(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()
def notice_key(url):
    p=urlsplit(url)
    m=re.search(r'/c\d+a(\d+)/page\.(?:htm|psp)',p.path)
    # WebPlus can expose one article through several category URLs.
    return digest(p.netloc.lower()+':webplus:'+m[1]) if m else digest(url)
class StateStore:
    def __init__(self, directory, git_sync=False, clock=None):
        self.directory=Path(directory); self.directory.mkdir(parents=True,exist_ok=True)
        self.path=self.directory/'state.json'; self.git_sync=git_sync; self.clock=clock
        if self.path.exists():
            self.data=json.loads(self.path.read_text(encoding='utf-8'))
            if self.data.get('version') != 1:raise ValueError('Unsupported or corrupt state; refusing reset')
        else:self.data={'version':1,'notices':{},'deliveries':{},'daily_reports':{},'health':{}}
        if git_sync and not (self.directory/'.git').exists():raise RuntimeError('State Git checkout missing')
    def save(self):
        temp=self.path.with_suffix('.tmp')
        with temp.open('w',encoding='utf-8') as f:
            json.dump(self.data,f,ensure_ascii=False,indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(temp,self.path)
        if self.git_sync:
            if self.clock:self.clock.guard()
            self.git('add','state.json')
            changed=self.git('diff','--cached','--name-only')
            if changed.strip():
                self.git('commit','-m','Persist monitor state')
            # Retry an earlier unpushed commit too. A failed push must prevent SMTP.
            if self.clock:self.clock.guard()
            self.git('push','origin','HEAD:monitor-state')
    def git(self,*args):
        r=subprocess.run(['git','-C',str(self.directory),*args],capture_output=True,text=True)
        if r.returncode:raise RuntimeError('State persistence Git operation failed: '+args[0])
        return r.stdout
    def upsert(self,item,now):
        notices=self.data['notices']; key=notice_key(item['url']); old=notices.get(key)
        item['first_seen_time']=old['first_seen_time'] if old else now.isoformat()
        item['last_seen_time']=now.isoformat()
        # Identical title AND identical nonempty detail content, same school: alias/repost.
        if not old and item.get('content_hash'):
            alias=next(((k,v) for k,v in notices.items() if v['university']==item['university'] and v['title']==item['title'] and v.get('content_hash')==item['content_hash']),None)
            if alias:
                alias[1].setdefault('aliases',[])
                if item['url'] not in alias[1]['aliases']:alias[1]['aliases'].append(item['url'])
                alias[1]['last_seen_time']=now.isoformat()
                return alias[0],False
        signature=digest(json.dumps([item['title'].replace(' ','').replace('\n',''),item.get('registration_deadline'),item.get('material_deadline'),item.get('interview_date')],ensure_ascii=False))
        if old:
            for k in ('reminded_72h','reminded_24h','reminded_6h','notified','aliases'):item[k]=old.get(k,[] if k=='aliases' else False)
            if (old.get('registration_deadline'),old.get('material_deadline')) != (item.get('registration_deadline'),item.get('material_deadline')):
                for k in ('reminded_72h','reminded_24h','reminded_6h'):item[k]=False
            item['revision']=old.get('revision',1)+(old.get('signature') != signature)
        else:
            item.update({'revision':1,'notified':False,'reminded_72h':False,'reminded_24h':False,'reminded_6h':False})
        item['signature']=signature; notices[key]=item
        return key,not old or old.get('signature')!=signature
