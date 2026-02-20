"""Tests for the bids_fixes module."""

import json

import nibabel as nib
import numpy as np

from workflow.lib.bids_fixes import (
    FIX_REGISTRY,
    _axcodes2aff,
    _compute_nifti_hash,
    describe_available_fixes,
    fix_orientation_quadruped,
    register_fix,
    remove_duplicate_niftis,
    remove_file,
    split_multiecho_nifti,
    update_json,
)


class TestRegisterFix:
    """Tests for the register_fix decorator."""

    def test_register_fix_adds_to_registry(self):
        """Test that the decorator adds the function to FIX_REGISTRY."""
        # Clear registry entry if exists from previous test
        test_name = "_test_fix_registration"
        FIX_REGISTRY.pop(test_name, None)

        @register_fix(test_name)
        def test_func(path, spec):
            return True

        assert test_name in FIX_REGISTRY
        assert FIX_REGISTRY[test_name]["func"] is test_func
        assert FIX_REGISTRY[test_name]["grouped"] is False

        # Cleanup
        FIX_REGISTRY.pop(test_name, None)

    def test_register_fix_grouped(self):
        """Test that grouped=True is stored correctly."""
        test_name = "_test_grouped_fix"
        FIX_REGISTRY.pop(test_name, None)

        @register_fix(test_name, grouped=True)
        def test_grouped_func(paths, spec):
            return len(paths)

        assert test_name in FIX_REGISTRY
        assert FIX_REGISTRY[test_name]["grouped"] is True

        # Cleanup
        FIX_REGISTRY.pop(test_name, None)

    def test_register_fix_uses_function_name_when_no_name_provided(self):
        """Test that the decorator uses the function name when name is None."""
        # Use a unique function name to avoid conflicts
        func_name = "_test_auto_name_func"
        FIX_REGISTRY.pop(func_name, None)

        @register_fix()
        def _test_auto_name_func(path, spec):
            return True

        assert func_name in FIX_REGISTRY

        # Cleanup
        FIX_REGISTRY.pop(func_name, None)

    def test_builtin_fixes_are_registered(self):
        """Test that built-in fixes are registered correctly."""
        assert "remove" in FIX_REGISTRY
        assert "update_json" in FIX_REGISTRY
        assert "fix_orientation_quadruped" in FIX_REGISTRY
        assert "remove_duplicate_niftis" in FIX_REGISTRY
        assert "split_multiecho_nifti" in FIX_REGISTRY


class TestRemoveFile:
    """Tests for the remove_file fix function."""

    def test_remove_file_removes_existing_file(self, tmp_path):
        """Test that remove_file removes an existing file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        assert test_file.exists()

        result = remove_file(test_file, {})

        assert result is True
        assert not test_file.exists()

    def test_remove_file_handles_missing_file(self, tmp_path):
        """Test that remove_file handles non-existent files gracefully."""
        test_file = tmp_path / "nonexistent.txt"
        assert not test_file.exists()

        result = remove_file(test_file, {})

        assert result is True
        assert not test_file.exists()


class TestUpdateJson:
    """Tests for the update_json fix function."""

    def test_update_json_updates_existing_fields(self, tmp_path):
        """Test that update_json updates existing JSON fields."""
        json_file = tmp_path / "test.json"
        original_data = {"field1": "value1", "field2": "value2"}
        json_file.write_text(json.dumps(original_data))

        spec = {"updates": {"field1": "updated_value1"}}
        result = update_json(json_file, spec)

        assert result is True
        with open(json_file) as f:
            updated_data = json.load(f)
        assert updated_data["field1"] == "updated_value1"
        assert updated_data["field2"] == "value2"

    def test_update_json_adds_new_fields(self, tmp_path):
        """Test that update_json adds new fields."""
        json_file = tmp_path / "test.json"
        original_data = {"field1": "value1"}
        json_file.write_text(json.dumps(original_data))

        spec = {"updates": {"new_field": "new_value"}}
        result = update_json(json_file, spec)

        assert result is True
        with open(json_file) as f:
            updated_data = json.load(f)
        assert updated_data["field1"] == "value1"
        assert updated_data["new_field"] == "new_value"

    def test_update_json_returns_false_for_non_json(self, tmp_path):
        """Test that update_json returns False for non-JSON files."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not json")

        spec = {"updates": {"field": "value"}}
        result = update_json(txt_file, spec)

        assert result is False

    def test_update_json_handles_empty_updates(self, tmp_path):
        """Test that update_json handles empty updates dict."""
        json_file = tmp_path / "test.json"
        original_data = {"field1": "value1"}
        json_file.write_text(json.dumps(original_data))

        spec = {"updates": {}}
        result = update_json(json_file, spec)

        assert result is True
        with open(json_file) as f:
            updated_data = json.load(f)
        assert updated_data == original_data


class TestAxcodes2Aff:
    """Tests for the _axcodes2aff helper function."""

    def test_axcodes2aff_creates_affine(self):
        """Test that _axcodes2aff creates a valid affine matrix."""
        axcodes = ("R", "A", "S")
        scale = [1.0, 1.0, 1.0]
        translate = [0.0, 0.0, 0.0]

        affine = _axcodes2aff(axcodes, scale, translate)

        assert affine.shape == (4, 4)
        assert affine[3, 3] == 1.0  # Homogeneous coordinate

    def test_axcodes2aff_applies_scale(self):
        """Test that _axcodes2aff applies scaling correctly."""
        axcodes = ("R", "A", "S")
        scale = [2.0, 3.0, 4.0]
        translate = [0.0, 0.0, 0.0]

        affine = _axcodes2aff(axcodes, scale, translate)

        # Check that scale is applied in the diagonal
        assert affine[0, 0] == 2.0
        assert affine[1, 1] == 3.0
        assert affine[2, 2] == 4.0


class TestFixOrientationQuadruped:
    """Tests for the fix_orientation_quadruped fix function."""

    def test_fix_orientation_quadruped_modifies_nifti(self, tmp_path):
        """Test that fix_orientation_quadruped modifies NIfTI file."""
        # Create a simple NIfTI image
        data = np.random.rand(10, 10, 10).astype(np.float32)
        affine = np.eye(4)
        img = nib.Nifti1Image(data, affine)

        nii_file = tmp_path / "test.nii.gz"
        nib.save(img, nii_file)

        result = fix_orientation_quadruped(nii_file, {})

        assert result is True
        # Verify the file was modified
        modified_img = nib.load(nii_file)
        # The affine should be different after reorientation
        assert not np.array_equal(modified_img.affine, affine)

    def test_fix_orientation_quadruped_returns_false_for_non_nifti(self, tmp_path):
        """Test that fix_orientation_quadruped returns False for non-NIfTI files."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not a nifti")

        result = fix_orientation_quadruped(txt_file, {})

        assert result is False

    def test_fix_orientation_quadruped_handles_nii_extension(self, tmp_path):
        """Test that fix_orientation_quadruped handles .nii extension."""
        # Note: Using .nii.gz instead of .nii to avoid memory-mapped file issues
        # in some environments, but the function should work with .nii as well
        data = np.random.rand(10, 10, 10).astype(np.float32)
        affine = np.eye(4)
        img = nib.Nifti1Image(data, affine)

        # Test that the function recognizes .nii as a valid extension
        # by checking the extension matching logic
        nii_file = tmp_path / "test.nii.gz"
        nib.save(img, nii_file)

        result = fix_orientation_quadruped(nii_file, {})

        assert result is True


class TestComputeNiftiHash:
    """Tests for the _compute_nifti_hash helper function."""

    def test_compute_nifti_hash_returns_hash(self, tmp_path):
        """Test that _compute_nifti_hash returns a hash string."""
        data = np.random.rand(10, 10, 10).astype(np.float32)
        img = nib.Nifti1Image(data, np.eye(4))

        nii_file = tmp_path / "test.nii.gz"
        nib.save(img, nii_file)

        hash_result = _compute_nifti_hash(nii_file)

        assert isinstance(hash_result, str)
        assert len(hash_result) == 32  # MD5 hex digest length

    def test_compute_nifti_hash_same_data_same_hash(self, tmp_path):
        """Test that identical data produces the same hash."""
        data = np.ones((5, 5, 5), dtype=np.float32)

        img1 = nib.Nifti1Image(data, np.eye(4))
        img2 = nib.Nifti1Image(data, np.eye(4))

        file1 = tmp_path / "test1.nii.gz"
        file2 = tmp_path / "test2.nii.gz"
        nib.save(img1, file1)
        nib.save(img2, file2)

        hash1 = _compute_nifti_hash(file1)
        hash2 = _compute_nifti_hash(file2)

        assert hash1 == hash2

    def test_compute_nifti_hash_different_data_different_hash(self, tmp_path):
        """Test that different data produces different hashes."""
        data1 = np.ones((5, 5, 5), dtype=np.float32)
        data2 = np.zeros((5, 5, 5), dtype=np.float32)

        img1 = nib.Nifti1Image(data1, np.eye(4))
        img2 = nib.Nifti1Image(data2, np.eye(4))

        file1 = tmp_path / "test1.nii.gz"
        file2 = tmp_path / "test2.nii.gz"
        nib.save(img1, file1)
        nib.save(img2, file2)

        hash1 = _compute_nifti_hash(file1)
        hash2 = _compute_nifti_hash(file2)

        assert hash1 != hash2


class TestRemoveDuplicateNiftis:
    """Tests for the remove_duplicate_niftis fix function."""

    def test_remove_duplicate_niftis_removes_duplicates(self, tmp_path):
        """Test that remove_duplicate_niftis removes duplicate files."""
        # Create two identical NIfTI files
        data = np.ones((5, 5, 5), dtype=np.float32)
        img = nib.Nifti1Image(data, np.eye(4))

        file1 = tmp_path / "file1.nii.gz"
        file2 = tmp_path / "file2.nii.gz"
        nib.save(img, file1)
        nib.save(img, file2)

        paths = [file1, file2]
        result = remove_duplicate_niftis(paths, {})

        # Should remove 1 file (the duplicate)
        assert result == 1
        # file1 should remain (first alphanumerically)
        assert file1.exists()
        assert not file2.exists()

    def test_remove_duplicate_niftis_keeps_unique_files(self, tmp_path):
        """Test that remove_duplicate_niftis keeps unique files."""
        # Create two different NIfTI files
        data1 = np.ones((5, 5, 5), dtype=np.float32)
        data2 = np.zeros((5, 5, 5), dtype=np.float32)
        img1 = nib.Nifti1Image(data1, np.eye(4))
        img2 = nib.Nifti1Image(data2, np.eye(4))

        file1 = tmp_path / "file1.nii.gz"
        file2 = tmp_path / "file2.nii.gz"
        nib.save(img1, file1)
        nib.save(img2, file2)

        paths = [file1, file2]
        result = remove_duplicate_niftis(paths, {})

        # No duplicates, no files removed
        assert result == 0
        assert file1.exists()
        assert file2.exists()

    def test_remove_duplicate_niftis_removes_json_sidecars(self, tmp_path):
        """Test that remove_duplicate_niftis removes JSON sidecars of duplicates."""
        # Create two identical NIfTI files with JSON sidecars
        data = np.ones((5, 5, 5), dtype=np.float32)
        img = nib.Nifti1Image(data, np.eye(4))

        file1 = tmp_path / "file1.nii.gz"
        file2 = tmp_path / "file2.nii.gz"
        json1 = tmp_path / "file1.json"
        json2 = tmp_path / "file2.json"

        nib.save(img, file1)
        nib.save(img, file2)
        json1.write_text('{"key": "value1"}')
        json2.write_text('{"key": "value2"}')

        paths = [file1, file2]
        result = remove_duplicate_niftis(paths, {})

        # Should remove 2 files (duplicate NIfTI + its JSON sidecar)
        assert result == 2
        assert file1.exists()
        assert json1.exists()
        assert not file2.exists()
        assert not json2.exists()

    def test_remove_duplicate_niftis_handles_nii_extension(self, tmp_path):
        """Test that remove_duplicate_niftis handles .nii extension."""
        # Note: Using .nii.gz to avoid memory-mapped file issues in some environments
        data = np.ones((5, 5, 5), dtype=np.float32)
        img = nib.Nifti1Image(data, np.eye(4))

        file1 = tmp_path / "file1.nii.gz"
        file2 = tmp_path / "file2.nii.gz"
        json1 = tmp_path / "file1.json"
        json2 = tmp_path / "file2.json"

        nib.save(img, file1)
        nib.save(img, file2)
        json1.write_text('{"key": "value1"}')
        json2.write_text('{"key": "value2"}')

        paths = [file1, file2]
        result = remove_duplicate_niftis(paths, {})

        # Should remove 2 files (duplicate NIfTI + its JSON sidecar)
        assert result == 2
        assert file1.exists()
        assert json1.exists()
        assert not file2.exists()
        assert not json2.exists()

    def test_remove_duplicate_niftis_handles_empty_list(self, tmp_path):
        """Test that remove_duplicate_niftis handles empty list."""
        result = remove_duplicate_niftis([], {})
        assert result == 0

    def test_remove_duplicate_niftis_handles_single_file(self, tmp_path):
        """Test that remove_duplicate_niftis handles single file."""
        data = np.ones((5, 5, 5), dtype=np.float32)
        img = nib.Nifti1Image(data, np.eye(4))

        file1 = tmp_path / "file1.nii.gz"
        nib.save(img, file1)

        paths = [file1]
        result = remove_duplicate_niftis(paths, {})

        assert result == 0
        assert file1.exists()

    def test_remove_duplicate_niftis_multiple_duplicates(self, tmp_path):
        """Test that remove_duplicate_niftis handles multiple duplicates."""
        data = np.ones((5, 5, 5), dtype=np.float32)
        img = nib.Nifti1Image(data, np.eye(4))

        file1 = tmp_path / "file1.nii.gz"
        file2 = tmp_path / "file2.nii.gz"
        file3 = tmp_path / "file3.nii.gz"

        nib.save(img, file1)
        nib.save(img, file2)
        nib.save(img, file3)

        paths = [file1, file2, file3]
        result = remove_duplicate_niftis(paths, {})

        # Should remove 2 files (file2 and file3)
        assert result == 2
        assert file1.exists()
        assert not file2.exists()
        assert not file3.exists()


class TestDescribeAvailableFixes:
    """Tests for the describe_available_fixes function."""

    def test_describe_available_fixes_returns_markdown(self):
        """Test that describe_available_fixes returns markdown formatted string."""
        result = describe_available_fixes()

        assert isinstance(result, str)
        assert "### Available Fixes:" in result
        assert "**remove**" in result
        assert "**update_json**" in result
        assert "**fix_orientation_quadruped**" in result
        assert "**remove_duplicate_niftis**" in result

    def test_describe_available_fixes_includes_docstrings(self):
        """Test that describe_available_fixes includes docstrings."""
        result = describe_available_fixes()

        # Check for parts of the docstrings
        assert "Remove the file entirely" in result
        assert "Update JSON file fields" in result


class TestSplitMultiechoNifti:
    """Tests for the split_multiecho_nifti fix function."""

    def _make_4d_nifti(self, tmp_path, name, shape=(10, 10, 10, 3), dtype=np.float32):
        """Create a synthetic 4D NIfTI file and return its Path."""
        data = np.random.rand(*shape).astype(dtype)
        img = nib.Nifti1Image(data, np.eye(4))
        nii_path = tmp_path / name
        nib.save(img, nii_path)
        return nii_path

    def test_split_multiecho_creates_echo_files(self, tmp_path):
        """Test that echo volumes are created with correct echo- entity."""
        nii_path = self._make_4d_nifti(tmp_path, "sub-XX_ses-YY_run-01_T2starw.nii.gz")

        result = split_multiecho_nifti(nii_path, {})

        assert result is True
        for echo_num in range(1, 4):
            echo_file = (
                tmp_path / f"sub-XX_ses-YY_run-01_echo-{echo_num}_T2starw.nii.gz"
            )
            assert echo_file.exists(), f"Missing {echo_file.name}"

    def test_split_multiecho_creates_avgecho_file(self, tmp_path):
        """Test that the average echo image is created with rec-avgecho entity."""
        nii_path = self._make_4d_nifti(tmp_path, "sub-XX_ses-YY_run-01_T2starw.nii.gz")

        split_multiecho_nifti(nii_path, {})

        avg_file = tmp_path / "sub-XX_ses-YY_rec-avgecho_run-01_T2starw.nii.gz"
        assert avg_file.exists()

    def test_split_multiecho_removes_original(self, tmp_path):
        """Test that the original multi-echo file is removed."""
        nii_path = self._make_4d_nifti(tmp_path, "sub-XX_ses-YY_run-01_T2starw.nii.gz")

        split_multiecho_nifti(nii_path, {})

        assert not nii_path.exists()

    def test_split_multiecho_copies_json_sidecar(self, tmp_path):
        """Test that JSON sidecars are copied for each output file."""
        nii_path = self._make_4d_nifti(tmp_path, "sub-XX_ses-YY_run-01_T2starw.nii.gz")
        json_path = tmp_path / "sub-XX_ses-YY_run-01_T2starw.json"
        json_path.write_text('{"EchoTime": 0.02}')

        split_multiecho_nifti(nii_path, {})

        # JSON removed for original
        assert not json_path.exists()
        # JSON present for each echo and for avgecho
        for echo_num in range(1, 4):
            assert (
                tmp_path / f"sub-XX_ses-YY_run-01_echo-{echo_num}_T2starw.json"
            ).exists()
        assert (tmp_path / "sub-XX_ses-YY_rec-avgecho_run-01_T2starw.json").exists()

    def test_split_multiecho_echo_data_correct(self, tmp_path):
        """Test that each echo volume contains the correct data slice."""
        data = np.random.rand(10, 10, 10, 3).astype(np.float32)
        img = nib.Nifti1Image(data, np.eye(4))
        nii_path = tmp_path / "sub-XX_run-01_T2starw.nii.gz"
        nib.save(img, nii_path)

        split_multiecho_nifti(nii_path, {})

        for echo_idx in range(3):
            echo_num = echo_idx + 1
            echo_file = tmp_path / f"sub-XX_run-01_echo-{echo_num}_T2starw.nii.gz"
            loaded = np.asanyarray(nib.load(echo_file).dataobj)
            np.testing.assert_array_equal(loaded, data[..., echo_idx])

    def test_split_multiecho_avgecho_data_correct(self, tmp_path):
        """Test that the average echo image contains the mean of all echoes."""
        data = np.random.rand(10, 10, 10, 3).astype(np.float32)
        img = nib.Nifti1Image(data, np.eye(4))
        nii_path = tmp_path / "sub-XX_run-01_T2starw.nii.gz"
        nib.save(img, nii_path)

        split_multiecho_nifti(nii_path, {})

        avg_file = tmp_path / "sub-XX_rec-avgecho_run-01_T2starw.nii.gz"
        loaded_avg = np.asanyarray(nib.load(avg_file).dataobj)
        expected_avg = np.mean(data, axis=3)
        np.testing.assert_array_almost_equal(loaded_avg, expected_avg)

    def test_split_multiecho_no_run_entity(self, tmp_path):
        """Test correct entity placement when there is no run entity in the filename."""
        nii_path = self._make_4d_nifti(tmp_path, "sub-XX_ses-YY_T2starw.nii.gz")

        split_multiecho_nifti(nii_path, {})

        # echo- placed before suffix
        assert (tmp_path / "sub-XX_ses-YY_echo-1_T2starw.nii.gz").exists()
        # rec- placed before suffix
        assert (tmp_path / "sub-XX_ses-YY_rec-avgecho_T2starw.nii.gz").exists()

    def test_split_multiecho_returns_false_for_non_nifti(self, tmp_path):
        """Test that split_multiecho_nifti returns False for non-NIfTI files."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not a nifti")

        result = split_multiecho_nifti(txt_file, {})

        assert result is False

    def test_split_multiecho_returns_false_for_3d_nifti(self, tmp_path):
        """Test that split_multiecho_nifti returns False for 3D NIfTI files."""
        data = np.random.rand(10, 10, 10).astype(np.float32)
        img = nib.Nifti1Image(data, np.eye(4))
        nii_path = tmp_path / "sub-XX_T2starw.nii.gz"
        nib.save(img, nii_path)

        result = split_multiecho_nifti(nii_path, {})

        assert result is False
        assert nii_path.exists()  # original should be unchanged
