import fnmatch
import re
#from custom.bruker import custom_callable
from custom.exvivo_extras import custom_callable

def create_key(template, outtype=("nii.gz",), annotation_classes=None):
    if template is None or not template:
        raise ValueError("Template must be a valid format string")
    return template, outtype, annotation_classes


def infotodict(seqinfo):
    """
    Heuristic evaluator for ex vivo acquisitions at 15T (Bruker ParaVision 360).

    Notes on Bruker DICOM structure
    --------------------------------
    - Every acquisition produces TWO series (e.g. 30001 + 30002).
      The first is the raw reconstruction; the second is Bruker-denoised.
      Identified by series_id order (lower = raw, higher = denoised).
    - MEGRE QSM (Gre3D_QSM_9Echo_ISO100_1A):
        dim3=720  → magnitude (9 echoes × 80 slices): first=raw, second=denoised
        dim3=2880 → real + imag concatenated (720 × 4), used for MCPC-3D-S
    - MP2RAGE (MP2RAGE_2Echo_100iso):
        dim3=100, VOLUME       → Bruker UNI reconstruction (single, no denoised copy)
        dim3=200, NON_PARALLEL → INV1 + INV2 concatenated → split with bruker_mp2rage_to_bids.py
    - DWI: single series per acquisition; bval/bvec extracted from tag (0177,1100).
    """

    # ── DWI ──────────────────────────────────────────────────────────────────
    dwi_pgsebruker = create_key(
        "sub-{subject}/{session}/dwi/sub-{subject}_{session}_acq-pgsebruker_dwi"
    )
    dwi_multidwienc = create_key(
        "sub-{subject}/{session}/dwi/sub-{subject}_{session}_acq-multidwienc_dwi"
    )

    # ── MEGRE QSM (9 echoes) ─────────────────────────────────────────────────
    megre_qsm_mag = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-qsm_part-mag_MEGRE"
    )
    megre_qsm_mag_denoised = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-qsm_rec-denoised_part-mag_MEGRE"
    )
    megre_qsm_complex = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-qsm_run-{item:02d}_MEGRE"
    )

    # ── MP2RAGE ──────────────────────────────────────────────────────────────
    mp2rage_uni = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_rec-bruker_UNI"
    )
    mp2rage_4d = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_MP2RAGE"
    )

    # ── Structural ───────────────────────────────────────────────────────────
    mtw = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-6p5uT5p5kHz_MTw"
    )
    mtw_denoised = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-6p5uT5p5kHz_rec-denoised_MTw"
    )
    t1w_flash = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-flash_T1w"
    )
    t1w_flash_denoised = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-flash_rec-denoised_T1w"
    )
    t1w_refmt = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-refMT_T1w"
    )
    t1w_refmt_denoised = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-refMT_rec-denoised_T1w"
    )
    t2w = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-rare_T2w"
    )
    t2w_denoised = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-rare_rec-denoised_T2w"
    )

    info = {
        dwi_pgsebruker:          [],
        dwi_multidwienc:         [],
        megre_qsm_mag:           [],
        megre_qsm_mag_denoised:  [],
        megre_qsm_complex:       [],
        mp2rage_uni:             [],
        mp2rage_4d:              [],
        mtw:                     [],
        mtw_denoised:            [],
        t1w_flash:               [],
        t1w_flash_denoised:      [],
        t1w_refmt:               [],
        t1w_refmt_denoised:      [],
        t2w:                     [],
        t2w_denoised:            [],
    }

    # Track already-mapped descriptions to distinguish raw vs denoised.
    # seqinfo is ordered by series_id (ascending), so first hit = raw,
    # second hit = Bruker-denoised reconstruction.
    seen = set()

    for s in seqinfo:
        desc  = s.series_description or ""
        itype = s.image_type

        # ── DWI ──────────────────────────────────────────────────────────────
        if fnmatch.fnmatch(desc, "Diff3D_10b0_30B2k_45B4k_60B6k_125iso*"):
            info[dwi_pgsebruker].append(s.series_id)

        elif fnmatch.fnmatch(desc, "Diff3D_OGSE_uFA_150iso*"):
            info[dwi_multidwienc].append(s.series_id)

        # ── MEGRE QSM 9-Echo ─────────────────────────────────────────────────
        elif fnmatch.fnmatch(desc, "Gre3D_QSM_9Echo_ISO100_1A*"):
            if s.dim3 == 720:
                if ("megre_mag",) not in seen:
                    info[megre_qsm_mag].append(s.series_id)
                    seen.add(("megre_mag",))
                elif ("megre_mag_denoised",) not in seen:
                    info[megre_qsm_mag_denoised].append(s.series_id)
                    seen.add(("megre_mag_denoised",))
            elif s.dim3 == 2880:
                info[megre_qsm_complex].append(s.series_id)   # if two complex files are available so it's two reconstruction not a second run 

        # ── MP2RAGE ──────────────────────────────────────────────────────────────
        # series_description = "MP2RAGE_2Echo_100iso" (protocol_name = "cfmmMPRAGE").
        # UNI : dim3=100 (volume 3D unique). INV1+INV2 : dim3=200 (concatenated → 4D 100x2).
        elif fnmatch.fnmatch(s.series_description or "", "MP2RAGE_2Echo_100iso*"):
            if s.dim3 == 100:
                key = ("mp2rage_uni",)
                if key not in seen:
                    info[mp2rage_uni].append(s.series_id)
                    seen.add(key)
            elif s.dim3 == 200:
                key = ("mp2rage_4d",)
                if key not in seen:
                    info[mp2rage_4d].append(s.series_id)
                    seen.add(key)

        # ── MTw ──────────────────────────────────────────────────────────────
        elif fnmatch.fnmatch(desc, "MT3D_6p5uT_5p5kHz_100iso*"):
            if ("mtw",) not in seen:
                info[mtw].append(s.series_id)
                seen.add(("mtw",))
            elif ("mtw_denoised",) not in seen:
                info[mtw_denoised].append(s.series_id)
                seen.add(("mtw_denoised",))

        # ── T1w FLASH ────────────────────────────────────────────────────────
        elif fnmatch.fnmatch(desc, "T1_FLASH3D_50iso*"):
            if ("t1w_flash",) not in seen:
                info[t1w_flash].append(s.series_id)
                seen.add(("t1w_flash",))
            elif ("t1w_flash_denoised",) not in seen:
                info[t1w_flash_denoised].append(s.series_id)
                seen.add(("t1w_flash_denoised",))

        # ── T1w RefMT ────────────────────────────────────────────────────────
        elif fnmatch.fnmatch(desc, "RefT13D_100iso*") and float(s.TR) < 1000:
            key = ("t1w_refmt",)
            if key not in seen:
                info[t1w_refmt].append(s.series_id)
                seen.add(key)
            elif ("t1w_refmt_denoised",) not in seen:
                info[t1w_refmt_denoised].append(s.series_id)
                seen.add(("t1w_refmt_denoised",))

        # ── T2w RARE ─────────────────────────────────────────────────────────
        elif fnmatch.fnmatch(desc, "T2w3D_RAREvfl_100iso*"):
            if ("t2w",) not in seen:
                info[t2w].append(s.series_id)
                seen.add(("t2w",))
            elif ("t2w_denoised",) not in seen:
                info[t2w_denoised].append(s.series_id)
                seen.add(("t2w_denoised",))

    return info