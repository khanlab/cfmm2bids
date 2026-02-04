"""
Tests for custom_dwi_bruker heuristic module.

These tests verify the basic functionality of the bvec/bval extraction
functions without requiring actual DICOM files.
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest


def test_import_custom_dwi_bruker():
    """Test that the custom_dwi_bruker module can be imported."""
    from heuristics import custom_dwi_bruker

    assert hasattr(custom_dwi_bruker, "get_bvec_bval")
    assert hasattr(custom_dwi_bruker, "write_bvec_bval")
    assert hasattr(custom_dwi_bruker, "get_dicom_path_from_series")
    assert hasattr(custom_dwi_bruker, "process_dwi_bvec_bval")
    assert hasattr(custom_dwi_bruker, "AttachToSession")


def test_get_bvec_bval():
    """Test the dummy get_bvec_bval function."""
    from heuristics.custom_dwi_bruker import get_bvec_bval

    # Test with a dummy path (function doesn't actually read the file)
    bvec, bval = get_bvec_bval("/dummy/path/to/dicom.dcm")

    # Check return types
    assert isinstance(bvec, np.ndarray)
    assert isinstance(bval, np.ndarray)

    # Check shapes
    assert bvec.ndim == 2
    assert bvec.shape[0] == 3  # Should have 3 rows (x, y, z)
    assert bval.ndim == 1
    assert bvec.shape[1] == bval.shape[0]  # Number of directions should match

    # Check that bvec vectors are normalized (or zero for b=0)
    for i in range(bvec.shape[1]):
        vec_norm = np.linalg.norm(bvec[:, i])
        # Each vector should be normalized (close to 1) or zero
        assert vec_norm < 1.001  # Allow small numerical errors


def test_write_bvec_bval():
    """Test writing bvec/bval files."""
    from heuristics.custom_dwi_bruker import write_bvec_bval

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test data
        n_directions = 10
        bvec = np.random.randn(3, n_directions)
        # Normalize each direction
        for i in range(n_directions):
            norm = np.linalg.norm(bvec[:, i])
            if norm > 0:
                bvec[:, i] /= norm

        bval = np.array([0] + [1000] * (n_directions - 1))

        # Write files
        basename = Path(tmpdir) / "test_dwi"
        write_bvec_bval(bvec, bval, basename)

        # Check files were created
        bvec_file = Path(tmpdir) / "test_dwi.bvec"
        bval_file = Path(tmpdir) / "test_dwi.bval"

        assert bvec_file.exists()
        assert bval_file.exists()

        # Read and verify bvec file
        with open(bvec_file) as f:
            bvec_lines = f.readlines()
        assert len(bvec_lines) == 3  # Should have 3 rows

        bvec_read = []
        for line in bvec_lines:
            values = [float(x) for x in line.strip().split()]
            assert len(values) == n_directions
            bvec_read.append(values)

        bvec_read = np.array(bvec_read)
        np.testing.assert_allclose(bvec_read, bvec, rtol=1e-4)

        # Read and verify bval file
        with open(bval_file) as f:
            bval_line = f.readline()

        bval_values = [int(x) for x in bval_line.strip().split()]
        assert len(bval_values) == n_directions
        np.testing.assert_array_equal(bval_values, bval)


def test_get_dicom_path_from_series():
    """Test the get_dicom_path_from_series function with mock seqinfo."""
    from heuristics.custom_dwi_bruker import get_dicom_path_from_series

    # Create mock seqinfo objects
    class MockSeqInfo:
        def __init__(self, series_id, dcm_file):
            self.series_id = series_id
            self.example_dcm_file = dcm_file

    seqinfo_list = [
        MockSeqInfo("001", "/path/to/dcm1.dcm"),
        MockSeqInfo("002", "/path/to/dcm2.dcm"),
        MockSeqInfo("003", "/path/to/dcm3.dcm"),
    ]

    # Test finding existing series
    result = get_dicom_path_from_series(seqinfo_list, "002")
    assert result == "/path/to/dcm2.dcm"

    # Test with string series ID
    result = get_dicom_path_from_series(seqinfo_list, "001")
    assert result == "/path/to/dcm1.dcm"

    # Test with non-existent series
    result = get_dicom_path_from_series(seqinfo_list, "999")
    assert result is None


def test_attach_to_session_callable():
    """Test that AttachToSession returns a callable."""
    from heuristics.custom_dwi_bruker import AttachToSession

    attach_func = AttachToSession()
    assert callable(attach_func)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
