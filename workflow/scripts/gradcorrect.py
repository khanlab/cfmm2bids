"""
Run gradient nonlinearity correction using the gradcorrect BIDS app.

Sets up a local BIDS input directory (with symlinks) containing only the
target subject/session, runs gradcorrect on it, then moves the corrected
subject/session directory to the final output location.

Note: the `snakemake` object is injected automatically by Snakemake's
script directive and is not imported explicitly.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from lib import utils

log_file = snakemake.log[0] if snakemake.log else None
logger = utils.setup_logger(log_file)

bids_subj_dir_in = Path(snakemake.input.bids_subj_dir)
bids_subj_dir_out = Path(snakemake.output.bids_subj_dir)
dataset_description = Path(snakemake.input.dataset_description)
bidsignore = Path(snakemake.input.bidsignore)
grad_coeff_file = snakemake.params.grad_coeff_file

subject = snakemake.wildcards.subject
session = snakemake.wildcards.session

logger.info(f"Running gradcorrect for sub-{subject}/ses-{session}")

with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)

    # --- Set up local BIDS input directory with symlinks ---
    local_bids_in = tmpdir / "bids_in"
    local_bids_in.mkdir()

    # Symlink top-level BIDS files
    (local_bids_in / "dataset_description.json").symlink_to(
        dataset_description.resolve()
    )
    (local_bids_in / ".bidsignore").symlink_to(bidsignore.resolve())

    # Symlink the subject directory (create sub-* parent first)
    subj_dir = local_bids_in / f"sub-{subject}"
    subj_dir.mkdir()
    (subj_dir / f"ses-{session}").symlink_to(bids_subj_dir_in.resolve())

    logger.info(f"Local BIDS input: {local_bids_in}")

    # --- Set up local BIDS output directory ---
    local_bids_out = tmpdir / "bids_out"
    local_bids_out.mkdir()

    logger.info(f"Local BIDS output: {local_bids_out}")

    # --- Run gradcorrect, capturing output to log file ---
    cmd = [
        "run.sh",
        str(local_bids_in),
        str(local_bids_out),
        "participant",
        "--grad-coeff-file",
        str(grad_coeff_file),
    ]
    logger.info(f"Running command: {' '.join(cmd)}")

    with open(log_file, "a") if log_file else open("/dev/null", "w") as log_fh:
        result = subprocess.run(
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
        )

    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd)

    # --- Move the corrected sub/ses to the final output location ---
    corrected_subj_dir = local_bids_out / f"sub-{subject}" / f"ses-{session}"

    if not corrected_subj_dir.exists():
        raise FileNotFoundError(
            f"Expected gradcorrect output not found: {corrected_subj_dir}"
        )

    bids_subj_dir_out.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Moving {corrected_subj_dir} -> {bids_subj_dir_out}")
    shutil.move(str(corrected_subj_dir), str(bids_subj_dir_out))

logger.info(f"gradcorrect complete for sub-{subject}/ses-{session}")
