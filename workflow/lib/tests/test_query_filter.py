"""Tests for query_filter module."""

import pandas as pd

from workflow.lib.query_filter import query_dicoms


class TestMetadataMappingsConstant:
    """Test constant value functionality in metadata mappings."""

    def test_constant_session_value(self, monkeypatch):
        """Test that constant session value is applied to all rows."""
        # Create mock data
        mock_df = pd.DataFrame(
            {
                "PatientID": ["Patient1", "Patient2", "Patient3"],
                "StudyDate": ["20230101", "20230102", "20230103"],
                "StudyInstanceUID": ["1.2.3.4", "1.2.3.5", "1.2.3.6"],
            }
        )

        # Mock query_metadata to return our test dataframe
        def mock_query_metadata(return_type=None, **kwargs):
            return mock_df.copy()

        # Patch the query_metadata function
        import workflow.lib.query_filter as qf_module

        monkeypatch.setattr(qf_module, "query_metadata", mock_query_metadata)

        # Define search spec with constant session
        search_specs = [
            {
                "dicom_query": {
                    "study_description": "Test^*",
                    "study_date": "20230101-",
                },
                "metadata_mappings": {
                    "subject": {
                        "source": "PatientID",
                        "sanitize": True,
                    },
                    "session": {
                        "constant": "15T",
                    },
                },
            }
        ]

        # Call query_dicoms
        result_df = query_dicoms(search_specs)

        # Verify that all rows have the constant session value
        assert len(result_df) == 3
        assert all(result_df["session"] == "15T")
        assert list(result_df["subject"]) == ["Patient1", "Patient2", "Patient3"]

    def test_constant_subject_value(self, monkeypatch):
        """Test that constant subject value is applied to all rows."""
        # Create mock data
        mock_df = pd.DataFrame(
            {
                "PatientID": ["Patient1", "Patient2"],
                "StudyDate": ["20230101", "20230102"],
                "StudyInstanceUID": ["1.2.3.4", "1.2.3.5"],
            }
        )

        # Mock query_metadata to return our test dataframe
        def mock_query_metadata(return_type=None, **kwargs):
            return mock_df.copy()

        # Patch the query_metadata function
        import workflow.lib.query_filter as qf_module

        monkeypatch.setattr(qf_module, "query_metadata", mock_query_metadata)

        # Define search spec with constant subject
        search_specs = [
            {
                "dicom_query": {
                    "study_description": "Test^*",
                    "study_date": "20230101-",
                },
                "metadata_mappings": {
                    "subject": {
                        "constant": "pilot",
                    },
                    "session": {
                        "source": "StudyDate",
                        "sanitize": True,
                    },
                },
            }
        ]

        # Call query_dicoms
        result_df = query_dicoms(search_specs)

        # Verify that all rows have the constant subject value
        assert len(result_df) == 2
        assert all(result_df["subject"] == "pilot")
        assert list(result_df["session"]) == ["20230101", "20230102"]

    def test_constant_both_subject_and_session(self, monkeypatch):
        """Test constant values for both subject and session."""
        # Create mock data
        mock_df = pd.DataFrame(
            {
                "PatientID": ["Patient1", "Patient2"],
                "StudyDate": ["20230101", "20230102"],
                "StudyInstanceUID": ["1.2.3.4", "1.2.3.5"],
            }
        )

        # Mock query_metadata to return our test dataframe
        def mock_query_metadata(return_type=None, **kwargs):
            return mock_df.copy()

        # Patch the query_metadata function
        import workflow.lib.query_filter as qf_module

        monkeypatch.setattr(qf_module, "query_metadata", mock_query_metadata)

        # Define search spec with constant subject and session
        search_specs = [
            {
                "dicom_query": {
                    "study_description": "Test^*",
                    "study_date": "20230101-",
                },
                "metadata_mappings": {
                    "subject": {
                        "constant": "pilot",
                    },
                    "session": {
                        "constant": "01",
                    },
                },
            }
        ]

        # Call query_dicoms
        result_df = query_dicoms(search_specs)

        # Verify that all rows have the constant values
        assert len(result_df) == 2
        assert all(result_df["subject"] == "pilot")
        assert all(result_df["session"] == "01")

    def test_constant_overrides_source(self, monkeypatch):
        """Test that constant takes precedence when both constant and source are present."""
        # Create mock data
        mock_df = pd.DataFrame(
            {
                "PatientID": ["Patient1", "Patient2"],
                "StudyDate": ["20230101", "20230102"],
                "StudyInstanceUID": ["1.2.3.4", "1.2.3.5"],
            }
        )

        # Mock query_metadata to return our test dataframe
        def mock_query_metadata(return_type=None, **kwargs):
            return mock_df.copy()

        # Patch the query_metadata function
        import workflow.lib.query_filter as qf_module

        monkeypatch.setattr(qf_module, "query_metadata", mock_query_metadata)

        # Define search spec with both constant and source (constant should win)
        search_specs = [
            {
                "dicom_query": {
                    "study_description": "Test^*",
                    "study_date": "20230101-",
                },
                "metadata_mappings": {
                    "subject": {
                        "source": "PatientID",
                        "sanitize": True,
                    },
                    "session": {
                        "source": "StudyDate",
                        "constant": "15T",  # This should override source
                        "sanitize": True,
                    },
                },
            }
        ]

        # Call query_dicoms
        result_df = query_dicoms(search_specs)

        # Verify that constant value is used, not source
        assert len(result_df) == 2
        assert all(result_df["session"] == "15T")
        assert list(result_df["subject"]) == ["Patient1", "Patient2"]

    def test_traditional_mapping_still_works(self, monkeypatch):
        """Test that traditional source-based mapping still works when constant is not present."""
        # Create mock data
        mock_df = pd.DataFrame(
            {
                "PatientID": ["TestPatient001", "TestPatient002"],
                "StudyDate": ["20230101", "20230102"],
                "StudyInstanceUID": ["1.2.3.4", "1.2.3.5"],
            }
        )

        # Mock query_metadata to return our test dataframe
        def mock_query_metadata(return_type=None, **kwargs):
            return mock_df.copy()

        # Patch the query_metadata function
        import workflow.lib.query_filter as qf_module

        monkeypatch.setattr(qf_module, "query_metadata", mock_query_metadata)

        # Define search spec without constant (traditional approach)
        search_specs = [
            {
                "dicom_query": {
                    "study_description": "Test^*",
                    "study_date": "20230101-",
                },
                "metadata_mappings": {
                    "subject": {
                        "source": "PatientID",
                        "pattern": r"TestPatient([0-9]+)",
                        "sanitize": True,
                    },
                    "session": {
                        "source": "StudyDate",
                        "sanitize": True,
                    },
                },
            }
        ]

        # Call query_dicoms
        result_df = query_dicoms(search_specs)

        # Verify traditional mapping works
        assert len(result_df) == 2
        assert list(result_df["subject"]) == ["001", "002"]
        assert list(result_df["session"]) == ["20230101", "20230102"]


class TestCombinedQuery:
    """Test combined DICOM and filesystem query functionality."""

    def test_combined_query_dicom_only(self, monkeypatch):
        """Test combined query with only DICOM specs."""
        # Create mock data
        mock_df = pd.DataFrame(
            {
                "PatientID": ["Patient1", "Patient2"],
                "StudyDate": ["20230101", "20230102"],
                "StudyInstanceUID": ["1.2.3.4", "1.2.3.5"],
            }
        )

        # Mock query_metadata to return our test dataframe
        def mock_query_metadata(return_type=None, **kwargs):
            return mock_df.copy()

        # Patch the query_metadata function
        import workflow.lib.query_filter as qf_module

        monkeypatch.setattr(qf_module, "query_metadata", mock_query_metadata)

        # Import after patching
        from workflow.lib.query_filter import query_combined

        # Define DICOM-only search specs
        search_specs = [
            {
                "dicom_query": {
                    "study_description": "Test^*",
                    "study_date": "20230101-",
                },
                "metadata_mappings": {
                    "subject": {"source": "PatientID", "sanitize": True},
                    "session": {"source": "StudyDate", "sanitize": True},
                },
            }
        ]

        # Call query_combined
        result_df = query_combined(search_specs)

        # Verify results
        assert len(result_df) == 2
        assert list(result_df["source"]) == ["dicom", "dicom"]
        assert list(result_df["subject"]) == ["Patient1", "Patient2"]

    def test_combined_query_filesystem_only(self, tmp_path):
        """Test combined query with only filesystem specs."""
        # Create test files
        (tmp_path / "sub-001_20230101.tar.gz").touch()
        (tmp_path / "sub-002_20230102.tar.gz").touch()

        # Import function
        from workflow.lib.query_filter import query_combined

        # Define filesystem-only search specs
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

        # Call query_combined
        result_df = query_combined(search_specs)

        # Verify results
        assert len(result_df) == 2
        assert list(result_df["source"]) == ["filesystem", "filesystem"]
        assert list(result_df["subject"]) == ["001", "002"]

    def test_combined_query_both_sources(self, monkeypatch, tmp_path):
        """Test combined query with both DICOM and filesystem specs."""
        # Create mock DICOM data
        mock_df = pd.DataFrame(
            {
                "PatientID": ["PatientA"],
                "StudyDate": ["20230101"],
                "StudyInstanceUID": ["1.2.3.4"],
            }
        )

        # Mock query_metadata
        def mock_query_metadata(return_type=None, **kwargs):
            return mock_df.copy()

        import workflow.lib.query_filter as qf_module

        monkeypatch.setattr(qf_module, "query_metadata", mock_query_metadata)

        # Create test filesystem files
        (tmp_path / "sub-B_20230102.tar.gz").touch()

        # Import function
        from workflow.lib.query_filter import query_combined

        # Define combined search specs
        search_specs = [
            {
                "dicom_query": {
                    "study_description": "Test^*",
                    "study_date": "20230101-",
                },
                "metadata_mappings": {
                    "subject": {"source": "PatientID", "sanitize": True},
                    "session": {"source": "StudyDate", "sanitize": True},
                },
            },
            {
                "fs_query": {
                    "path": str(tmp_path),
                    "pattern": r"sub-(?P<PatientID>[A-Z])_(?P<StudyDate>\d{8})\.tar\.gz",
                },
                "metadata_mappings": {
                    "subject": {"source": "PatientID", "sanitize": True},
                    "session": {"source": "StudyDate", "sanitize": True},
                },
            },
        ]

        # Call query_combined
        result_df = query_combined(search_specs)

        # Verify combined results
        assert len(result_df) == 2
        # One DICOM source, one filesystem source
        assert (result_df["source"] == "dicom").sum() == 1
        assert (result_df["source"] == "filesystem").sum() == 1

    def test_combined_query_no_matches_raises_error(self):
        """Test that combined query with no matches raises LookupError."""
        # Import function
        from workflow.lib.query_filter import query_combined

        # Define search specs that won't match anything
        search_specs = []

        # Call query_combined and expect error
        with pytest.raises(LookupError, match="No matching studies found"):
            query_combined(search_specs)
