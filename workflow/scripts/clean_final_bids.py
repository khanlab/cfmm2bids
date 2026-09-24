"""Clean the final BIDS directory by removing extraneous files."""

import shutil
from pathlib import Path

from lib import utils

log_file = snakemake.log[0] if snakemake.log else None
logger = utils.setup_logger(log_file)

# Get the final BIDS directory from the output
clean_marker = Path(snakemake.output.clean_marker)
final_bids_dir = clean_marker.parent

# Get expected subjects from inputs
expected_subjects = set()
for session_dir in snakemake.input.session_dirs:
    # Extract subject from path like "bids/sub-123/ses-456"
    parts = Path(session_dir).parts
    for part in parts:
        if part.startswith("sub-"):
            expected_subjects.add(part)
            break

# Find all subject directories in the final BIDS directory
actual_subjects = set()
if final_bids_dir.exists():
    for item in final_bids_dir.iterdir():
        if item.is_dir() and item.name.startswith("sub-"):
            actual_subjects.add(item.name)

# Remove extraneous subjects
extraneous_subjects = actual_subjects - expected_subjects
if extraneous_subjects:
    logger.info(f"Removing extraneous subjects: {extraneous_subjects}")
    for subject in extraneous_subjects:
        subject_path = final_bids_dir / subject
        logger.info(f"Removing {subject_path}")
        shutil.rmtree(subject_path)
else:
    logger.info("No extraneous subjects found.")

# Also check for extraneous session directories within subjects
for subject in expected_subjects:
    subject_path = final_bids_dir / subject
    if not subject_path.exists():
        continue

    # Get expected sessions for this subject
    expected_sessions = set()
    for session_dir in snakemake.input.session_dirs:
        session_path = Path(session_dir)
        if subject in session_path.parts:
            # Extract session from path
            for part in session_path.parts:
                if part.startswith("ses-"):
                    expected_sessions.add(part)
                    break

    # Find actual sessions
    actual_sessions = set()
    for item in subject_path.iterdir():
        if item.is_dir() and item.name.startswith("ses-"):
            actual_sessions.add(item.name)

    # Remove extraneous sessions
    extraneous_sessions = actual_sessions - expected_sessions
    if extraneous_sessions:
        logger.info(f"Removing extraneous sessions in {subject}: {extraneous_sessions}")
        for session in extraneous_sessions:
            session_path = subject_path / session
            logger.info(f"Removing {session_path}")
            shutil.rmtree(session_path)

logger.info("Clean operation completed.")
