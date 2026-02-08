# Import bruker custom_callable for extracting bval/bvec from dicoms
from custom.bruker import custom_callable  # noqa: F401



# ======================================================================================================================
def create_key(template, outtype=("nii.gz",), annotation_classes=None):
    if template is None or not template:
        raise ValueError("Template must be a valid format string")

    return template, outtype, annotation_classes


# ======================================================================================================================
def filter_files(fl):
    if fl.endswith(".dcm"):
        # better to add the SatckId and the rest of info separately, otherwise it messes up the header
        pass
    return fl


# ======================================================================================================================
def infotodict(seqinfo):
    """Heuristic evaluator for determining which runs belong where
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
    t2w_rare_orig = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-RARE_rec-orig_run-{item:01d}_T2w"
    )
    t2w_rare_den = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-RARE_rec-denoised_run-{item:01d}_T2w"
    )

    t2starw_flash = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_acq-FLASH_run-{item:01d}_T2starw"
    )

    mp2rage = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_run-{item:01d}_MP2RAGE"
    )

    mtsat = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_run-{item:01d}_MTS"
    )

    # ==================================================================================================================
    #megre
    megre_orig = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_rec-orig_run-{item:01d}_MEGRE"
    )
    megre_den = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_rec-denoised_run-{item:01d}_MEGRE"
    )



    # ==================================================================================================================
    # diffusion
    dwi = create_key(
        "sub-{subject}/{session}/dwi/sub-{subject}_{session}_dir-AP_run-{item:01d}_dwi"
    )
    dwi_rpe = create_key(
        "sub-{subject}/{session}/dwi/sub-{subject}_{session}_dir-PA_run-{item:01d}_dwi"
    )


    # ==================================================================================================================

    info = {
        t2w_tse: [],
        t2starw_flash: [],
        t2w_rare_orig: [],
        t2w_rare_den: [],
        megre_orig: [],
        megre_den: [],
        mp2rage: [],
        mtsat: [],
        dwi: [],
        dwi_rpe: [],
    }


    # T2w RARE is also similar, but we have the original, then the denoised
    # First: collect candidate T2w RARE
    t2w_rare_candidates = []
    for s in seqinfo:
        desc = s.series_description.lower()
        if "t2_rarevfl" in desc:
            t2w_rare_candidates.append(s)

    # Sort by series_id to ensure acquisition order
    t2w_rare_candidates = sorted(t2w_rare_candidates, key=lambda x: x.series_id)

    # Assign triplets sequentially: mag, swi, phase
    for i, s in enumerate(t2w_rare_candidates):
        pos = i % 2
        if pos == 0:
            info[t2w_rare_orig].append(s.series_id)
        elif pos == 1:
            info[t2w_rare_den].append(s.series_id)

    # --- MEGRE, raw then denoised
    # First: collect candidate MEGRE
    megre_candidates = []
    for s in seqinfo:
        desc = s.series_description.lower()
        if "mge" in desc:
            print('adding MGE scan to MEGRE candidates')
            print(s)
            megre_candidates.append(s)

    # Sort by series_id to ensure acquisition order
    megre_candidates = sorted(megre_candidates, key=lambda x: x.series_id)

    # Assign triplets sequentially: mag, swi, phase
    for i, s in enumerate(megre_candidates):
        pos = i % 2
        if pos == 0:
            info[megre_orig].append(s.series_id)
        elif pos == 1:
            info[megre_den].append(s.series_id)


    # ---------------------------------------------------------------------------------------

    for _idx, s in enumerate(seqinfo):
        if "tse2d" in s.series_description:
            info[t2w_tse].append(s.series_id)

        elif "t2star_flash" in s.series_description.lower():
            info[t2starw_flash].append(s.series_id)

        elif "mp2rage" in s.series_description.lower():
            info[mp2rage].append(s.series_id)

        elif "MT" in s.series_description:
            info[mtsat].append(s.series_id)


        elif (
            "dwi" in s.series_description.lower()
            or "diff3d" in s.series_description.lower()
            or "dtiepi" in s.series_description.lower()
        ):
            if 'rpe' in s.series_description.lower() or 'rv' in s.series_description.lower():
                info[dwi_rpe].append(s.series_id)
            else:
                info[dwi].append(s.series_id)


    return info
