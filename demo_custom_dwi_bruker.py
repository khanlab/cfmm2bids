#!/usr/bin/env python
"""
Demo script to show how custom_dwi_bruker functions work.

This script demonstrates the basic functionality of the custom_dwi_bruker
module without requiring actual DICOM files or a full heudiconv setup.
"""

import sys
import tempfile
from pathlib import Path

# Add heuristics to path
sys.path.insert(0, str(Path(__file__).parent))

from heuristics.custom_dwi_bruker import (
    get_bvec_bval,
    get_dicom_path_from_series,
    write_bvec_bval,
)


def demo_get_bvec_bval():
    """Demonstrate extracting bvec/bval from DICOM (using dummy data)."""
    print("\n" + "=" * 70)
    print("Demo 1: Extract bvec/bval from DICOM")
    print("=" * 70)

    dummy_dcm_path = "/path/to/dummy/dicom.dcm"
    print(f"Input: {dummy_dcm_path}")
    print("Note: This uses dummy data. Replace get_bvec_bval() implementation")
    print("      with actual DICOM tag extraction for your scanner.")

    bvec, bval = get_bvec_bval(dummy_dcm_path)

    print(f"\nExtracted bvec shape: {bvec.shape}")
    print(f"Extracted bval shape: {bval.shape}")
    print(f"Number of gradient directions: {bvec.shape[1]}")

    print("\nFirst 5 directions (bvec):")
    for i in range(min(5, bvec.shape[1])):
        print(
            f"  Direction {i}: [{bvec[0, i]:7.4f}, {bvec[1, i]:7.4f}, {bvec[2, i]:7.4f}]"
        )

    print("\nFirst 5 b-values:")
    for i in range(min(5, bval.shape[0])):
        print(f"  b-value {i}: {bval[i]:.0f} s/mm²")


def demo_write_bvec_bval():
    """Demonstrate writing bvec/bval files to disk."""
    print("\n" + "=" * 70)
    print("Demo 2: Write bvec/bval to BIDS-format files")
    print("=" * 70)

    # Get dummy data
    bvec, bval = get_bvec_bval("/dummy/path")

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "sub-01_ses-01_run-01_dwi"
        print(f"Output basename: {output_path}")

        write_bvec_bval(bvec, bval, output_path)

        bvec_file = output_path.with_suffix(".bvec")
        bval_file = output_path.with_suffix(".bval")

        print("\nCreated files:")
        print(f"  {bvec_file.name}")
        print(f"  {bval_file.name}")

        print("\nbvec file content (first 3 directions):")
        with open(bvec_file) as f:
            for i, line in enumerate(f):
                values = line.strip().split()[:3]  # First 3 values
                axis = ["x", "y", "z"][i]
                print(f"  {axis}: {' '.join(values)} ...")

        print("\nbval file content (first 10 values):")
        with open(bval_file) as f:
            line = f.readline()
            values = line.strip().split()[:10]  # First 10 values
            print(f"  {' '.join(values)} ...")


def demo_get_dicom_path():
    """Demonstrate finding DICOM path from series info."""
    print("\n" + "=" * 70)
    print("Demo 3: Get DICOM path from series info")
    print("=" * 70)

    # Create mock seqinfo objects
    class MockSeqInfo:
        def __init__(self, series_id, series_desc, dcm_file):
            self.series_id = series_id
            self.series_description = series_desc
            self.example_dcm_file = dcm_file

    seqinfo_list = [
        MockSeqInfo("001", "T1w", "/path/to/series001/dcm001.dcm"),
        MockSeqInfo("002", "DWI", "/path/to/series002/dcm002.dcm"),
        MockSeqInfo("003", "T2w", "/path/to/series003/dcm003.dcm"),
    ]

    print("Mock seqinfo list:")
    for seq in seqinfo_list:
        print(f"  Series {seq.series_id}: {seq.series_description}")

    series_id = "002"
    dcm_path = get_dicom_path_from_series(seqinfo_list, series_id)

    print(f"\nLooking for series ID: {series_id}")
    print(f"Found DICOM path: {dcm_path}")


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print("Custom DWI Bruker Heuristic - Functionality Demo")
    print("=" * 70)

    demo_get_bvec_bval()
    demo_write_bvec_bval()
    demo_get_dicom_path()

    print("\n" + "=" * 70)
    print("Demo complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Replace get_bvec_bval() with actual DICOM tag extraction")
    print("2. Use the heuristic with heudiconv:")
    print(
        "   heudiconv -d /dicoms -s sub01 -ss ses01 -f custom_dwi_bruker.py -c dcm2niix -b -o /bids"
    )
    print("3. Or import into existing heuristics (see trident_15T.py example)")
    print()


if __name__ == "__main__":
    main()
