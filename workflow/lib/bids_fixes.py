# workflow/lib/bids_fixes.py

"""
bids_fixes.py — Library of dataset fix functions.
Each fix function operates on a Path and a fix specification dict.
They are auto-registered via the @register_fix decorator.
"""

import hashlib
import json
import logging
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)

# --- global registry ---
FIX_REGISTRY: dict[str, dict[str, Any]] = {}


def register_fix(name: str | None = None, grouped: bool = False):
    """Decorator to register a fix function.

    Stored metadata (FIX_REGISTRY[name]):
      {
        "func": <callable>,
        "grouped": bool
      }

    grouped=True -> runner should call func(list_of_paths, ctx)
    grouped=False -> runner should call func(path, ctx) for each match
    """

    def decorator(func: Callable):
        fix_name = name or func.__name__
        meta = {"func": func, "grouped": bool(grouped)}
        FIX_REGISTRY[fix_name] = meta
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


def _axcodes2aff(axcodes, scale, translate, labels=None):
    """Create a homogeneous affine from axis codes.

    Uses the provided scale and translate to set diag and offset.

    Parameters
    ----------
    axcodes : sequence of length p
        Axis codes, e.g. ('R','A','S') or (None, 'L', 'S').
    scale: (3,) list of scaling values for X Y Z
    translate: (3,) list of translation values for X Y Z
    labels : sequence of (2,) label tuples, optional
        Same semantics as for axcodes2ornt / ornt2axcodes.  If None, defaults
        to (('L','R'), ('P','A'), ('I','S')).

    Returns
    -------
    aff : (p+1, p+1) ndarray
        Homogeneous affine implementing the permutation and flips implied by
        `axcodes`, with provided translation and scaling.

    Notes
    -----
    - If an axis code is None (a dropped axis), the corresponding column in
      the linear part is left all zeros.
    """
    from nibabel.orientations import axcodes2ornt

    ornt = axcodes2ornt(axcodes, labels)
    p = ornt.shape[0]
    aff = np.zeros((p + 1, p + 1), dtype=float)
    # Fill linear part: for each input axis (column), put a 1 or -1 in the
    # output-axis row indicated by ornt[:,0]
    for in_idx, (out_ax, flip) in enumerate(ornt):
        if np.isnan(out_ax):
            # dropped axis -> leave column zero
            continue
        out_idx = int(out_ax)
        aff[out_idx, in_idx] = float(flip) * scale[in_idx]
        aff[out_idx, p] = translate[in_idx]
    aff[p, p] = 1.0
    return aff


@register_fix("fix_orientation_quadruped")
def fix_orientation_quadruped(path: Path, spec: dict) -> bool:
    """Robust and minimal reorientation of quadruped (sphinx) data."""
    if not any(path.name.endswith(ext) for ext in [".nii", ".nii.gz"]):
        return False

    img = nib.load(path)
    scale = img.header.get_zooms()
    old_affine = img.affine

    # quadruped orientation requires reorder ([0,2,1]) then flip ([1,-1,1])
    quad_ornt = np.array([[0, 2, 1], [1, -1, 1]]).T  #  (e.g. RPI to RSP)

    # apply these transformations to the original orientation
    init_orient = nib.orientations.aff2axcodes(old_affine)

    out_orient_reordered = [init_orient[i] for i in quad_ornt[:, 0]]

    out_orient_flipped = []
    flip_lut = dict(zip("RASLPI", "LPIRAS", strict=False))
    for ax, flip in zip(out_orient_reordered, quad_ornt[:, 1], strict=False):
        if flip == 1:
            out_orient_flipped.append(ax)
        else:
            out_orient_flipped.append(flip_lut[ax])

    out_orient = "".join(out_orient_flipped)

    # get the voxel coordinates of origin (magnet isocentre)
    # using original affine (we want to ensure these same voxel
    # coordinates also get mapped to the magnet isocentre

    origin_ras = np.zeros((4, 1))
    origin_ras[-1, 0] = 1
    origin_old_vox = np.linalg.inv(old_affine) @ origin_ras

    # make an initial affine with zero translation offset
    # (will add the offset later based on magnet isocentre)
    affine = _axcodes2aff(out_orient, scale=scale, translate=np.zeros((3, 1)))

    offset = affine @ origin_old_vox

    # adjust offset to obtain phys origin (ie scanner isocenter) in identical vox location
    affine[:, -1] = -offset[:, 0]

    out_img = nib.Nifti1Image(img.dataobj, affine=affine, header=img.header)
    out_img.to_filename(path)
    return True


def _compute_nifti_hash(path: Path) -> str:
    """Compute hash of NIfTI file data for duplicate detection.

    Loads the NIfTI data and computes MD5 hash of the array data.
    This is more reliable than file-level hashing as it ignores
    minor header differences.

    Note: For very large files, this may be memory-intensive as it
    loads the entire image into memory.
    """
    img = nib.load(path)
    data = np.asanyarray(img.dataobj)
    return hashlib.md5(data.tobytes()).hexdigest()


@register_fix("remove_duplicate_niftis", grouped=True)
def remove_duplicate_niftis(paths: list[Path], spec: dict) -> int:
    """Remove duplicate NIfTI files keeping the first one (alphanum sorted)."""

    # Sort files alphanumerically
    nifti_files = sorted(paths, key=str)

    # Group files by their content hash
    hash_to_files = {}
    for nifti_file in nifti_files:
        try:
            file_hash = _compute_nifti_hash(nifti_file)
            if file_hash not in hash_to_files:
                hash_to_files[file_hash] = []
            hash_to_files[file_hash].append(nifti_file)
        except (OSError, ValueError, nib.spatialimages.ImageFileError) as e:
            # If we can't read a file, skip it
            logger.warning(f"Could not compute hash for {nifti_file}: {e}")
            continue

    # Remove duplicates (keep first, remove rest)
    files_removed = 0
    for _file_hash, files in hash_to_files.items():
        if len(files) > 1:
            # Keep the first file (already sorted), remove the rest
            for duplicate_file in files[1:]:
                # Remove the NIfTI file
                duplicate_file.unlink()
                files_removed += 1

                # Remove corresponding JSON sidecar if it exists
                # Handle both .nii and .nii.gz extensions
                if duplicate_file.suffix == ".gz" and str(duplicate_file).endswith(
                    ".nii.gz"
                ):
                    # For .nii.gz, replace with .json
                    json_file = duplicate_file.with_suffix("").with_suffix(".json")
                elif duplicate_file.suffix == ".nii":
                    # For .nii, replace with .json
                    json_file = duplicate_file.with_suffix(".json")
                else:
                    # Unknown extension, skip
                    continue

                if json_file.exists():
                    json_file.unlink()
                    files_removed += 1

    return files_removed


@register_fix("split_multiecho_nifti")
def split_multiecho_nifti(path: Path, spec: dict) -> bool:
    """Split a multi-echo NIfTI into separate echo volumes and an average echo image.

    Expects a 4D NIfTI where the 4th dimension indexes echoes.  Produces one
    3D file per echo (``echo-N`` entity placed after ``run-``) and one average
    echo image (``rec-avgecho`` entity placed before ``run-``), then removes
    the original combined file.  JSON sidecars are copied for every output
    file and the original sidecar is removed alongside the NIfTI.
    """
    if not any(path.name.endswith(ext) for ext in [".nii", ".nii.gz"]):
        return False

    img = nib.load(path)

    # Use img.shape to check dimensions before loading full data array
    if len(img.shape) != 4 or img.shape[3] < 2:
        return False

    data = np.asanyarray(img.dataobj)
    n_echoes = data.shape[3]

    # Parse filename base and extension
    if path.name.endswith(".nii.gz"):
        ext = ".nii.gz"
        base = path.name[:-7]
    else:
        ext = ".nii"
        base = path.name[:-4]

    # Locate the run entity so we can place echo- / rec- correctly
    run_match = re.search(r"(_run-[^_]+)", base)

    # JSON sidecar path (same stem, .json extension)
    json_path = (
        path.with_suffix("").with_suffix(".json")
        if ext == ".nii.gz"
        else path.with_suffix(".json")
    )

    # Save individual echo volumes
    for echo_idx in range(n_echoes):
        echo_num = echo_idx + 1
        echo_data = data[..., echo_idx]
        echo_img = nib.Nifti1Image(echo_data, img.affine, img.header)

        # echo- placed immediately after run- (BIDS spec)
        if run_match:
            echo_base = (
                base[: run_match.end()] + f"_echo-{echo_num}" + base[run_match.end() :]
            )
        else:
            last_us = base.rfind("_")
            if last_us >= 0:
                echo_base = base[:last_us] + f"_echo-{echo_num}" + base[last_us:]
            else:
                echo_base = base + f"_echo-{echo_num}"

        nib.save(echo_img, path.parent / (echo_base + ext))

        if json_path.exists():
            shutil.copy2(json_path, path.parent / (echo_base + ".json"))

    # Create average echo image (float32) with rec-avgecho entity
    avg_data = np.mean(data, axis=3).astype(np.float32)
    avg_img = nib.Nifti1Image(avg_data, img.affine, img.header)
    avg_img.set_data_dtype(np.float32)

    # rec- placed immediately before run- (BIDS spec)
    if run_match:
        avg_base = (
            base[: run_match.start()] + "_rec-avgecho" + base[run_match.start() :]
        )
    else:
        last_us = base.rfind("_")
        if last_us >= 0:
            avg_base = base[:last_us] + "_rec-avgecho" + base[last_us:]
        else:
            avg_base = base + "_rec-avgecho"

    nib.save(avg_img, path.parent / (avg_base + ext))

    if json_path.exists():
        shutil.copy2(json_path, path.parent / (avg_base + ".json"))

    # Remove the original multi-echo file and its JSON sidecar
    path.unlink()
    if json_path.exists():
        json_path.unlink()

    return True


def describe_available_fixes():
    """Return a markdown list of all registered fixes and their docstrings."""
    lines = ["### Available Fixes:"]
    for name, meta in FIX_REGISTRY.items():
        func = meta["func"]
        doc = (func.__doc__ or "").strip().split("\n")[0]
        lines.append(f"- **{name}** — {doc}")
    return "\n".join(lines)
