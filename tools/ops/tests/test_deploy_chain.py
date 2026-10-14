from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_deploy_chain import pushes_to_main


class PublisherChainTests(unittest.TestCase):
    def test_indirect_python_publisher_is_still_a_main_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'publisher.py').write_text("git('push', 'origin', 'HEAD:main', check=False)\n")
            self.assertTrue(pushes_to_main("python3 'publisher.py' --checkpoint x", root))

    def test_review_branch_script_is_not_a_main_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'publisher.py').write_text("git('push', 'origin', 'review-branch')\n")
            self.assertFalse(pushes_to_main("python3 'publisher.py'", root))

    def test_existing_shell_main_push_is_detected(self):
        self.assertTrue(pushes_to_main('git push origin HEAD:main'))
