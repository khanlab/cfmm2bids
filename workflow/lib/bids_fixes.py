# workflow/lib/bids_fixes.py

"""
bids_fixes.py — Library of dataset fix functions.
Each fix function operates on a Path and a fix specification dict.
They are auto-registered via the @register_fix decorator.
"""

import json
import nibabel as nib
import numpy as np
from pathlib import Path


# --- global registry ---
FIX_REGISTRY = {}


def register_fix(name=None):
    """Decorator to register a fix function automatically."""

    def decorator(func):
        fix_name = name or func.__name__
        FIX_REGISTRY[fix_name] = func
        return func

    return decorator


# --- fix implementations ---


@register_fix("remove")
def remove_file(path: Path, spec: dict) -> bool:
    """Remove the file entirely."""
    path.unlink(missing_ok=True)
    return True


@register_fix("update_json")
def update_json(path: Path, spec: dict) -> bool:
    """Update JSON file fields according to `updates` dict."""
    if path.suffix != ".json":
        return False
    updates = spec.get("updates", {})
    with open(path) as f:
        data = json.load(f)
    data.update(updates)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return True


@register_fix("fix_orientation")
def fix_orientation(path: Path, spec: dict) -> bool:
    """Reorient NIfTI file to canonical (RAS+) orientation."""
    if not any(path.name.endswith(ext) for ext in [".nii", ".nii.gz"]):
        return False
    img = nib.load(str(path))
    img = nib.as_closest_canonical(img)
    nib.save(img, str(path))
    return True


@register_fix("reset_orientation")
def reset_orientation(path: Path, spec: dict) -> bool:
    """Reorder affine and volume to canonical, then reset origin to center (for quadrupeds imaged with wrong orientation)."""
    if not any(path.name.endswith(ext) for ext in [".nii", ".nii.gz"]):
        return False
    
    # Load the image
    img = nib.load(str(path))
    
    # Step 1: Reorder to canonical orientation
    img_canonical = nib.as_closest_canonical(img)
    
    # Step 2: Reset the origin to center of volume
    # Extract the rotation/scaling matrix and current translation
    affine = img_canonical.affine
    mat, vec = nib.affines.to_matvec(affine)
    
    # Calculate center voxel coordinates
    shape = img_canonical.shape[:3]  # only spatial dimensions
    center_voxel = [(s - 1) / 2.0 for s in shape]
    
    # Calculate new translation so center voxel maps to world origin (0,0,0)
    # world = mat @ voxel + vec, we want world = 0 at center
    # so: vec_new = -mat @ center_voxel
    new_vec = -mat @ np.array(center_voxel)
    
    # Create new affine with reset origin
    new_affine = nib.affines.from_matvec(mat, new_vec)
    
    # Create new image with updated affine
    # Note: as_closest_canonical may have already loaded data into memory if reordering was needed
    img_reset = nib.Nifti1Image(img_canonical.dataobj, new_affine, img_canonical.header)
    
    # Save the result
    nib.save(img_reset, str(path))
    return True


def describe_available_fixes():
    """Return a markdown list of all registered fixes and their docstrings."""
    lines = ["### Available Fixes:"]
    for name, func in FIX_REGISTRY.items():
        doc = (func.__doc__ or "").strip().split("\n")[0]
        lines.append(f"- **{name}** — {doc}")
    return "\n".join(lines)
