"""Tests for query_filter module."""

import os
import time

import pandas as pd
import pytest

from workflow.lib.query_filter import (
    QUERY_CACHE_MAX_AGE_SECONDS,
    post_filter,
    query_dicoms,
    remap_sessions_by_date,
    remap_values,
    should_skip_query,
)


class TestShouldSkipQuery:
    """Tests for should_skip_query cache-skip logic."""

    def _write_files(self, tmp_path, hash_value="abc123"):
        tsv = tmp_path / "studies.tsv"
        hash_file = tmp_path / "query_hash.txt"
        tsv.write_text("col1\tcol2\n")
        hash_file.write_text(hash_value)
        return tsv, hash_file

    def test_skips_when_fresh_and_hash_matches(self, tmp_path):
        tsv, hash_file = self._write_files(tmp_path, "abc123")
        assert should_skip_query(tsv, hash_file, "abc123") is True

    def test_requery_when_hash_differs(self, tmp_path):
        tsv, hash_file = self._write_files(tmp_path, "abc123")
        assert should_skip_query(tsv, hash_file, "different_hash") is False

    def test_requery_when_tsv_missing(self, tmp_path):
        tsv = tmp_path / "studies.tsv"
        hash_file = tmp_path / "query_hash.txt"
        hash_file.write_text("abc123")
        assert should_skip_query(tsv, hash_file, "abc123") is False

    def test_requery_when_hash_file_missing(self, tmp_path):
        tsv = tmp_path / "studies.tsv"
        tsv.write_text("col1\n")
        hash_file = tmp_path / "query_hash.txt"
        assert should_skip_query(tsv, hash_file, "abc123") is False

    def test_requery_when_force_requery(self, tmp_path):
        tsv, hash_file = self._write_files(tmp_path, "abc123")
        assert should_skip_query(tsv, hash_file, "abc123", force_requery=True) is False

    def test_requery_when_tsv_older_than_one_day(self, tmp_path):
        tsv, hash_file = self._write_files(tmp_path, "abc123")
        # Set mtime to more than one day ago
        old_time = time.time() - QUERY_CACHE_MAX_AGE_SECONDS - 1
        os.utime(tsv, (old_time, old_time))
        assert should_skip_query(tsv, hash_file, "abc123") is False

    def test_skips_when_tsv_just_within_one_day(self, tmp_path):
        tsv, hash_file = self._write_files(tmp_path, "abc123")
        # Set mtime to just under one day ago (1 second under the limit)
        fresh_time = time.time() - QUERY_CACHE_MAX_AGE_SECONDS + 1
        os.utime(tsv, (fresh_time, fresh_time))
        assert should_skip_query(tsv, hash_file, "abc123") is True


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


class TestRemapSessionsByDateRoundStep:
    """Tests for remap_sessions_by_date with scalar and list round_step."""

    def _make_df(self, subjects, sessions):
        return pd.DataFrame({"subject": subjects, "session": sessions})

    def test_scalar_round_step_evenly_spaced(self):
        """Scalar round_step snaps to nearest multiple (existing behaviour)."""
        df = self._make_df(
            ["sub01", "sub01", "sub01"],
            ["20200101", "20200701", "20210101"],
        )
        result = remap_sessions_by_date(df, round_step=6)
        sessions = list(result["session"])
        assert sessions[0] == "0m"
        assert sessions[1] == "6m"
        assert sessions[2] == "12m"

    def test_list_round_step_equally_spaced(self):
        """List round_step with equal spacing matches scalar behaviour."""
        df = self._make_df(
            ["sub01", "sub01", "sub01"],
            ["20200101", "20200701", "20210101"],
        )
        result_scalar = remap_sessions_by_date(df, round_step=6)
        result_list = remap_sessions_by_date(df, round_step=[0, 6, 12, 18])
        assert list(result_scalar["session"]) == list(result_list["session"])

    def test_list_round_step_unequal_spacing(self):
        """List round_step correctly snaps to nearest unequally-spaced breakpoint."""
        # Sessions at 0, ~3, ~6, ~10 months
        df = self._make_df(
            ["sub01", "sub01", "sub01", "sub01"],
            ["20200101", "20200401", "20200701", "20201101"],
        )
        result = remap_sessions_by_date(df, round_step=[0, 3, 6, 10])
        sessions = list(result["session"])
        assert sessions[0] == "0m"
        assert sessions[1] == "3m"
        assert sessions[2] == "6m"
        assert sessions[3] == "10m"

    def test_list_round_step_midpoint_snaps_to_nearest(self):
        """A value exactly between two breakpoints snaps to the nearest one."""
        # ~4.5 months since baseline – equidistant between 3 and 6, numpy picks lower index
        df = self._make_df(
            ["sub01", "sub01"],
            ["20200101", "20200615"],
        )
        result = remap_sessions_by_date(df, round_step=[0, 3, 6, 10])
        # ~5.5 months → closer to 6
        assert result["session"].iloc[1] == "6m"

    def test_list_round_step_custom_time_to_label(self):
        """Custom time_to_label still works when list round_step is used."""
        df = self._make_df(
            ["sub01", "sub01", "sub01"],
            ["20200101", "20200401", "20200701"],
        )
        result = remap_sessions_by_date(
            df,
            round_step=[0, 3, 6],
            time_to_label={0: "baseline", 3: "3mo", 6: "6mo"},
        )
        sessions = list(result["session"])
        assert sessions[0] == "baseline"
        assert sessions[1] == "3mo"
        assert sessions[2] == "6mo"

    def test_list_round_step_single_subject_multiple_sessions(self):
        """List round_step handles multiple sessions for one subject correctly."""
        df = self._make_df(
            ["sub01"] * 4,
            ["20200101", "20200401", "20200701", "20201101"],
        )
        result = remap_sessions_by_date(df, round_step=[0, 3, 6, 10])
        assert list(result["session"]) == ["0m", "3m", "6m", "10m"]

    def test_list_round_step_multiple_subjects(self):
        """List round_step handles multiple subjects independently."""
        df = self._make_df(
            ["sub01", "sub01", "sub02", "sub02"],
            ["20200101", "20201101", "20190601", "20191201"],
        )
        result = remap_sessions_by_date(df, round_step=[0, 6])
        # Each subject starts at 0; second session ~10 months → snaps to 6
        for _, grp in result.groupby("subject"):
            sessions = list(grp["session"])
            assert sessions[0] == "0m"
            assert sessions[1] == "6m"

    @pytest.mark.parametrize("step_input", [[0, 6], (0, 6)])
    def test_list_or_tuple_accepted(self, step_input):
        """Both list and tuple are accepted as round_step."""
        df = self._make_df(["sub01", "sub01"], ["20200101", "20200701"])
        result = remap_sessions_by_date(df, round_step=step_input)
        assert list(result["session"]) == ["0m", "6m"]


class TestRemapValues:
    """Tests for remap_values: manual column-value overrides."""

    def _make_df(self, subjects, sessions):
        return pd.DataFrame({"subject": subjects, "session": sessions})

    def test_remap_single_row_by_subject_query(self):
        """Remap the session for a single subject matched by query."""
        df = self._make_df(["sub01", "sub02", "sub03"], ["6m", "3m", "6m"])
        result = remap_values(
            df, [{"query": "subject == 'sub02'", "column": "session", "value": "6m"}]
        )
        assert list(result["session"]) == ["6m", "6m", "6m"]

    def test_remap_multiple_specs(self):
        """Multiple remap_values specs are applied in order."""
        df = self._make_df(["sub01", "sub02"], ["wrong1", "wrong2"])
        specs = [
            {"query": "subject == 'sub01'", "column": "session", "value": "0m"},
            {"query": "subject == 'sub02'", "column": "session", "value": "6m"},
        ]
        result = remap_values(df, specs)
        assert list(result["session"]) == ["0m", "6m"]

    def test_remap_non_session_column(self):
        """remap_values works on columns other than 'session'."""
        df = pd.DataFrame(
            {
                "subject": ["sub01", "sub02"],
                "session": ["0m", "6m"],
                "group": ["A", "A"],
            }
        )
        result = remap_values(
            df, [{"query": "subject == 'sub02'", "column": "group", "value": "B"}]
        )
        assert list(result["group"]) == ["A", "B"]

    def test_remap_with_no_matching_rows(self):
        """A query that matches no rows leaves the dataframe unchanged."""
        df = self._make_df(["sub01", "sub02"], ["0m", "6m"])
        result = remap_values(
            df, [{"query": "subject == 'sub99'", "column": "session", "value": "12m"}]
        )
        assert list(result["session"]) == ["0m", "6m"]

    def test_remap_invalid_column_raises(self):
        """Referencing a non-existent column raises ValueError."""
        df = self._make_df(["sub01"], ["0m"])
        with pytest.raises(ValueError, match="column 'nonexistent'"):
            remap_values(
                df,
                [
                    {
                        "query": "subject == 'sub01'",
                        "column": "nonexistent",
                        "value": "x",
                    }
                ],
            )

    def test_remap_invalid_query_raises(self):
        """An invalid query string raises ValueError."""
        df = self._make_df(["sub01"], ["0m"])
        with pytest.raises(ValueError, match="invalid query"):
            remap_values(
                df,
                [
                    {
                        "query": "this is not valid @@@ python",
                        "column": "session",
                        "value": "x",
                    }
                ],
            )

    def test_original_df_not_mutated(self):
        """remap_values does not mutate the input DataFrame."""
        df = self._make_df(["sub01"], ["0m"])
        original_session = df["session"].iloc[0]
        remap_values(
            df, [{"query": "subject == 'sub01'", "column": "session", "value": "6m"}]
        )
        assert df["session"].iloc[0] == original_session


class TestPostFilterRemapValues:
    """Integration tests for remap_values inside post_filter."""

    def _make_df(self, subjects, sessions):
        return pd.DataFrame({"subject": subjects, "session": sessions})

    def test_remap_values_applied_after_remap_sessions_by_date(self):
        """remap_values runs after remap_sessions_by_date, allowing manual correction."""
        df = self._make_df(
            ["sub01", "sub01", "sub02"],
            ["20200101", "20200701", "20200101"],
        )
        post_filter_specs = {
            "remap_sessions_by_date": {
                "enable": True,
                "units": "months",
                "round_step": 6,
            },
            "remap_values": [
                # sub02 was incorrectly mapped to 0m; override to 6m
                {"query": "subject == 'sub02'", "column": "session", "value": "6m"}
            ],
        }
        result = post_filter(df, post_filter_specs)
        sub01 = result[result["subject"] == "sub01"]["session"].tolist()
        sub02 = result[result["subject"] == "sub02"]["session"].tolist()
        assert sub01 == ["0m", "6m"]
        assert sub02 == ["6m"]

    def test_remap_values_without_remap_sessions_by_date(self):
        """remap_values works standalone without remap_sessions_by_date."""
        df = self._make_df(["sub01", "sub02"], ["wrong", "ok"])
        post_filter_specs = {
            "remap_values": [
                {
                    "query": "subject == 'sub01'",
                    "column": "session",
                    "value": "corrected",
                }
            ]
        }
        result = post_filter(df, post_filter_specs)
        assert list(result["session"]) == ["corrected", "ok"]

    def test_no_remap_values_key_leaves_df_unchanged(self):
        """Omitting remap_values from specs leaves the DataFrame unchanged."""
        df = self._make_df(["sub01"], ["0m"])
        result = post_filter(df, {"include": [], "exclude": []})
        assert list(result["session"]) == ["0m"]
