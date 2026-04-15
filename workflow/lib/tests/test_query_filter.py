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


class TestMetadataMappingsFormat:
    """Test format string functionality in metadata mappings."""

    def test_format_prepend(self, monkeypatch):
        """Test that format string can prepend text to extracted value."""
        mock_df = pd.DataFrame(
            {
                "PatientID": ["TestPatient001", "TestPatient002"],
                "StudyDate": ["20230101", "20230102"],
                "StudyInstanceUID": ["1.2.3.4", "1.2.3.5"],
            }
        )

        def mock_query_metadata(return_type=None, **kwargs):
            return mock_df.copy()

        import workflow.lib.query_filter as qf_module

        monkeypatch.setattr(qf_module, "query_metadata", mock_query_metadata)

        search_specs = [
            {
                "dicom_query": {"study_description": "Test^*"},
                "metadata_mappings": {
                    "subject": {
                        "source": "PatientID",
                        "pattern": r"TestPatient([0-9]+)",
                        "sanitize": True,
                        "format": "AA{value}",
                    },
                    "session": {
                        "source": "StudyDate",
                        "sanitize": True,
                    },
                },
            }
        ]

        result_df = query_dicoms(search_specs)

        assert len(result_df) == 2
        assert list(result_df["subject"]) == ["AA001", "AA002"]
        assert list(result_df["session"]) == ["20230101", "20230102"]

    def test_format_append(self, monkeypatch):
        """Test that format string can append text to extracted value."""
        mock_df = pd.DataFrame(
            {
                "PatientID": ["001", "002"],
                "StudyDate": ["20230101", "20230102"],
                "StudyInstanceUID": ["1.2.3.4", "1.2.3.5"],
            }
        )

        def mock_query_metadata(return_type=None, **kwargs):
            return mock_df.copy()

        import workflow.lib.query_filter as qf_module

        monkeypatch.setattr(qf_module, "query_metadata", mock_query_metadata)

        search_specs = [
            {
                "dicom_query": {"study_description": "Test^*"},
                "metadata_mappings": {
                    "subject": {
                        "source": "PatientID",
                        "sanitize": True,
                        "format": "{value}suffix",
                    },
                    "session": {
                        "source": "StudyDate",
                        "sanitize": True,
                    },
                },
            }
        ]

        result_df = query_dicoms(search_specs)

        assert len(result_df) == 2
        assert list(result_df["subject"]) == ["001suffix", "002suffix"]

    def test_format_applied_after_map(self, monkeypatch):
        """Test that format is applied after map remapping."""
        mock_df = pd.DataFrame(
            {
                "PatientID": ["old001", "old002"],
                "StudyDate": ["20230101", "20230102"],
                "StudyInstanceUID": ["1.2.3.4", "1.2.3.5"],
            }
        )

        def mock_query_metadata(return_type=None, **kwargs):
            return mock_df.copy()

        import workflow.lib.query_filter as qf_module

        monkeypatch.setattr(qf_module, "query_metadata", mock_query_metadata)

        search_specs = [
            {
                "dicom_query": {"study_description": "Test^*"},
                "metadata_mappings": {
                    "subject": {
                        "source": "PatientID",
                        "sanitize": True,
                        "map": {"old001": "new001", "old002": "new002"},
                        "format": "sub{value}",
                    },
                    "session": {
                        "source": "StudyDate",
                        "sanitize": True,
                    },
                },
            }
        ]

        result_df = query_dicoms(search_specs)

        assert len(result_df) == 2
        assert list(result_df["subject"]) == ["subnew001", "subnew002"]

    def test_format_without_pattern(self, monkeypatch):
        """Test that format works without a pattern."""
        mock_df = pd.DataFrame(
            {
                "PatientID": ["001", "002"],
                "StudyDate": ["20230101", "20230102"],
                "StudyInstanceUID": ["1.2.3.4", "1.2.3.5"],
            }
        )

        def mock_query_metadata(return_type=None, **kwargs):
            return mock_df.copy()

        import workflow.lib.query_filter as qf_module

        monkeypatch.setattr(qf_module, "query_metadata", mock_query_metadata)

        search_specs = [
            {
                "dicom_query": {"study_description": "Test^*"},
                "metadata_mappings": {
                    "subject": {
                        "source": "PatientID",
                        "sanitize": False,
                        "format": "prefix{value}suffix",
                    },
                    "session": {
                        "source": "StudyDate",
                        "sanitize": True,
                    },
                },
            }
        ]

        result_df = query_dicoms(search_specs)

        assert len(result_df) == 2
        assert list(result_df["subject"]) == ["prefix001suffix", "prefix002suffix"]


class TestMetadataMappingsDerivedSource:
    """Test that 'source' can reference previously-derived columns."""

    def _mock_setup(self, monkeypatch, mock_df):
        def mock_query_metadata(return_type=None, **kwargs):
            return mock_df.copy()

        import workflow.lib.query_filter as qf_module

        monkeypatch.setattr(qf_module, "query_metadata", mock_query_metadata)

    def test_session_source_subject(self, monkeypatch):
        """session.source: subject – map session labels based on derived subject column."""
        mock_df = pd.DataFrame(
            {
                "PatientID": ["sub-01extra", "sub-02extra", "sub-03extra"],
                "StudyDate": ["20230101", "20230102", "20230103"],
                "StudyInstanceUID": ["1.2.3.4", "1.2.3.5", "1.2.3.6"],
            }
        )
        self._mock_setup(monkeypatch, mock_df)

        search_specs = [
            {
                "dicom_query": {
                    "study_description": "Test^*",
                    "study_date": "20230101-",
                },
                "metadata_mappings": {
                    "subject": {
                        "source": "PatientID",
                        "pattern": r"[sS][uU][bB][-_]([a-zA-Z0-9]+)",
                        "sanitize": True,
                    },
                    "session": {
                        # Reference the already-derived 'subject' column
                        "source": "subject",
                        "map": {
                            "01extra": "3T",
                            "02extra": "3T",
                        },
                        "default": "7T",
                    },
                },
            }
        ]

        result_df = query_dicoms(search_specs)

        assert len(result_df) == 3
        assert list(result_df["subject"]) == ["01extra", "02extra", "03extra"]
        # sub-01 and sub-02 explicitly mapped to 3T; sub-03 gets the default 7T
        assert list(result_df["session"]) == ["3T", "3T", "7T"]

    def test_session_source_subject_constant_as_default(self, monkeypatch):
        """'constant' acts as catch-all default when 'map' is also present."""
        mock_df = pd.DataFrame(
            {
                "PatientID": ["sub01", "sub02", "sub03"],
                "StudyDate": ["20230101", "20230102", "20230103"],
                "StudyInstanceUID": ["1.2.3.4", "1.2.3.5", "1.2.3.6"],
            }
        )
        self._mock_setup(monkeypatch, mock_df)

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
                        "source": "subject",
                        "map": {
                            "sub01": "3T",
                            "sub02": "3T",
                        },
                        # 'constant' used as alias for catch-all default (no 'default' key)
                        "constant": "7T",
                    },
                },
            }
        ]

        result_df = query_dicoms(search_specs)

        assert len(result_df) == 3
        assert list(result_df["subject"]) == ["sub01", "sub02", "sub03"]
        assert list(result_df["session"]) == ["3T", "3T", "7T"]

    def test_map_default_null_drops_unmapped(self, monkeypatch):
        """default: null sets unmapped rows to NaN."""
        mock_df = pd.DataFrame(
            {
                "PatientID": ["sub01", "sub02", "sub03"],
                "StudyDate": ["20230101", "20230102", "20230103"],
                "StudyInstanceUID": ["1.2.3.4", "1.2.3.5", "1.2.3.6"],
            }
        )
        self._mock_setup(monkeypatch, mock_df)

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
                        "source": "subject",
                        "map": {
                            "sub01": "3T",
                        },
                        "default": None,
                    },
                },
            }
        ]

        result_df = query_dicoms(search_specs)

        assert len(result_df) == 3
        assert result_df.loc[result_df["subject"] == "sub01", "session"].iloc[0] == "3T"
        # Unmapped subjects should have NaN session
        assert result_df.loc[result_df["subject"] == "sub02", "session"].isna().all()
        assert result_df.loc[result_df["subject"] == "sub03", "session"].isna().all()

    def test_constant_alone_still_sets_all_rows(self, monkeypatch):
        """Backwards compat: 'constant' without 'map' still sets every row."""
        mock_df = pd.DataFrame(
            {
                "PatientID": ["sub01", "sub02", "sub03"],
                "StudyDate": ["20230101", "20230102", "20230103"],
                "StudyInstanceUID": ["1.2.3.4", "1.2.3.5", "1.2.3.6"],
            }
        )
        self._mock_setup(monkeypatch, mock_df)

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

        result_df = query_dicoms(search_specs)

        assert len(result_df) == 3
        assert all(result_df["session"] == "15T")
