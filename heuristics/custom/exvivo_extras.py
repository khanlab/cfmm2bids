# heuristics/custom/exvivo_extras.py
"""
Hook heudiconv (custom_callable) for ex vivo acquisitions on the Bruker PV360 at 15 T.

Routing by BIDS suffix of the prefix:
  *_dwi      → bvec/bval delegated to custom.bruker (manages the OGSE), + .bmat + _method.json
  *_MP2RAGE  → split of the 4D [X,Y,Z,2] into inv-1/inv-2 + JSON sidecars (Bruker parameters)
"""
import json
import logging
import re
from pathlib import Path
import numpy as np
import nibabel as nib
import pydicom
from custom.bruker import get_bvec_bval, write_bvec_bval  

logger = logging.getLogger(__name__)

BRUKER_METHOD_TAG = (0x0177, 0x1100)
GAMMA_H = 42.577478518  # rapport gyromagnétique 1H (MHz/T)


# ── Parser JCAMP-DX (ton parse_method, verbatim) ─────────────────────────────

def parse_method(lines: list) -> dict:
    """Parses the Bruker PV360 (JCAMP-DX) method file. Keys without ‘$’.
    Returns {key: [tokens]} (consumed dimension) or {key: ‘string’}."""
    params = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = re.match(r'^##\$(\w+)=(.*)$', line)
        if not m:
            i += 1
            continue

        key = m.group(1)
        rest = m.group(2).strip()

        arr_m = re.match(r'^\(\s*([\d,\s]+)\)\s*(.*)', rest)
        if arr_m:
            dims = [int(d) for d in re.split(r'[\s,]+', arr_m.group(1).strip()) if d]
            total = 1
            for d in dims:
                total *= d

            tokens = arr_m.group(2).split() if arr_m.group(2).strip() else []
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if next_line.startswith('##'):
                    break
                tokens += next_line.split()
                j += 1
                if len(tokens) >= total:
                    break

            params[key] = tokens[:total]
            i = j
        else:
            params[key] = rest
            i += 1

    return params


def get_floats(params: dict, key: str) -> list:
    val = params.get(key)
    if val is None:
        return []
    if isinstance(val, list):
        out = []
        for v in val:
            try:
                out.append(float(v))
            except ValueError:
                pass
        return out
    try:
        return [float(str(val).strip())]
    except ValueError:
        return []


def get_float(params: dict, key: str, default=None):
    v = get_floats(params, key)
    return v[0] if v else default


def read_method(dcm_path) -> dict | None:
    """Reads the private tag “Bruker” and returns parse_method(...), or None if it is absent."""
    H = pydicom.dcmread(str(dcm_path), stop_before_pixels=True, force=True)
    elem = H.get(BRUKER_METHOD_TAG)
    if elem is None or not getattr(elem, "value", None):
        logger.warning("Bruker method tag missing/empty in %s", dcm_path)
        return None
    raw = elem.value
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    return parse_method(text.splitlines())


def dump_method_json(method: dict, out_basename: str):
    with open(f"{out_basename}_method.json", "w", encoding="utf-8") as f:
        json.dump(method, f, indent=2)
    logger.info("_method.json written : %s_method.json", out_basename)


# ── DWI : .bmat (bvec/bval sont gérés par custom.bruker) ─────────────────────

def write_bmat(method: dict, out_basename: str):
    """Wrote {out_basename}.bmat (9 lines) from PVM_DwBMat.
    parse_method has already processed the header (n,3,3) → no offset, unlike
    the old standalone version, which used [5:] with simple_jcamp_parse."""
    raw = method.get("PVM_DwBMat")
    if not raw:
        logger.warning("PVM_DwBMat mising ; .bmat not written for %s", out_basename)
        return
    bmat = np.asarray([float(x) for x in raw], dtype=np.float32).reshape(-1, 9).T
    with open(f"{out_basename}.bmat", "w") as fp:
        for row in bmat:
            fp.write(" ".join(str(v) for v in row) + " \n")
    logger.info(".bmat written : %s.bmat (%d volumes)", out_basename, bmat.shape[1])


# ── MP2RAGE : extraction params + split 4D (ton code, verbatim) ──────────────

def extract_mp2rage_params(method: dict) -> dict:
    """MP2RAGE settings with official BIDS names."""
    frq = get_float(method, "PVM_FrqRef")
    b0 = round(frq / GAMMA_H, 4) if frq else None

    tr_ms = get_float(method, "PVM_RepetitionTime")
    rtp = round(tr_ms / 1e3, 6) if tr_ms else None

    tre_ms = get_float(method, "EchoRepTime")
    rte = round(tre_ms / 1e3, 6) if tre_ms else None

    ti_ms = get_floats(method, "MPRAGE_InversionTime")
    tis = [round(v / 1e3, 6) for v in ti_ms]

    fas = get_floats(method, "MPRAGE_FlipAngle")

    overscans = get_floats(method, "PVM_EncPftOverscans")
    matrix = get_floats(method, "PVM_Matrix")
    if len(matrix) >= 3:
        number_shots = int(matrix[2])
    elif len(overscans) >= 3:
        number_shots = int(overscans[2]) * 2  # approximation
    else:
        number_shots = None

    missing = []
    for name, val in [("MagneticFieldStrength", b0),
                      ("RepetitionTimePreparation", rtp),
                      ("RepetitionTimeExcitation", rte),
                      ("InversionTime", tis or None),
                      ("FlipAngle", fas or None),
                      ("NumberShots", number_shots)]:
        if val is None or val == []:
            missing.append(name)
            logger.warning("MP2RAGE parameter missing: %s", name)

    return {
        "MagneticFieldStrength": b0,
        "RepetitionTimePreparation": rtp,
        "RepetitionTimeExcitation": rte,
        "InversionTime": tis,   # [TI1, TI2]
        "FlipAngle": fas,       # [FA1, FA2]
        "NumberShots": number_shots,
        "_missing": missing,
    }


def build_sidecar(params: dict, inv_index: int, existing_json: dict = None) -> dict:
    """BIDS sidecar for inv_index (1 or 2), merged with the dcm2niix JSON."""
    i = inv_index - 1
    sidecar = existing_json.copy() if existing_json else {}

    if params.get("MagneticFieldStrength") is not None:
        sidecar["MagneticFieldStrength"] = params["MagneticFieldStrength"]
    if params.get("RepetitionTimePreparation") is not None:
        sidecar["RepetitionTimePreparation"] = params["RepetitionTimePreparation"]
    if params.get("RepetitionTimeExcitation") is not None:
        sidecar["RepetitionTimeExcitation"] = params["RepetitionTimeExcitation"]
    if params.get("NumberShots") is not None:
        sidecar["NumberShots"] = params["NumberShots"]

    tis = params.get("InversionTime", [])
    fas = params.get("FlipAngle", [])
    if len(tis) > i:
        sidecar["InversionTime"] = tis[i]
    if len(fas) > i:
        sidecar["FlipAngle"] = fas[i]

    return sidecar


def split_mp2rage_4d(nifti_path, base_prefix: str) -> list:
    """Split {…}_MP2RAGE.nii.gz [X,Y,Z,2] → {base}_inv-{1,2}_part-mag_MP2RAGE.nii.gz."""
    img = nib.load(str(nifti_path))
    data = img.get_fdata()
    if data.ndim != 4 or data.shape[3] != 2:
        raise ValueError(
            f"MP2RAGE 4D attendu [X,Y,Z,2], obtenu {data.shape} pour {nifti_path}"
        )
    paths = []
    for idx in (0, 1):
        vol = nib.Nifti1Image(data[..., idx], img.affine, img.header)
        out_path = Path(f"{base_prefix}_inv-{idx + 1}_part-mag_MP2RAGE.nii.gz")
        nib.save(vol, str(out_path))
        logger.info("Volume INV%d écrit : %s", idx + 1, out_path)
        paths.append(out_path)
    return paths


def write_sidecar(sidecar: dict, nii_path: Path):
    json_path = nii_path.with_suffix("").with_suffix(".json")  # retire .gz puis .nii
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=2)
    logger.info("Sidecar written : %s", json_path)


# ── Hook heudiconv ───────────────────────────────────────────────────────────

def custom_callable(prefix, outtypes, item_dicoms):
    logger.debug("custom_callable: prefix=%s", prefix)
    if not item_dicoms:
        logger.warning("custom_callable: No DICOM for %s ; skip.", prefix)
        return

    dcm = item_dicoms[0]
    suffix = prefix.split("_")[-1]

    try:
        if suffix == "dwi":
            bvec, bval = get_bvec_bval(dcm)
            if bvec is not None:
                write_bvec_bval(bvec, bval, prefix)
            method = read_method(dcm)
            if method:
                write_bmat(method, prefix)
                dump_method_json(method, prefix)

        elif suffix == "MP2RAGE":
            nii = Path(f"{prefix}.nii.gz")
            if not nii.exists():
                logger.warning("MP2RAGE 4D not found : %s ; skip.", nii)
                return
            base = prefix[:-len("_MP2RAGE")]

            existing = {}
            dcm2niix_json = Path(f"{prefix}.json")
            if dcm2niix_json.exists():
                existing = json.loads(dcm2niix_json.read_text(encoding="utf-8"))

            method = read_method(dcm)
            params = extract_mp2rage_params(method) if method else {}

            inv_paths = split_mp2rage_4d(nii, base)
            for inv_idx, p in enumerate(inv_paths, start=1):
                write_sidecar(build_sidecar(params, inv_idx, existing), p)

            if method:
                dump_method_json(method, base)

            nii.unlink(missing_ok=True)                  # retirer le 4D d'origine
            dcm2niix_json.unlink(missing_ok=True)

    except Exception:
        logger.exception("custom_callable: failed on %s (other series are not affected)", prefix)