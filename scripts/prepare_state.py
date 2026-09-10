"""Git branch is the authoritative state. Network errors must NEVER create empty state."""
import os, subprocess
from pathlib import Path
def git(*args,cwd=None):
    r=subprocess.run(['git',*args],cwd=cwd,capture_output=True,text=True)
    if r.returncode:raise RuntimeError('Git operation failed: '+args[0])
    return r.stdout.strip()
remote=git('remote','get-url','origin')
# actions/checkout stores a masked authorization extraheader; copy config without displaying it.
header=git('config','--get','http.https://github.com/.extraheader')
if not header:raise RuntimeError('GitHub checkout authentication not configured')
branches=git('ls-remote','--heads','origin','monitor-state')
state=Path('state')
if state.exists():raise RuntimeError('Unexpected state directory; refusing overwrite')
state.mkdir()
git('init',cwd=state); git('remote','add','origin',remote,cwd=state)
git('config','http.https://github.com/.extraheader',header,cwd=state)
git('config','user.name','github-actions[bot]',cwd=state)
git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com',cwd=state)
if branches:
    git('fetch','--depth=1','origin','monitor-state',cwd=state)
    git('checkout','-B','monitor-state','FETCH_HEAD',cwd=state)
    if not (state/'state.json').exists():raise RuntimeError('State branch exists but state.json missing')
else:
    git('checkout','--orphan','monitor-state',cwd=state)
    (state/'state.json').write_text('{"version":1,"notices":{},"deliveries":{},"daily_reports":{},"health":{}}',encoding='utf-8')
    git('add','state.json',cwd=state);git('commit','-m','Initialize durable monitor state',cwd=state)
    git('push','origin','HEAD:monitor-state',cwd=state)
