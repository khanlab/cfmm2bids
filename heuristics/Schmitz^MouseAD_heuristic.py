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
    t1w = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_run-{item:01d}_T1w"
    )

    t2w = create_key(
        "sub-{subject}/{session}/anat/sub-{subject}_{session}_run-{item:01d}_T2w"
    )

    # ==================================================================================================================
    # resting-state
    # change PE and RPE when find out what the phase encoding direction is

    fMRI_PA = create_key(
        "sub-{subject}/{session}/func/sub-{subject}_{session}_task-rest_dir-PA_run-{item:01d}_bold"
    )

    fMRI_AP = create_key(
        "sub-{subject}/{session}/func/sub-{subject}_{session}_task-rest_dir-AP_run-{item:01d}_bold"
    )

    #  ==================================================================================================================

    info = {
        t1w: [],
        t2w: [],
        fMRI_PA: [],
        fMRI_AP: [],
    }

    # extract the digits of the name to separate
    # you can even add the videos
    # magnitude data has name: 170001, phase: 170002
    # reverse phase and normal phase
    # we need the json files as well
    # TODO: no of volumes
    # trying to get the denopised version which is usually x0002
    for _idx, s in enumerate(seqinfo):
        if s.series_description == "MT_GRE3D_ISO150_6A":
            info[t1w].append(s.series_id)

        if s.series_description == "T2_100x100x500_AX_24A":
            info[t2w].append(s.series_id)

        # ==================================================rest========================================================
        # if the name does not contain "_RV_" then it is a normal phase

        if s.series_description == "T2star_rsFMRI_3x3x500_AX_192x96_Sat_DIR-PA_TOPUP":
            info[fMRI_PA].append(s.series_id)
        # RPE is reverse phase encoding
        if s.series_description == "T2star_rsFMRI_3x3x500_AX_192x96_Sat_DIR-AP":
            info[fMRI_AP].append(s.series_id)

        #

    return info
