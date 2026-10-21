"""Private, bounded checkpoint transport. No credentials enter the archive."""
import io
import json
import os
from pathlib import Path, PurePosixPath
import tarfile
import requests

BUCKET='idn-collector-state'
OBJECT='automatic/current.tar.gz'
LIMIT=48*1024*1024
UNPACK_LIMIT=1024**3

def pack(root):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w:gz') as archive:
        for path in sorted(Path(root).rglob('*')):
            if path.is_symlink(): raise ValueError('checkpoint symlink rejected')
            if path.is_file():
                rel=path.relative_to(root)
                if path.name.startswith('.env') or path.name.endswith('.lock') or path.name=='scheduler.lock': continue
                archive.add(path,arcname=str(rel),recursive=False)
    data=out.getvalue()
    if len(data)>LIMIT: raise ValueError('checkpoint exceeds 48 MiB; retain local state and review capacity')
    return data

def unpack(data,root):
    if len(data)>LIMIT: raise ValueError('checkpoint too large')
    root=Path(root);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        members=archive.getmembers()
        if len(members)>20000 or sum(x.size for x in members)>UNPACK_LIMIT: raise ValueError('checkpoint expansion too large')
        for member in members:
            path=PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not member.isfile() or any(p.startswith('.env') for p in path.parts):
                raise ValueError('unsafe checkpoint member')
        for member in members:
            target=root/member.name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            target.write_bytes(archive.extractfile(member).read());target.chmod(0o600)
    if not (root/'active-run.json').is_file(): raise ValueError('missing scheduler checkpoint')

class Storage:
    def __init__(self,url,key):
        self.url=url.rstrip('/')+'/storage/v1'
        self.headers={'apikey':key}
        if key.startswith('eyJ'): self.headers['Authorization']='Bearer '+key
    def call(self,method,path,**kwargs):
        try:
            response=requests.request(method,self.url+path,headers=self.headers,timeout=(10,90),allow_redirects=False,**kwargs)
        except requests.RequestException: raise RuntimeError('private checkpoint transport failed') from None
        if response.status_code not in (200,201): raise RuntimeError('private checkpoint HTTP '+str(response.status_code))
        return response
    def restore(self,root):
        response=self.call('GET','/object/'+BUCKET+'/'+OBJECT,stream=True,params={'v':str(__import__('time').time_ns())})
        data=bytearray()
        for part in response.iter_content(65536):
            data.extend(part)
            if len(data)>LIMIT: raise ValueError('remote checkpoint too large')
        response.close();unpack(bytes(data),root)
    def save(self,root):
        data=pack(root)
        headers={**self.headers,'Content-Type':'application/gzip','x-upsert':'true'}
        try:
            r=requests.post(self.url+'/object/'+BUCKET+'/'+OBJECT,headers=headers,data=data,timeout=(10,90),allow_redirects=False)
        except requests.RequestException: raise RuntimeError('private checkpoint upload failed') from None
        if r.status_code not in (200,201): raise RuntimeError('private checkpoint upload HTTP '+str(r.status_code))
        return len(data)
