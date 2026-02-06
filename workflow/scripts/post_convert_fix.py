import json
import shutil
import stat
import traceback
from pathlib import Path

from lib import bids_fixes, utils

log_file = snakemake.log[0] if snakemake.log else None
logger = utils.setup_logger(log_file)

logger.info(bids_fixes.describe_available_fixes())

src = Path(snakemake.input.bids_subj_dir)
dst = Path(snakemake.output.bids_subj_dir)
fixes = snakemake.params.fixes

logger.info(f"Fixing dataset for {src.name} → {dst}")


# --- Helper functions ---
def make_tree_writable(path: Path):
    """Recursively make files and dirs under `path` writable by owner."""
    for p in [path] + list(path.rglob("*")):
        try:
            mode = p.stat().st_mode
            p.chmod(mode | stat.S_IWUSR)
        except Exception as e:
            logger.info(f"⚠️ Could not make writable: {p} ({e})")


# --- Always do a normal copy ---
logger.info("📂 Copying source tree...")
shutil.copytree(src, dst)  # full, independent copy

# --- Make writable before applying fixes ---
logger.info("🔧 Making copied tree writable...")
make_tree_writable(dst)


num_changes = 0
fixes_used = []
if fixes is not None:
    for fix in fixes:
        name = fix.get("name", "unnamed_fix")
        pattern = fix["pattern"]
        action = fix["action"]

        meta = bids_fixes.FIX_REGISTRY.get(action)

        if meta is None:
            raise ValueError(f"Unknown fix type: {action}")

        func = meta.get("func")
        grouped = bool(meta.get("grouped", False))

        logger.info(f"\n=== Applying fix: {name} ({action}) ===")
        matches = list(dst.rglob(pattern))
        if not matches:
            logger.info(f"  ⚠️ No matches for pattern: {pattern}")
            continue

        try:
            if grouped:
                # pass the whole list of Path objects and the fix dict
                added = func(matches, fix)
                num_changes += added
                logger.info(f"  grouped handler returned: {added}")
            else:
                # per-file handler: call once per match
                for path in matches:
                    try:
                        changed = func(path, fix)
                    except Exception:
                        logger.error(f"  Exception running handler for {path}:")
                        logger.error(traceback.format_exc())
                        changed = False
                    if changed:
                        num_changes += 1
        except Exception:
            logger.error(f"  Exception running fix '{name}' ({action}):")
            logger.error(traceback.format_exc())
            # continue to next fix

    fixes_used = [f["action"] for f in fixes]

logger.info(f"✅ Done with {src.name}: {num_changes} files modified.")


# Optional lightweight provenance per subject/session
Path(snakemake.output.prov_json).write_text(
    json.dumps(
        {
            "subject": snakemake.wildcards.subject,
            "session": snakemake.wildcards.session,
            "fixes_used": fixes_used,
            "files_modified": num_changes,
        },
        indent=2,
    )
)
