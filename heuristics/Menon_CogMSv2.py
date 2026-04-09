from cfmm_base import create_key
from cfmm_base import infotodict as cfmminfodict


def infotodict(seqinfo):
    """Heuristic evaluator for determining which runs belong where
    allowed template fields - follow python string module:
    item: index within category
    subject: participant id
    seqitem: run number during scanning
    subindex: sub index within group
    """

    # call cfmm for general labelling and get dictionary
    info = cfmminfodict(seqinfo)

    # create functional keys
    bold_mag_ap = create_key(
        "{bids_subject_session_dir}/func/{bids_subject_session_prefix}_task-rest_dir-AP_run-{item:02d}_part-mag_bold"
    )
    bold_phase_ap = create_key(
        "{bids_subject_session_dir}/func/{bids_subject_session_prefix}_task-rest_dir-AP_run-{item:02d}_part-phase_bold"
    )

    bold_mag_pa = create_key(
        "{bids_subject_session_dir}/func/{bids_subject_session_prefix}_task-rest_dir-PA_run-{item:02d}_part-mag_bold"
    )
    bold_phase_pa = create_key(
        "{bids_subject_session_dir}/func/{bids_subject_session_prefix}_task-rest_dir-PA_run-{item:02d}_part-phase_bold"
    )

    bold_sbref_ap = create_key(
        "{bids_subject_session_dir}/fmap/{bids_subject_session_prefix}_dir-AP_epi"
    )
    bold_sbref_pa = create_key(
        "{bids_subject_session_dir}/fmap/{bids_subject_session_prefix}_dir-PA_epi"
    )

    # add functional keys to the dictionary
    info[bold_mag_ap] = []
    info[bold_phase_ap] = []
    info[bold_sbref_ap] = []
    info[bold_mag_pa] = []
    info[bold_phase_pa] = []
    info[bold_sbref_pa] = []

    for _idx, s in enumerate(seqinfo):
        # bold
        if "bold" in s.protocol_name:
            if "_PA" in s.series_description:
                if s.dim4 > 2 and ("M" in s.image_type[2].strip()):
                    info[bold_mag_pa].append({"item": s.series_id})
                if s.dim4 > 2 and ("P" in s.image_type[2].strip()):
                    info[bold_phase_pa].append({"item": s.series_id})
                if s.dim4 <= 2 and "SBRef" in (s.series_description).strip():
                    info[bold_sbref_pa].append({"item": s.series_id})
            elif "_AP" in s.series_description:
                if s.dim4 > 2 and ("M" in s.image_type[2].strip()):
                    info[bold_mag_ap].append({"item": s.series_id})
                if s.dim4 > 2 and ("P" in s.image_type[2].strip()):
                    info[bold_phase_ap].append({"item": s.series_id})
                if s.dim4 <= 2 and "SBRef" in (s.series_description).strip():
                    info[bold_sbref_ap].append({"item": s.series_id})

    return info
