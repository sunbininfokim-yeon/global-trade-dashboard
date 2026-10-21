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

if __name__=='__main__':unittest.main()
