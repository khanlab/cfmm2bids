# Import bruker custom_callable for extracting bval/bvec from dicoms
from custom.bruker import custom_callable  # noqa: F401


def create_key(template, outtype=("nii.gz",), annotation_classes=None):
    if template is None or not template:
        raise ValueError("Template must be a valid format string")
    return template, outtype, annotation_classes


def filter_files(fl):
    if fl.endswith(".dcm"):
        # better to add the StackId and the rest of info separately, otherwise it messes up the header
        pass
    return fl


# -------------------------------------------------------------------------------------------------
# ONE helper: "collect candidates -> sort -> assign by position in repeating pattern"
def assign_series_by_pattern(
    seqinfo,
    *,
    match,  # predicate: match(s) -> bool
    keys,  # tuple/list of heudiconv keys in acquisition order (e.g., (orig, den), (mag,swi,phase))
    info,  # the heudiconv info dict to append into
    exclude=None,  # optional predicate: exclude(s) -> bool
    sort_key=lambda s: s.series_id,
    handled=None,  # optional set to track handled series_ids
    drop_incomplete_tail=False,
):
    """
    Assign matching series to BIDS keys by repeating positional pattern.

    Example patterns:
      keys=(t2w_rare_orig, t2w_rare_den)  -> pairs (orig, denoised)
      keys=(t2starw_mag, t2starw_swi, t2starw_phase) -> triplets (mag, swi, phase)

    Controls:
      - exclude: remove e.g. NON_PARALLEL complex data
      - drop_incomplete_tail: if True, ignore trailing incomplete group (useful for robustness)

    Returns:
      list of series_id that were assigned (handy for marking handled)
    """
    cands = []
    for s in seqinfo:
        if s.series_id in handled:
            print(f"{s.series_id} already handled, skipping")
            continue
        if not match(s):
            print(f"{s.series_id} not matched, skipping")
            continue
        if exclude is not None and exclude(s):
            print(f"{s.series_id} excluded, skipping")
            continue
        print(f"appending {s.series_id} to list of candidates")
        cands.append(s)

    cands.sort(key=sort_key)

    n = len(keys)
    if n == 0:
        print("no candidates, returning []")
        return []

    # Optionally drop trailing partial group to avoid "shift" if acquisition is incomplete
    usable = (len(cands) // n) * n if drop_incomplete_tail else len(cands)

    print(f"usable candidates: {cands[:usable]}")

    assigned = []
    for i, s in enumerate(cands[:usable]):
        k = keys[i % n]
        print(f"assigning {s.series_id} to key {info[k]}")
        info[k].append(s.series_id)
        assigned.append(s.series_id)

        if handled is not None:
            handled.add(s.series_id)

    print(f"assigned {assigned}")
    return assigned


def infotodict(seqinfo):
    """
    Heuristic evaluator for determining which runs belong where
    allowed template fields - follow python string module:
      item: index within category
      subject: participant id
      seqitem: run number during scanning
      subindex: sub index within group
    """
    # anatomical
    t2w_tse = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-TSE_run-{item:01d}_T2w"
    )

    t2w_rarevfl_orig = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-RAREVFL_rec-orig_run-{item:01d}_T2w"
    )
    t2w_rarevfl_den = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-RAREVFL_rec-denoised_run-{item:01d}_T2w"
    )

    t2w_turborare_orig = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-TurboRARE_rec-orig_run-{item:01d}_T2w"
    )
    t2w_turborare_den = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-TurboRARE_rec-denoised_run-{item:01d}_T2w"
    )

    t2w_gre = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-GRE_run-{item:01d}_T2starw"
    )

    t2w_gre_mag = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-GRE_rec-orig_run-{item:01d}_part-mag_T2starw"
    )
    t2w_gre_phase = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-GRE_rec-orig_run-{item:01d}_part-phase_T2starw"
    )
    t2w_gre_den = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-GRE_rec-denoised_run-{item:01d}_part-mag_T2starw"
    )

    t2w_pregad_orig = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-PreGadGRE_rec-orig_run-{item:01d}_T2starw"
    )
    t2w_postgad_orig = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-PostGadGRE_rec-orig_run-{item:01d}_T2starw"
    )
    t2w_pregad_den = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-PreGadGRE_rec-denoised_run-{item:01d}_T2starw"
    )
    t2w_postgad_den = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-PostGadGRE_rec-denoised_run-{item:01d}_T2starw"
    )

    t2starw_mag = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-FLASH_run-{item:01d}_part-mag_T2starw"
    )
    t2starw_swi = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-FLASH_rec-SWI_run-{item:01d}_T2starw"
    )
    t2starw_phase = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-FLASH_run-{item:01d}_part-phase_T2starw"
    )

    tof = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-TOF_run-{item:01d}_angio"
    )

    # resting-state
    func_resting_R = create_key(
        "sub-{subject}/{session}/func/sub-{subject}_{session}_task-rest_dir-PA_run-{item:01d}_bold"
    )
    func_resting_RV = create_key(
        "sub-{subject}/{session}/func/sub-{subject}_{session}_task-rest_dir-AP_run-{item:01d}_bold"
    )

    # diffusion
    dwi = create_key(
        "sub-{subject}/{session}/dwi/sub-{subject}_{session}_run-{item:01d}_dwi"
    )

    info = {
        t2w_tse: [],
        t2w_gre: [],
        t2w_gre_mag: [],
        t2w_gre_phase: [],
        t2w_gre_den: [],
        t2w_rarevfl_orig: [],
        t2w_rarevfl_den: [],
        t2w_turborare_orig: [],
        t2w_turborare_den: [],
        t2starw_mag: [],
        t2starw_swi: [],
        t2starw_phase: [],
        tof: [],
        t2w_pregad_orig: [],
        t2w_postgad_orig: [],
        t2w_pregad_den: [],
        t2w_postgad_den: [],
        func_resting_R: [],
        func_resting_RV: [],
        dwi: [],
    }

    handled = set()

    # ---------------------------------------------------------------------------------------
    # Main assignment loop for everything else
    for s in seqinfo:
        if s.series_id in handled:
            continue
        if "gre" in s.series_description.lower():
            info[t2w_gre].append(s.series_id)


        elif "tse2d" in s.series_description:
            info[t2w_tse].append(s.series_id)

        elif "TOF3D" in s.series_description:
            info[tof].append(s.series_id)

        # Resting-state
        elif "rsfMRI" in s.series_description:
            if "RPE" in s.series_description:
                info[func_resting_RV].append(s.series_id)
            else:
                info[func_resting_R].append(s.series_id)

        # Diffusion
        elif ("dwi" in s.series_description.lower()) or (
            "diff3d" in s.series_description.lower()
        ):
            info[dwi].append(s.series_id)

    return info
