# cfmm2bids

A Snakemake workflow for converting CFMM DICOM data to BIDS format using heudiconv.

## Features

- Download DICOM studies from CFMM
- Convert DICOM to BIDS format using heudiconv
- Generate quality control (QC) reports for each subject/session
- Optional reorientation of images to a specified orientation (e.g., RIA)

## QC Reports

The workflow automatically generates QC reports for each subject/session after heudiconv conversion. The reports include:

1. **Series List** (`*_series.svg`): A detailed table showing each series with:
   - Series ID and description
   - Protocol name
   - Image dimensions
   - TR and TE values
   - Corresponding BIDS filename (or "NOT MAPPED" if unmapped)

2. **Unmapped Summary** (`*_unmapped.svg`): A summary of series that were not mapped to BIDS, helping identify potential missing data or heuristic issues

QC reports are saved in the `sourcedata/qc/` directory with the structure:
```
sourcedata/qc/
└── sub-{subject}/
    └── ses-{session}/
        ├── sub-{subject}_ses-{session}_series.svg
        └── sub-{subject}_ses-{session}_unmapped.svg
```

**Note:** The QC report generation is integrated into the Snakemake workflow as a script directive and cannot be run manually as a standalone CLI tool.

## Reorientation

The workflow can optionally reorient all NIfTI images to a specified orientation. This is controlled by the `reorient` section in `config.yml`:

```yaml
reorient:
  do_reorient: True
  orientation: 'RIA'  # Target orientation (e.g., RAS, RIA, LAS, etc.)
```

When enabled, the workflow will:
1. Process all NIfTI images in `bids/sub-{subject}/ses-{session}` directories
2. Apply the specified reorientation transformation to the affine matrix
3. Write reoriented images to `bids_reorient/sub-{subject}/ses-{session}` directories
4. Copy all non-NIfTI files (JSON sidecars, etc.) to maintain BIDS structure

The reorientation uses the following orientation codes:
- **R**ight, **L**eft: First axis (left-right)
- **A**nterior, **P**osterior: Second axis (front-back)
- **S**uperior, **I**nferior: Third axis (top-bottom)

Common orientations:
- **RAS**: Standard neurological orientation (Right-Anterior-Superior)
- **RIA**: Right-Inferior-Anterior
- **LAS**: Left-Anterior-Superior

Set `do_reorient: False` or omit the `reorient` section to disable this feature.

## Usage

1. Install [pixi](https://pixi.sh/latest/installation/)
   ```bash
   curl -fsSL https://pixi.sh/install.sh | sh
   ```
2. Clone the [cfmm2bids repository](https://github.com/akhanf/cfmm2bids)
   ```bash
   git clone https://github.com/akhanf/cfmm2bids
   cd cfmm2bids
   ```
3. Install dependencies into pixi virtual environment
   ```bash
   pixi install
   ```
4. Configure your search specifications by editing the `config.yml`
5. Run the workflow as a dry-run:
   ```bash
   pixi run snakemake --dry-run
6. Run the workflow on local cores:
   ```bash
   pixi run snakemake --cores all
   ```
7. Run the workflow on a SLURM system:
   ```bash
   pixi run snakemake --executor slurm 
   ```   

## Output Directory Structure

```
.
├── bids/                       # BIDS-formatted output
│   └──sub-*/ses-*/            # BIDS session directories
├── bids_reorient/              # Reoriented images (if enabled)
│   └──sub-*/ses-*/            # Reoriented BIDS session directories
└── sourcedata/                 # Source DICOM data
    ├── sub-*/ses-*/           # Downloaded DICOMs
    ├── heudiconv/             # Heudiconv metadata
    └── qc/                    # QC reports
```

## Repository Directory Structure
```
├── workflow/                  # Workflow files
│   ├── Snakefile              # Snakemake workflow
│   ├── lib/                   # Python module with helper functions
│   └── scripts/               # Workflow scripts 
├── resources/                 # Configuration files
│   ├── heuristic.py          # Heudiconv heuristic
│   └── dcm2niix_config.json  # dcm2niix configuration
└── config.yml                # Workflow configuration
```

