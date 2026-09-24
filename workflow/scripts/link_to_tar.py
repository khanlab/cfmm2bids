import os
from pathlib import Path

from lib import utils

log_file = snakemake.log[0] if snakemake.log else None
logger = utils.setup_logger(log_file)


output_dir = Path(snakemake.output.dicoms_dir)
output_dir.mkdir(parents=True, exist_ok=True)

# Create symlinks to all tar files from the cached UID directories
for cached_dir in snakemake.input.cached_dirs:
    cached_path = Path(cached_dir)
    for tar_file in cached_path.glob("*.tar*"):
        symlink_path = output_dir / tar_file.name
        # Create relative symlink for portability
        relative_target = os.path.relpath(tar_file, output_dir)
        symlink_path.symlink_to(relative_target)


# Log the operation
logger.info("Symlinked tar files from cached UIDs:")
for cached_dir in snakemake.input.cached_dirs:
    logger.info(f"{cached_dir}")
