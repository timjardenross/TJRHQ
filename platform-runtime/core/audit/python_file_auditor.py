"""
Python File Auditor Module

This module provides functionality to scan Python files in a repository,
distinguishing between test files and source files, and generating metrics
about the codebase.
"""

import os
from pathlib import Path
from typing import Dict, List, Tuple

class PythonFileAuditor:
    """
    Auditor for Python files in a repository, distinguishing between
    test files and source files.
    """

    def __init__(self, repo_root: str):
        """
        Initialize the auditor with the repository root path.

        Args:
            repo_root: Path to the root of the repository to audit
        """
        self.repo_root = Path(repo_root).resolve()
        self.test_suffixes = ('test_', 'tests/', '_test.py')
        self.source_extensions = ('.py',)

    def is_test_file(self, filepath: Path) -> bool:
        """
        Determine if a file is a test file based on its path and name.

        Args:
            filepath: Path to the file to check

        Returns:
            bool: True if the file is a test file, False otherwise
        """
        # Check if the file is in a test directory
        if any(part == 'test' or part.endswith('tests') for part in filepath.parts):
            return True

        # Check if the file has a test-related suffix or prefix
        if any(suffix in str(filepath) for suffix in self.test_suffixes):
            return True

        return False

    def find_python_files(self) -> Tuple[List[Path], List[Path]]:
        """
        Find all Python files in the repository and separate them into
        test files and source files.

        Returns:
            Tuple of (source_files, test_files) where each is a list of Path objects
        """
        source_files = []
        test_files = []

        for root, _, files in os.walk(self.repo_root):
            current_path = Path(root)

            # Skip virtual environments and other excluded directories
            if any(part in ('venv', '.venv', 'site-packages') for part in current_path.parts):
                continue

            for file in files:
                if file.endswith(self.source_extensions):
                    file_path = current_path / file
                    if self.is_test_file(file_path):
                        test_files.append(file_path)
                    else:
                        source_files.append(file_path)

        return source_files, test_files

    def generate_metrics(self) -> Dict[str, int]:
        """
        Generate metrics about the Python files in the repository.

        Returns:
            Dictionary containing metrics about source and test files
        """
        source_files, test_files = self.find_python_files()

        return {
            'total_python_files': len(source_files) + len(test_files),
            'source_files': len(source_files),
            'test_files': len(test_files),
            'test_coverage_ratio': len(test_files) / len(source_files) if source_files else 0
        }

    def reconcile_with_test_suites(self) -> Dict[str, List[str]]:
        """
        Reconcile source files with their corresponding test suites.

        Returns:
            Dictionary mapping source files to their test suites
        """
        source_files, test_files = self.find_python_files()
        reconciliation = {}

        # Create a mapping of source file names to paths
        source_map = {f.name: f for f in source_files}

        for test_file in test_files:
            # Try to find a corresponding source file
            for suffix in self.test_suffixes:
                if suffix in str(test_file):
                    # Remove test-related parts to find potential source file
                    source_name = str(test_file.name).replace(suffix, '').replace('.py', '.py')
                    if source_name in source_map:
                        if source_map[source_name] not in reconciliation:
                            reconciliation[source_map[source_name]] = []
                        reconciliation[source_map[source_name]].append(str(test_file))
                        break

        return reconciliation
