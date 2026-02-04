"""Tests for the query_filter module."""

import pandas as pd
import pytest

from workflow.lib.query_filter import (
    post_filter,
    remap_session_globally,
)


class TestRemapSessionGlobally:
    """Tests for the remap_session_globally function."""

    def test_remap_all_sessions_to_single_value(self):
        """Test that all sessions are remapped to a single value."""
        df = pd.DataFrame(
            {
                "subject": ["sub-01", "sub-01", "sub-02", "sub-02"],
                "session": ["20230101", "20230601", "20230215", "20230815"],
            }
        )

        result = remap_session_globally(df, session_col="session", session_name="15T")

        # All sessions should be '15T'
        assert all(result["session"] == "15T")
        # Subject column should be unchanged
        assert list(result["subject"]) == ["sub-01", "sub-01", "sub-02", "sub-02"]

    def test_remap_with_default_session_name(self):
        """Test that default session name is '01'."""
        df = pd.DataFrame(
            {
                "subject": ["sub-01", "sub-02"],
                "session": ["A", "B"],
            }
        )

        result = remap_session_globally(df)

        assert all(result["session"] == "01")

    def test_remap_preserves_dataframe_structure(self):
        """Test that remapping preserves other columns and index."""
        df = pd.DataFrame(
            {
                "subject": ["sub-01", "sub-02"],
                "session": ["A", "B"],
                "extra_col": ["data1", "data2"],
            },
            index=[10, 20],
        )

        result = remap_session_globally(df, session_name="MRI")

        # Check index is preserved
        assert list(result.index) == [10, 20]
        # Check other columns are preserved
        assert list(result["subject"]) == ["sub-01", "sub-02"]
        assert list(result["extra_col"]) == ["data1", "data2"]
        # Check session is remapped
        assert all(result["session"] == "MRI")

    def test_remap_with_custom_session_column(self):
        """Test remapping with a custom session column name."""
        df = pd.DataFrame(
            {
                "subject": ["sub-01", "sub-02"],
                "ses": ["A", "B"],
            }
        )

        result = remap_session_globally(df, session_col="ses", session_name="01")

        assert all(result["ses"] == "01")


class TestPostFilterWithGlobalRemap:
    """Tests for post_filter function with global session remapping."""

    def test_global_remap_when_enabled(self):
        """Test that global remapping is applied when enabled."""
        df = pd.DataFrame(
            {
                "subject": ["sub-01", "sub-01", "sub-02"],
                "session": ["A", "B", "C"],
            }
        )

        post_filter_specs = {
            "remap_session_globally": {
                "enable": True,
                "session_name": "15T",
            }
        }

        result = post_filter(df, post_filter_specs)

        assert all(result["session"] == "15T")

    def test_global_remap_when_disabled(self):
        """Test that global remapping is not applied when disabled."""
        df = pd.DataFrame(
            {
                "subject": ["sub-01", "sub-02"],
                "session": ["A", "B"],
            }
        )

        post_filter_specs = {
            "remap_session_globally": {
                "enable": False,
                "session_name": "15T",
            }
        }

        result = post_filter(df, post_filter_specs)

        # Sessions should be unchanged
        assert list(result["session"]) == ["A", "B"]

    def test_global_remap_with_include_exclude(self):
        """Test that global remapping works with include/exclude filters."""
        df = pd.DataFrame(
            {
                "subject": ["sub-01", "sub-02", "sub-03"],
                "session": ["A", "B", "C"],
            }
        )

        post_filter_specs = {
            "include": ["subject.str.startswith('sub-0')"],
            "exclude": ["subject == 'sub-03'"],
            "remap_session_globally": {
                "enable": True,
                "session_name": "MRI",
            },
        }

        result = post_filter(df, post_filter_specs)

        # Only sub-01 and sub-02 should remain (sub-03 excluded)
        assert len(result) == 2
        assert list(result["subject"]) == ["sub-01", "sub-02"]
        # All remaining sessions should be 'MRI'
        assert all(result["session"] == "MRI")

    def test_no_remap_when_config_missing(self):
        """Test that no remapping occurs when config is missing."""
        df = pd.DataFrame(
            {
                "subject": ["sub-01", "sub-02"],
                "session": ["A", "B"],
            }
        )

        post_filter_specs = {}

        result = post_filter(df, post_filter_specs)

        # Sessions should be unchanged
        assert list(result["session"]) == ["A", "B"]

    def test_global_remap_applied_before_date_remap(self):
        """Test that global remapping is applied before date-based remapping.

        Note: In practice, these two options should not be used together since
        global remapping sets all sessions to the same value, making date-based
        remapping meaningless. This test verifies the order of operations but
        expects an error when trying to parse the globally remapped value as a date.
        """
        df = pd.DataFrame(
            {
                "subject": ["sub-01", "sub-01"],
                "session": ["20230101", "20230601"],
            }
        )

        # Enable both global and date-based remapping
        # Global remap should be applied first
        post_filter_specs = {
            "remap_session_globally": {
                "enable": True,
                "session_name": "15T",
            },
            "remap_sessions_by_date": {
                "enable": True,
                "session_format": "%Y%m%d",
            },
        }

        # This should raise an error because '15T' cannot be parsed as a date
        with pytest.raises((ValueError, TypeError)):
            post_filter(df, post_filter_specs)

    def test_exclude_post_remap_still_works(self):
        """Test that exclude_post_remap still works with global remapping."""
        df = pd.DataFrame(
            {
                "subject": ["sub-01", "sub-02", "sub-03"],
                "session": ["A", "B", "C"],
                "modality": ["T1w", "T2w", "T1w"],
            }
        )

        post_filter_specs = {
            "remap_session_globally": {
                "enable": True,
                "session_name": "01",
            },
            "exclude_post_remap": ["modality == 'T2w'"],
        }

        result = post_filter(df, post_filter_specs)

        # sub-02 should be excluded (T2w modality)
        assert len(result) == 2
        assert list(result["subject"]) == ["sub-01", "sub-03"]
        # All remaining sessions should be '01'
        assert all(result["session"] == "01")
