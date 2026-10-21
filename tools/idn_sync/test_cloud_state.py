import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from cloud_state import pack,unpack

class CheckpointTests(unittest.TestCase):
    def test_roundtrip_preserves_cursors_stop_and_artifacts_without_env(self):
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            root=Path(a);(root/'active-run.json').write_text('{"phase":"refresh","candidate_index":2}')
            (root/'STOP').touch();(root/'.env').write_text('do not publish');(root/'scheduler.lock').touch()
            (root/'runs').mkdir();(root/'runs'/'candidate.json').write_text('official evidence')
            unpack(pack(root),Path(b));out=Path(b)
            self.assertTrue((out/'STOP').exists());self.assertEqual((out/'active-run.json').read_bytes(),(root/'active-run.json').read_bytes())
            self.assertEqual((out/'runs/candidate.json').read_text(),'official evidence');self.assertFalse((out/'.env').exists());self.assertFalse((out/'scheduler.lock').exists())
    def test_traversal_links_and_missing_checkpoint_fail_closed(self):
        for name,kind in [('../escape',tarfile.REGTYPE),('/absolute',tarfile.REGTYPE),('link',tarfile.SYMTYPE)]:
            stream=io.BytesIO()
            with tarfile.open(fileobj=stream,mode='w:gz') as archive:
                item=tarfile.TarInfo(name);item.type=kind;archive.addfile(item)
            with tempfile.TemporaryDirectory() as d,self.assertRaises(ValueError):unpack(stream.getvalue(),Path(d))
        with tempfile.TemporaryDirectory() as d,self.assertRaises(ValueError):unpack(pack(Path(d)),Path(d))


class MemoryStorage(__import__('cloud_state').Storage):
    def __init__(self):self.objects={};self.fail_key=None;self.upload_sizes=[]
    def get(self,key,limit):
        from cloud_state import StorageError
        if key not in self.objects:raise StorageError(404,True)
        data=self.objects[key]
        if len(data)>limit:raise ValueError('too large')
        return data
    def put(self,key,data,kind):
        if self.fail_key and self.fail_key in key:raise RuntimeError('injected upload failure')
        self.objects[key]=data;self.upload_sizes.append(len(data))

class ChunkTests(unittest.TestCase):
    def test_over_48_mib_roundtrip_keeps_each_object_small(self):
        import os
        from cloud_state import CHUNK_SIZE,MANIFEST
        with tempfile.TemporaryDirectory() as d,tempfile.TemporaryDirectory() as target:
            root=Path(d);(root/'active-run.json').write_text('{"phase":"admission","candidate_index":5,"cooldowns":{"blocked.go.id":99999}}')
            body=os.urandom(49*1024*1024);(root/'raw').mkdir();(root/'raw'/'official-source').write_bytes(body)
            remote=MemoryStorage();size=remote.save(root)
            self.assertGreater(size,48*1024*1024);self.assertLessEqual(max(remote.upload_sizes),CHUNK_SIZE)
            remote.restore(target);self.assertEqual((Path(target)/'raw/official-source').read_bytes(),body)
            self.assertEqual((Path(target)/'active-run.json').read_bytes(),(root/'active-run.json').read_bytes())
    def test_failed_chunk_preserves_previous_manifest_and_corruption_never_falls_back(self):
        import json
        from cloud_state import MANIFEST
        with tempfile.TemporaryDirectory() as d,tempfile.TemporaryDirectory() as out:
            root=Path(d);(root/'active-run.json').write_text('{"cursor":2}')
            remote=MemoryStorage();remote.save(root);prior=remote.objects[MANIFEST]
            (root/'active-run.json').write_text('{"cursor":3}');remote.fail_key='chunks/'
            with self.assertRaises(RuntimeError):remote.save(root)
            self.assertEqual(remote.objects[MANIFEST],prior)
            remote.restore(out);self.assertEqual((Path(out)/'active-run.json').read_text(),'{"cursor":2}')
            remote.objects[MANIFEST]=b'{broken json'
            with self.assertRaises(ValueError):remote.restore(out)
    def test_legacy_upgrade_and_missing_chunk_rejection(self):
        import json
        from cloud_state import MANIFEST,OBJECT
        with tempfile.TemporaryDirectory() as d,tempfile.TemporaryDirectory() as out:
            root=Path(d);(root/'active-run.json').write_text('{"cursor":4}')
            remote=MemoryStorage();remote.objects[OBJECT]=pack(root);remote.restore(out)
            remote.save(root);manifest=json.loads(remote.objects[MANIFEST]);del remote.objects['automatic/chunks/'+manifest['parts'][0]['sha256']]
            with self.assertRaises(RuntimeError):remote.restore(out)

if __name__=='__main__':unittest.main()
