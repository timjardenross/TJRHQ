"""
Test suite for the PythonFileAuditor class.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from platform_runtime.core.audit.python_file_auditor import PythonFileAuditor

class TestPythonFileAuditor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.repo_root = Path(self.temp_dir.name)

        # Create test directory structure
        (self.repo_root / "src").mkdir()
        (self.repo_root / "tests").mkdir()
        (self.repo_root / "venv").mkdir()

        # Create some test files
        (self.repo_root / "src" / "module.py").write_text("print('source')")
        (self.repo_root / "src" / "test_module.py").write_text("print('test')")
        (self.repo_root / "tests" / "test_module.py").write_text("print('test')")
        (self.repo_root / "src" / "submodule" / "test_module.py").write_text("print('test')")
        (self.repo_root / "src" / "submodule" / "module.py").write_text("print('source')")

        self.auditor = PythonFileAuditor(str(self.repo_root))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_is_test_file(self):
        test_file = self.repo_root / "tests" / "test_module.py"
        self.assertTrue(self.auditor.is_test_file(test_file))

        source_file = self.repo_root / "src" / "module.py"
        self.assertFalse(self.auditor.is_test_file(source_file))

    def test_find_python_files(self):
        source_files, test_files = self.auditor.find_python_files()

        # Verify source files
        self.assertEqual(len(source_files), 2)
        self.assertTrue(any(f.name == "module.py" for f in source_files))
        self.assertTrue(any(f.name == "module.py" and "submodule" in str(f) for f in source_files))

        # Verify test files
        self.assertEqual(len(test_files), 3)
        self.assertTrue(any(f.name == "test_module.py" for f in test_files))
        self.assertTrue(any(f.name == "test_module.py" and "tests" in str(f) for f in test_files))
        self.assertTrue(any(f.name == "test_module.py" and "submodule" in str(f) for f in test_files))

    def test_generate_metrics(self):
        metrics = self.auditor.generate_metrics()

        self.assertEqual(metrics['total_python_files'], 5)
        self.assertEqual(metrics['source_files'], 2)
        self.assertEqual(metrics['test_files'], 3)
        self.assertAlmostEqual(metrics['test_coverage_ratio'], 1.5, places=1)

    def test_reconcile_with_test_suites(self):
        reconciliation = self.auditor.reconcile_with_test_suites()

        # Verify that source files are mapped to their test suites
        self.assertEqual(len(reconciliation), 2)
        for source_file, test_files in reconciliation.items():
            if "submodule" in str(source_file):
                self.assertEqual(len(test_files), 1)
                self.assertTrue("submodule" in test_files[0])
            else:
                self.assertEqual(len(test_files), 2)
                self.assertTrue(any("tests" in f for f in test_files))
                self.assertTrue(any("src/test_module.py" in f for f in test_files))

if __name__ == "__main__":
    unittest.main()
