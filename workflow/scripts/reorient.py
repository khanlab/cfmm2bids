#!/usr/bin/env python3
"""
Reorient NIfTI images to a specified orientation.

This script reads all NIfTI images from a BIDS subject/session directory,
applies a reorientation transformation, and writes the output to a new directory
with the same structure and filenames.
"""

import numpy as np
import nibabel as nib
from pathlib import Path
import shutil


def _align_affine_to_input_orientation(affine, orientation):
    """
    Reorders and flips the affine matrix to align with the specified input orientation.

    Parameters:
        affine (np.ndarray): Initial affine matrix.
        orientation (str): Input orientation (e.g., 'RAS').

    Returns:
        np.ndarray: Reordered and flipped affine matrix.
    """
    axis_map = {"R": 0, "L": 0, "A": 1, "P": 1, "S": 2, "I": 2}
    sign_map = {"R": 1, "L": -1, "A": 1, "P": -1, "S": 1, "I": -1}

    input_axes = [axis_map[ax] for ax in orientation]
    input_signs = [sign_map[ax] for ax in orientation]

    reordered_affine = np.zeros_like(affine)
    for i, (axis, sign) in enumerate(zip(input_axes, input_signs)):
        reordered_affine[i, :3] = sign * affine[axis, :3]
        reordered_affine[i, 3] = sign * affine[i, 3]

    # Copy the homogeneous row
    reordered_affine[3, :] = affine[3, :]

    return reordered_affine


def reorient_nifti(input_path, output_path, orientation):
    """
    Reorient a NIfTI image to the specified orientation.

    Parameters:
        input_path (Path): Path to input NIfTI file
        output_path (Path): Path to output NIfTI file
        orientation (str): Target orientation (e.g., 'RIA')
    """
    # Load the NIfTI image
    img = nib.load(input_path)
    
    # Get the current affine and data
    affine = img.affine
    data = img.get_fdata()
    
    # Apply reorientation to the affine
    new_affine = _align_affine_to_input_orientation(affine, orientation)
    
    # Create new image with reoriented affine
    new_img = nib.Nifti1Image(data, new_affine, img.header)
    
    # Save the reoriented image
    nib.save(new_img, output_path)


def process_session_directory(input_dir, output_dir, orientation):
    """
    Process all NIfTI files in a session directory.

    Parameters:
        input_dir (Path): Input session directory
        output_dir (Path): Output session directory
        orientation (str): Target orientation
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    # Create output directory structure
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Find all .nii and .nii.gz files
    nifti_files = list(input_path.rglob("*.nii")) + list(input_path.rglob("*.nii.gz"))
    
    print(f"Found {len(nifti_files)} NIfTI files to process")
    
    for nifti_file in nifti_files:
        # Get relative path from input directory
        rel_path = nifti_file.relative_to(input_path)
        
        # Create corresponding output path
        out_file = output_path / rel_path
        out_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Reorient the image
        print(f"Processing: {rel_path}")
        reorient_nifti(nifti_file, out_file, orientation)
    
    # Copy all non-NIfTI files (JSON sidecars, etc.)
    all_files = list(input_path.rglob("*"))
    for file_path in all_files:
        if file_path.is_file():
            # Skip NIfTI files (already processed)
            if file_path.suffix == '.nii' or (file_path.suffix == '.gz' and file_path.stem.endswith('.nii')):
                continue
                
            rel_path = file_path.relative_to(input_path)
            out_file = output_path / rel_path
            out_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy the file
            shutil.copy2(file_path, out_file)
            print(f"Copied: {rel_path}")
    
    print(f"Completed processing session directory")


# Main execution for Snakemake
if __name__ == "__main__":
    input_dir = snakemake.input.bids_subj_dir
    output_dir = snakemake.output.reoriented_subj_dir
    orientation = snakemake.params.orientation
    
    print(f"Reorienting images to {orientation}")
    print(f"Input: {input_dir}")
    print(f"Output: {output_dir}")
    
    process_session_directory(input_dir, output_dir, orientation)
