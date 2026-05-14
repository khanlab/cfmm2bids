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
from glob import glob
from pathlib import Path
from typing import Any, Literal

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)

# --- global registry ---
FIX_REGISTRY: dict[str, dict[str, Any]] = {}


def register_fix(
    name: str | None = None,
    grouped: bool = False,
    scope: Literal["path", "session"] = "path",
):
    """Decorator to register a fix function.

    Stored metadata (FIX_REGISTRY[name]):
      {
        "func": <callable>,
        "grouped": bool,
        "scope": "path" | "session",
      }

    grouped=True -> runner should call func(list_of_paths, ctx)
    grouped=False -> runner should call func(path, ctx) for each match
    """

    def decorator(func: Callable):
        fix_name = name or func.__name__
        meta = {"func": func, "grouped": bool(grouped), "scope": scope}
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


@register_fix("copy_from_path", scope="session")
def copy_from_path(session_dir: Path, spec: dict) -> int:
    """Copy one file from a globbed custom source path into the BIDS session directory.

    Uses shell-style glob syntax in ``src`` (`*`, `?`, `[abc]`, `**`).
    Recursive matching requires ``**`` in the source pattern.
    """
    subject = str(spec.get("subject", ""))
    session = str(spec.get("session", ""))

    src_template = spec.get("src", "")
    dst_template = spec.get("dst", "")
    required = bool(spec.get("required", True))

    if not src_template or not dst_template:
        raise ValueError("copy_from_path requires both 'src' and 'dst'")

    try:
        src_pattern = src_template.format(subject=subject, session=session)
        dst_rel = Path(dst_template.format(subject=subject, session=session))
    except KeyError as exc:
        raise ValueError(f"copy_from_path template key missing: {exc}") from exc

    if dst_rel.is_absolute():
        raise ValueError(
            "copy_from_path 'dst' must be relative to the session directory"
        )
    if ".." in dst_rel.parts:
        raise ValueError("copy_from_path 'dst' cannot include '..' path segments")

    matches = sorted(glob(src_pattern, recursive=True))
    if len(matches) == 0:
        msg = f"copy_from_path: no matches for source pattern: {src_pattern}"
        if required:
            raise FileNotFoundError(msg)
        logger.warning(msg)
        return 0

    if len(matches) > 1:
        raise ValueError(
            f"copy_from_path expected 1 match for '{src_pattern}', got {len(matches)}"
        )

    src_path = Path(matches[0])
    dst_path = session_dir / dst_rel
    resolved_dst = dst_path.resolve()
    resolved_session = session_dir.resolve()
    if not resolved_dst.is_relative_to(resolved_session):
        raise ValueError("copy_from_path destination escapes the session directory")

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dst_path)
    logger.info(f"copy_from_path: copied {src_path} -> {dst_path}")
    return 1


def _find_bids_root(path: Path) -> Path | None:
    """Find the BIDS dataset root from a path inside the dataset.

    Traverses parent directories until a ``sub-*`` directory is found,
    then returns its parent (the BIDS root).  Returns ``None`` when no
    such parent can be located.
    """
    for parent in path.parents:
        if parent.name.startswith("sub-"):
            return parent.parent
    return None


@register_fix("intended_for")
def fix_intended_for(path: Path, spec: dict) -> bool:
    """Populate IntendedFor in a fieldmap JSON with paths to matching NIfTI files.

    Searches for NIfTI files matching ``target_pattern`` within the same
    session directory as the fieldmap JSON and sets the ``IntendedFor``
    field.  By default paths are written relative to the subject directory
    (e.g. ``"ses-pre/func/sub-01_ses-pre_task-rest_bold.nii.gz"``), which is
    the format expected by most BIDS apps (including fMRIPrep).  Set
    ``use_bids_uri: true`` in the spec to use the ``bids::`` URI format
    instead.

    Spec fields
    -----------
    target_pattern : str
        Glob pattern for target NIfTI files, relative to the session
        directory (e.g. ``"func/*bold.nii.gz"``).
    use_bids_uri : bool, optional
        When ``true``, write paths using the ``bids::`` URI scheme
        (e.g. ``"bids::sub-01/ses-pre/func/sub-01_ses-pre_task-rest_bold.nii.gz"``).
        Defaults to ``false``.
    """
    if path.suffix != ".json":
        return False

    target_pattern = spec.get("target_pattern", "")
    if not target_pattern:
        logger.warning(f"intended_for fix: no target_pattern specified for {path}")
        return False

    use_bids_uri = bool(spec.get("use_bids_uri", False))

    # The session directory is the parent of the modality folder (e.g. fmap/).
    session_dir = path.parent.parent

    if use_bids_uri:
        bids_root = _find_bids_root(path)
        if bids_root is None:
            logger.warning(
                f"intended_for fix: could not determine BIDS root for {path}"
            )
            return False

    # Collect target NIfTI files within the session directory.
    target_paths = sorted(session_dir.glob(target_pattern))

    if not target_paths:
        logger.warning(
            f"intended_for fix: no targets matching '{target_pattern}' in {session_dir}"
        )
        return False

    if use_bids_uri:
        intended_for = [
            f"bids::{p.relative_to(bids_root).as_posix()}" for p in target_paths
        ]
    else:
        # Paths relative to the subject directory (fMRIPrep-compatible format),
        # e.g. "ses-pre/func/sub-01_ses-pre_task-rest_bold.nii.gz".
        subject_dir = session_dir.parent
        intended_for = [p.relative_to(subject_dir).as_posix() for p in target_paths]

    with open(path) as f:
        data = json.load(f)
    data["IntendedFor"] = intended_for
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


def _mp2rage_robust_func(inv1: np.ndarray, inv2: np.ndarray, beta: float) -> np.ndarray:
    """Robust MP2RAGE combination function.

    Adapted from Jose Marques' RobustCombination MATLAB implementation,
    https://github.com/JosePMarques/MP2RAGE-related-scripts, as described in
    Caan et al. (2019) https://doi.org/10.1371/journal.pone.0099676.
    """
    return (np.conj(inv1) * inv2 - beta) / (inv1**2 + inv2**2 + 2 * beta)


def _rootsquares_pos(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Positive root of ax^2 + bx + c = 0."""
    return (-b + np.sqrt(b**2 - 4 * a * c)) / (2 * a)


def _rootsquares_neg(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Negative root of ax^2 + bx + c = 0."""
    return (-b - np.sqrt(b**2 - 4 * a * c)) / (2 * a)


def _compute_mp2rage_uni_den(
    uni_path: Path,
    inv1_path: Path,
    inv2_path: Path,
    output_path: Path,
    multiplying_factor: int = 6,
) -> None:
    """Compute and save the noise-robust MP2RAGE UNI-DEN image.

    Implements the algorithm from Caan et al. (2019):
    https://doi.org/10.1371/journal.pone.0099676

    Parameters
    ----------
    uni_path:
        Path to the MP2RAGE UNI NIfTI file.
    inv1_path:
        Path to the INV1 (first inversion) NIfTI file.
    inv2_path:
        Path to the INV2 (second inversion) NIfTI file.
    output_path:
        Destination path for the UNI-DEN output NIfTI file.
    multiplying_factor:
        Noise scaling factor.  Values between 1 and 10 are typical; higher
        values suppress more noise.  Defaults to ``6``.
    """
    mp2rage_img = nib.load(uni_path)
    inv1_img = nib.load(inv1_path)
    inv2_img = nib.load(inv2_path)

    mp2rage_data = mp2rage_img.get_fdata()
    inv1_data = inv1_img.get_fdata()
    inv2_data = inv2_img.get_fdata()

    with np.errstate(all="ignore"):
        if mp2rage_data.min() >= 0 and mp2rage_data.max() >= 0.51:
            # Convert from positive integer format to -0.5 to 0.5 range
            mp2rage_data = (mp2rage_data - mp2rage_data.max() / 2) / mp2rage_data.max()
            integer_format = True
        else:
            integer_format = False

        # Give the correct polarity to INV1
        inv1_data = np.sign(mp2rage_data) * inv1_data

        # Estimate a phase-sensitive INV1 using INV2 as reference
        inv1_pos = _rootsquares_pos(
            -mp2rage_data, inv2_data, -(inv2_data**2) * mp2rage_data
        )
        inv1_neg = _rootsquares_neg(
            -mp2rage_data, inv2_data, -(inv2_data**2) * mp2rage_data
        )

        inv1_final = inv1_data.copy()
        mask_neg = np.abs(inv1_data - inv1_pos) > np.abs(inv1_data - inv1_neg)
        inv1_final[mask_neg] = inv1_neg[mask_neg]
        inv1_final[~mask_neg] = inv1_pos[~mask_neg]

        # Estimate noise from the corner of INV2 and compute robust combination
        noise_level = multiplying_factor * np.mean(inv2_data[:, -11:, -11:])
        result = _mp2rage_robust_func(inv1_final, inv2_data, noise_level**2)

        if integer_format:
            result = np.round(4095 * (result + 0.5))

    result_int16 = nib.casting.float_to_int(result, "int16")
    new_img = nib.Nifti1Image(result_int16, mp2rage_img.affine, mp2rage_img.header)
    new_img.set_data_dtype(np.int16)
    nib.save(new_img, output_path)


@register_fix("gen_mp2rage_uni_den")
def gen_mp2rage_uni_den(path: Path, spec: dict) -> bool:
    """Generate a noise-robust MP2RAGE UNI-DEN T1w image from UNI, INV1, and INV2.

    For a ``_UNIT1`` MP2RAGE NIfTI file this fix locates the matching INV1 and
    INV2 inversion images in the same directory and computes a denoised T1w
    image (UNI-DEN) using the robust combination method described in Caan et
    al. (2019).  The output is written as a T1w NIfTI with the ``acq-`` entity
    set to ``output_acq`` (default ``MP2RAGEpostproc``).

    Expected filename patterns (from cfmm_base heuristic):

    * UNI:   ``{prefix}_acq-MP2RAGE_{entities}_UNIT1.nii.gz``
    * INV1:  ``{prefix}_{entities}_inv-1_MP2RAGE.nii.gz``
    * INV2:  ``{prefix}_{entities}_inv-2_MP2RAGE.nii.gz``

    The fix is skipped when the destination file already exists *or* when a
    T1w file with ``acq-MP2RAGE`` (i.e. a scanner-produced T1w) is already
    present for the same subject/session/run.

    The JSON sidecar from the UNI file is copied to the new T1w output when
    present.

    Spec fields
    -----------
    multiplying_factor : int, optional
        Noise scaling factor passed to the UNI-DEN algorithm.  Increase up to
        ``10`` for more aggressive noise suppression.  Defaults to ``6``.
    output_acq : str, optional
        Value for the ``acq-`` BIDS entity in the output filename.  Defaults
        to ``"MP2RAGEpostproc"``.
    """
    if not any(path.name.endswith(ext) for ext in [".nii", ".nii.gz"]):
        return False

    multiplying_factor = int(spec.get("multiplying_factor", 6))
    output_acq = spec.get("output_acq", "MP2RAGEpostproc")

    # Parse filename: determine extension and base stem
    if path.name.endswith(".nii.gz"):
        ext = ".nii.gz"
        base = path.name[:-7]
    else:
        ext = ".nii"
        base = path.name[:-4]

    # Must end with _UNIT1 (BIDS MP2RAGE UNI suffix)
    unit1_marker = "_UNIT1"
    if not base.endswith(unit1_marker):
        logger.warning(f"gen_mp2rage_uni_den: '_UNIT1' suffix not found in {path.name}")
        return False

    base_stripped = base[: -len(unit1_marker)]

    # Must contain _acq-MP2RAGE_ to locate the split point
    acq_marker = "_acq-MP2RAGE_"
    idx = base_stripped.find(acq_marker)
    if idx == -1:
        logger.warning(f"gen_mp2rage_uni_den: '_acq-MP2RAGE_' not found in {path.name}")
        return False

    # Everything before the acq entity (subject/session prefix)
    before_acq = base_stripped[:idx]
    # Remaining entities after acq-MP2RAGE (e.g. run-01 or rec-DIS3D_run-01)
    other_entities = base_stripped[idx + len(acq_marker) :]

    anat_dir = path.parent

    # INV files share the same prefix and entities but have no acq- entity
    inv1_path = anat_dir / f"{before_acq}_{other_entities}_inv-1_MP2RAGE{ext}"
    inv2_path = anat_dir / f"{before_acq}_{other_entities}_inv-2_MP2RAGE{ext}"
    existing_t1w_path = anat_dir / f"{before_acq}_acq-MP2RAGE_{other_entities}_T1w{ext}"
    new_t1w_path = anat_dir / f"{before_acq}_acq-{output_acq}_{other_entities}_T1w{ext}"

    if not inv1_path.exists():
        logger.warning(f"gen_mp2rage_uni_den: INV1 not found: {inv1_path}")
        return False

    if not inv2_path.exists():
        logger.warning(f"gen_mp2rage_uni_den: INV2 not found: {inv2_path}")
        return False

    if existing_t1w_path.exists():
        logger.info(
            f"gen_mp2rage_uni_den: scanner T1w already exists, skipping: "
            f"{existing_t1w_path.name}"
        )
        return False

    if new_t1w_path.exists():
        logger.info(
            f"gen_mp2rage_uni_den: output already exists, skipping: {new_t1w_path.name}"
        )
        return False

    _compute_mp2rage_uni_den(
        path, inv1_path, inv2_path, new_t1w_path, multiplying_factor
    )

    # Copy JSON sidecar from UNI file
    uni_json = (
        path.with_suffix("").with_suffix(".json")
        if ext == ".nii.gz"
        else path.with_suffix(".json")
    )
    if uni_json.exists():
        new_t1w_json = (
            new_t1w_path.with_suffix("").with_suffix(".json")
            if ext == ".nii.gz"
            else new_t1w_path.with_suffix(".json")
        )
        shutil.copy2(uni_json, new_t1w_json)

    logger.info(f"gen_mp2rage_uni_den: generated {new_t1w_path.name}")
    return True


def describe_available_fixes():
    """Return a markdown list of all registered fixes and their docstrings."""
    lines = ["### Available Fixes:"]
    for name, meta in FIX_REGISTRY.items():
        func = meta["func"]
        doc = (func.__doc__ or "").strip().split("\n")[0]
        lines.append(f"- **{name}** — {doc}")
    return "\n".join(lines)
