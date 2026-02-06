"""Tests for filesystem query module."""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from workflow.lib.fs_query import query_filesystem


class TestFilesystemQuery:
    """Test filesystem querying functionality."""

    def test_query_tar_files(self, tmp_path):
        """Test querying tar.gz files with pattern matching."""
        # Create test tar.gz files
        test_files = [
            "sub-001_20230101.tar.gz",
            "sub-002_20230102.tar.gz",
            "sub-003_20230103.tar.gz",
        ]
        
        for filename in test_files:
            (tmp_path / filename).touch()

        # Define search spec
        search_specs = [
            {
                "fs_query": {
                    "path": str(tmp_path),
                    "pattern": r"sub-(?P<PatientID>\d+)_(?P<StudyDate>\d{8})\.tar\.gz",
                },
                "metadata_mappings": {
                    "subject": {"source": "PatientID", "sanitize": True},
                    "session": {"source": "StudyDate", "sanitize": True},
                },
            }
        ]

        # Execute query
        result_df = query_filesystem(search_specs)

        # Verify results
        assert len(result_df) == 3
        assert all(result_df["subject"] == ["001", "002", "003"])
        assert all(result_df["session"] == ["20230101", "20230102", "20230103"])
        assert all(result_df["path"].str.endswith(".tar.gz"))

    def test_query_folders(self, tmp_path):
        """Test querying folders with pattern matching."""
        # Create test folders
        test_folders = [
            "Patient_ABC_20230101",
            "Patient_DEF_20230102",
            "Patient_GHI_20230103",
        ]
        
        for foldername in test_folders:
            (tmp_path / foldername).mkdir()

        # Define search spec
        search_specs = [
            {
                "fs_query": {
                    "path": str(tmp_path),
                    "pattern": r"Patient_(?P<PatientID>[A-Z]+)_(?P<StudyDate>\d{8})",
                },
                "metadata_mappings": {
                    "subject": {"source": "PatientID", "sanitize": True},
                    "session": {"source": "StudyDate", "sanitize": True},
                },
            }
        ]

        # Execute query
        result_df = query_filesystem(search_specs)

        # Verify results
        assert len(result_df) == 3
        assert all(result_df["subject"] == ["ABC", "DEF", "GHI"])
        assert all(result_df["session"] == ["20230101", "20230102", "20230103"])

    def test_query_with_pattern_extraction(self, tmp_path):
        """Test regex pattern extraction in metadata mappings."""
        # Create test files
        test_files = [
            "study_sub-001_ses-baseline.tar",
            "study_sub-002_ses-followup.tar",
        ]
        
        for filename in test_files:
            (tmp_path / filename).touch()

        # Define search spec with pattern extraction
        search_specs = [
            {
                "fs_query": {
                    "path": str(tmp_path),
                    "pattern": r"study_sub-(?P<SubjectID>\d+)_ses-(?P<SessionID>\w+)\.tar",
                },
                "metadata_mappings": {
                    "subject": {
                        "source": "SubjectID",
                        "pattern": r"(\d+)",
                        "sanitize": True,
                    },
                    "session": {"source": "SessionID", "sanitize": True},
                },
            }
        ]

        # Execute query
        result_df = query_filesystem(search_specs)

        # Verify results
        assert len(result_df) == 2
        assert all(result_df["subject"] == ["001", "002"])
        assert all(result_df["session"] == ["baseline", "followup"])

    def test_query_with_constant_values(self, tmp_path):
        """Test constant value functionality."""
        # Create test files
        test_files = [
            "scan_20230101.tar.gz",
            "scan_20230102.tar.gz",
        ]
        
        for filename in test_files:
            (tmp_path / filename).touch()

        # Define search spec with constant session
        search_specs = [
            {
                "fs_query": {
                    "path": str(tmp_path),
                    "pattern": r"scan_(?P<StudyDate>\d{8})\.tar\.gz",
                },
                "metadata_mappings": {
                    "subject": {"constant": "pilot"},
                    "session": {"source": "StudyDate", "sanitize": True},
                },
            }
        ]

        # Execute query
        result_df = query_filesystem(search_specs)

        # Verify results
        assert len(result_df) == 2
        assert all(result_df["subject"] == "pilot")
        assert all(result_df["session"] == ["20230101", "20230102"])

    def test_query_with_mapping(self, tmp_path):
        """Test value mapping functionality."""
        # Create test files
        test_files = [
            "sub-A_20230101.tar.gz",
            "sub-B_20230102.tar.gz",
        ]
        
        for filename in test_files:
            (tmp_path / filename).touch()

        # Define search spec with value mapping
        search_specs = [
            {
                "fs_query": {
                    "path": str(tmp_path),
                    "pattern": r"sub-(?P<SubID>[A-Z])_(?P<StudyDate>\d{8})\.tar\.gz",
                },
                "metadata_mappings": {
                    "subject": {
                        "source": "SubID",
                        "map": {"A": "001", "B": "002"},
                        "sanitize": False,
                    },
                    "session": {"source": "StudyDate", "sanitize": True},
                },
            }
        ]

        # Execute query
        result_df = query_filesystem(search_specs)

        # Verify results
        assert len(result_df) == 2
        assert all(result_df["subject"] == ["001", "002"])
        assert all(result_df["session"] == ["20230101", "20230102"])

    def test_empty_query(self, tmp_path):
        """Test query with no matches."""
        # Define search spec that won't match anything
        search_specs = [
            {
                "fs_query": {
                    "path": str(tmp_path),
                    "pattern": r"nonexistent_(?P<PatientID>\d+)\.tar\.gz",
                },
                "metadata_mappings": {
                    "subject": {"source": "PatientID", "sanitize": True},
                    "session": {"constant": "01"},
                },
            }
        ]

        # Execute query
        result_df = query_filesystem(search_specs)

        # Verify empty result with expected columns
        assert len(result_df) == 0
        assert "subject" in result_df.columns
        assert "session" in result_df.columns
        assert "path" in result_df.columns

    def test_multiple_specs(self, tmp_path):
        """Test combining results from multiple search specs."""
        # Create test files in different patterns
        (tmp_path / "typeA_sub-001_20230101.tar.gz").touch()
        (tmp_path / "typeB_sub-002_20230102.tar.gz").touch()

        # Define multiple search specs
        search_specs = [
            {
                "fs_query": {
                    "path": str(tmp_path),
                    "pattern": r"typeA_sub-(?P<PatientID>\d+)_(?P<StudyDate>\d{8})\.tar\.gz",
                },
                "metadata_mappings": {
                    "subject": {"source": "PatientID", "sanitize": True},
                    "session": {"source": "StudyDate", "sanitize": True},
                },
            },
            {
                "fs_query": {
                    "path": str(tmp_path),
                    "pattern": r"typeB_sub-(?P<PatientID>\d+)_(?P<StudyDate>\d{8})\.tar\.gz",
                },
                "metadata_mappings": {
                    "subject": {"source": "PatientID", "sanitize": True},
                    "session": {"source": "StudyDate", "sanitize": True},
                },
            },
        ]

        # Execute query
        result_df = query_filesystem(search_specs)

        # Verify combined results
        assert len(result_df) == 2
        assert all(result_df["subject"] == ["001", "002"])

    def test_missing_source_field_raises_error(self, tmp_path):
        """Test that missing source field raises appropriate error."""
        # Create test file
        (tmp_path / "test.tar.gz").touch()

        # Define search spec with non-existent source field
        search_specs = [
            {
                "fs_query": {
                    "path": str(tmp_path),
                    "pattern": r"(?P<PatientID>test)\.tar\.gz",
                },
                "metadata_mappings": {
                    "subject": {
                        "source": "NonExistentField",  # This field doesn't exist
                        "sanitize": True,
                    },
                    "session": {"constant": "01"},
                },
            }
        ]

        # Execute query and expect error
        with pytest.raises(ValueError, match="Source column.*not found"):
            query_filesystem(search_specs)

    def test_sanitize_removes_special_characters(self, tmp_path):
        """Test that sanitize option removes non-alphanumeric characters."""
        # Create test file with special characters in pattern
        (tmp_path / "sub-001-test_20230101.tar.gz").touch()

        # Define search spec
        search_specs = [
            {
                "fs_query": {
                    "path": str(tmp_path),
                    "pattern": r"sub-(?P<PatientID>[0-9]+-test)_(?P<StudyDate>\d{8})\.tar\.gz",
                },
                "metadata_mappings": {
                    "subject": {"source": "PatientID", "sanitize": True},
                    "session": {"source": "StudyDate", "sanitize": True},
                },
            }
        ]

        # Execute query
        result_df = query_filesystem(search_specs)

        # Verify sanitization removed special characters
        assert result_df["subject"].iloc[0] == "001test"
