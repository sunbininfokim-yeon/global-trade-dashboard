"""Private, bounded checkpoint transport. No credentials enter the archive."""
import hashlib
import re
import time
import io
import json
import os
from pathlib import Path, PurePosixPath
import tarfile
import requests

BUCKET='idn-collector-state'
OBJECT='automatic/current.tar.gz'  # read-only legacy fallback
MANIFEST='automatic/current.json'
CHUNK_SIZE=16*1024*1024
ARCHIVE_LIMIT=1024**3
LIMIT=48*1024*1024
UNPACK_LIMIT=1024**3

def pack(root):
    out=io.BytesIO(); count=0; expanded=0
    with tarfile.open(fileobj=out,mode='w:gz', compresslevel=6) as archive:
        for path in sorted(Path(root).rglob('*')):
            if path.is_symlink(): raise ValueError('checkpoint symlink rejected')
            if path.is_file():
                rel=path.relative_to(root)
                if path.name.startswith('.env') or path.name.endswith('.lock') or path.name=='scheduler.lock': continue
                count+=1;expanded+=path.stat().st_size
                if count>20000 or expanded>UNPACK_LIMIT: raise ValueError('checkpoint expansion budget exceeded')
                archive.add(path,arcname=str(rel),recursive=False)
    data=out.getvalue()
    if len(data)>ARCHIVE_LIMIT: raise ValueError('checkpoint exceeds 1 GiB archive budget')
    return data

def unpack(data,root):
    if len(data)>ARCHIVE_LIMIT: raise ValueError('checkpoint too large')
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

class StorageError(RuntimeError):
    def __init__(self,status,missing=False):
        self.status=status;self.missing=missing
        super().__init__('private checkpoint HTTP '+str(status))

class Storage:
    def __init__(self,url,key):
        self.url=url.rstrip('/')+'/storage/v1'
        self.headers={'apikey':key}
        if key.startswith('eyJ'): self.headers['Authorization']='Bearer '+key
    def call(self,method,path,**kwargs):
        try:
            response=requests.request(method,self.url+path,headers=self.headers,timeout=(10,90),allow_redirects=False,**kwargs)
        except requests.RequestException: raise RuntimeError('private checkpoint transport failed') from None
        if response.status_code not in (200,201):
            try: body=response.json()
            except ValueError: body={}
            missing=response.status_code==404 or response.status_code==400 and str(body.get('statusCode'))=='404'
            raise StorageError(response.status_code,missing)
        return response
    def get(self,key,limit):
        response=self.call('GET','/object/'+BUCKET+'/'+key,stream=True,params={'v':str(time.time_ns())})
        data=bytearray()
        try:
            for part in response.iter_content(65536):
                data.extend(part)
                if len(data)>limit: raise ValueError('remote checkpoint object too large')
        finally: response.close()
        return bytes(data)
    def put(self,key,data,kind):
        headers={**self.headers,'Content-Type':kind,'x-upsert':'true','Cache-Control':'no-store'}
        try:
            r=requests.post(self.url+'/object/'+BUCKET+'/'+key,headers=headers,data=data,timeout=(10,90),allow_redirects=False)
        except requests.RequestException: raise RuntimeError('private checkpoint upload failed') from None
        if r.status_code not in (200,201): raise RuntimeError('private checkpoint upload HTTP '+str(r.status_code))
    def restore(self,root):
        try: raw=self.get(MANIFEST,65536)
        except StorageError as e:
            if not e.missing: raise
            # Only genuinely absent manifest falls back. Corruption/auth/network errors never reset progress.
            unpack(self.get(OBJECT,LIMIT),root);return
        manifest=json.loads(raw)
        if manifest.get('version')!=2 or type(manifest.get('size')) is not int or not 1<=manifest['size']<=ARCHIVE_LIMIT:
            raise ValueError('invalid checkpoint manifest')
        parts=manifest.get('parts')
        if not isinstance(parts,list) or not 1<=len(parts)<=64: raise ValueError('invalid checkpoint parts')
        if not re.fullmatch('[a-f0-9]{64}',str(manifest.get('sha256'))): raise ValueError('invalid checkpoint digest')
        for part in parts:
            if not isinstance(part,dict) or not re.fullmatch('[a-f0-9]{64}',str(part.get('sha256'))) or type(part.get('size')) is not int or not 1<=part['size']<=CHUNK_SIZE:
                raise ValueError('invalid checkpoint part')
        if sum(p['size'] for p in parts)!=manifest['size']: raise ValueError('checkpoint manifest size mismatch')
        data=bytearray()
        for part in parts:
            chunk=self.get('automatic/chunks/'+part['sha256'],CHUNK_SIZE)
            if len(chunk)!=part['size'] or hashlib.sha256(chunk).hexdigest()!=part['sha256']: raise ValueError('checkpoint part checksum mismatch')
            data.extend(chunk)
        if hashlib.sha256(data).hexdigest()!=manifest['sha256']: raise ValueError('checkpoint checksum mismatch')
        unpack(bytes(data),root)
    def save(self,root):
        data=pack(root);parts=[]
        for start in range(0,len(data),CHUNK_SIZE):
            chunk=data[start:start+CHUNK_SIZE];digest=hashlib.sha256(chunk).hexdigest()
            self.put('automatic/chunks/'+digest,chunk,'application/gzip')
            parts.append({'sha256':digest,'size':len(chunk)})
        manifest={'version':2,'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'parts':parts}
        # Commit the small pointer LAST. Any failed chunk keeps the prior checkpoint usable.
        self.put(MANIFEST,json.dumps(manifest).encode(),'application/json')
        return len(data)
