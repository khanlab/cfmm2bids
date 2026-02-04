"""
Custom heuristic for extracting bvec/bval from Bruker DWI DICOM files.

This module provides functions to extract diffusion gradient information
from DICOM files and write them as BIDS-compliant bvec/bval files.

Can be used standalone or imported into other heuristics (e.g., trident_15T.py).
"""

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def get_dicom_path_from_series(seqinfo_list, series_id):
    """
    Get the DICOM file path for a given series ID from seqinfo list.

    Parameters
    ----------
    seqinfo_list : list
        List of seqinfo objects from heudiconv
    series_id : str or int
        The series ID to find

    Returns
    -------
    str or None
        Path to the example DICOM file, or None if not found
    """
    for seq in seqinfo_list:
        if str(seq.series_id) == str(series_id):
            if hasattr(seq, "example_dcm_file"):
                return seq.example_dcm_file
    return None


def get_bvec_bval(in_dcm_path):
    """
    Extract bvec and bval from DICOM file.

    This is a dummy implementation. The actual extraction logic
    should be inserted here based on the specific DICOM tags
    used by Bruker scanners.

    Parameters
    ----------
    in_dcm_path : str or Path
        Path to the DICOM file

    Returns
    -------
    tuple
        (bvec, bval) where:
        - bvec: numpy array of shape (3, n_directions)
        - bval: numpy array of shape (n_directions,)
    """
    # Dummy implementation - returns example data
    # TODO: Replace with actual DICOM tag extraction using pydicom
    logger.info(f"Extracting bvec/bval from DICOM: {in_dcm_path}")

    # Example dummy data for a simple DWI acquisition
    # Real implementation would use pydicom to read DICOM tags
    n_directions = 64  # Example: 64 gradient directions

    # Dummy bvec: 3 x n_directions (normalized gradient directions)
    dummy_bvec = np.random.randn(3, n_directions)
    # Normalize each direction
    for i in range(n_directions):
        norm = np.linalg.norm(dummy_bvec[:, i])
        if norm > 0:
            dummy_bvec[:, i] /= norm

    # Dummy bval: n_directions (b-values in s/mm^2)
    dummy_bval = np.array([0] + [1000] * (n_directions - 1))

    logger.info(f"Extracted {n_directions} gradient directions")
    return dummy_bvec, dummy_bval


def write_bvec_bval(bvec, bval, output_basename):
    """
    Write bvec and bval arrays to BIDS-format files.

    BIDS format:
    - bvec: 3 rows (x, y, z), space-separated values
    - bval: 1 row, space-separated values

    Parameters
    ----------
    bvec : numpy.ndarray
        Array of shape (3, n_directions) with gradient directions
    bval : numpy.ndarray
        Array of shape (n_directions,) with b-values
    output_basename : str or Path
        Base path for output files (without extension)
        Will create {basename}.bvec and {basename}.bval
    """
    output_basename = Path(output_basename)

    # Write bvec file (3 rows, space-separated)
    bvec_file = output_basename.with_suffix(".bvec")
    with open(bvec_file, "w") as f:
        for row in range(3):
            row_values = " ".join(f"{val:.6f}" for val in bvec[row, :])
            f.write(row_values + "\n")
    logger.info(f"Wrote bvec file: {bvec_file}")

    # Write bval file (1 row, space-separated)
    bval_file = output_basename.with_suffix(".bval")
    with open(bval_file, "w") as f:
        bval_values = " ".join(f"{int(val)}" for val in bval)
        f.write(bval_values + "\n")
    logger.info(f"Wrote bval file: {bval_file}")


def process_dwi_bvec_bval(session_path, seqinfo_list):
    """
    Process all DWI files in a session and generate bvec/bval files.

    This function finds all *_dwi.nii* files in the session directory,
    extracts the gradient information from corresponding DICOM files,
    and writes bvec/bval sidecar files.

    Parameters
    ----------
    session_path : str or Path
        Path to the BIDS session directory (e.g., sub-01/ses-01)
    seqinfo_list : list
        List of seqinfo objects from heudiconv containing DICOM metadata
    """
    session_path = Path(session_path)
    logger.info(f"Processing DWI files in session: {session_path}")

    # Find all DWI NIfTI files in the dwi subdirectory
    dwi_dir = session_path / "dwi"
    if not dwi_dir.exists():
        logger.info("No dwi directory found, skipping bvec/bval generation")
        return

    # Process all *_dwi.nii* files
    dwi_files = list(dwi_dir.glob("*_dwi.nii*"))
    logger.info(f"Found {len(dwi_files)} DWI files to process")

    for dwi_file in dwi_files:
        logger.info(f"Processing DWI file: {dwi_file.name}")

        # Extract series ID from the filename or JSON sidecar
        # For now, we'll try to match based on the run number or other metadata
        # In a real implementation, you would parse the JSON sidecar to get
        # the series information

        # Get the basename without extension
        basename = str(dwi_file)
        if basename.endswith(".nii.gz"):
            basename = basename[:-7]
        elif basename.endswith(".nii"):
            basename = basename[:-4]

        # Check if bvec/bval already exist
        if Path(f"{basename}.bvec").exists() and Path(f"{basename}.bval").exists():
            logger.info(f"bvec/bval files already exist for {dwi_file.name}, skipping")
            continue

        # In a real implementation, you would:
        # 1. Read the JSON sidecar to get series information
        # 2. Use get_dicom_path_from_series() to find the DICOM file
        # 3. Extract bvec/bval using get_bvec_bval()

        # For now, we'll use a simplified approach
        # Assuming we can find the DICOM path from seqinfo
        dcm_path = None
        for seq in seqinfo_list:
            # Match based on series description or other criteria
            # This is simplified - real implementation would be more robust
            if hasattr(seq, "example_dcm_file") and "DWI" in str(
                getattr(seq, "series_description", "")
            ):
                dcm_path = seq.example_dcm_file
                break

        if dcm_path:
            logger.info(f"Found DICOM file: {dcm_path}")
            bvec, bval = get_bvec_bval(dcm_path)
            write_bvec_bval(bvec, bval, basename)
        else:
            logger.warning(f"Could not find DICOM file for {dwi_file.name}, skipping")


def AttachToSession():  # noqa: N802
    """
    Return a callable that will be called by heudiconv after conversion.

    This function is called by heudiconv's conversion process and allows
    custom post-processing of the converted data.

    Returns
    -------
    callable
        Function that takes (session, seqinfo, **kwargs) and processes DWI files
    """

    def process_session(session, seqinfo, **kwargs):
        """
        Process a BIDS session to add bvec/bval files for DWI data.

        Parameters
        ----------
        session : str or Path
            Path to the BIDS session directory
        seqinfo : list
            List of seqinfo objects from heudiconv
        **kwargs : dict
            Additional keyword arguments (ignored)
        """
        process_dwi_bvec_bval(session, seqinfo)

    return process_session
