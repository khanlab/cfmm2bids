# cfmm2bids

A Snakemake workflow for converting CFMM DICOM data to BIDS format using heudiconv.

## Features

- Download DICOM studies from CFMM
- Convert DICOM to BIDS format using heudiconv
- Generate quality control (QC) reports for each subject/session
- Generate comprehensive summary reports with interactive visualizations

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

## Summary Reports

The workflow can generate comprehensive summary reports for each subject/session that aggregate information from all processing stages. To generate summary reports, run:

```bash
pixi run snakemake --cores all report
```

Each summary report includes:

1. **Interactive HTML Report** (`report.html`): An interactive table rendered with [datavzrd](https://datavzrd.github.io/) containing:
   - Metadata summary (subject, session, conversion statistics)
   - Post-conversion fixes applied
   - Interactive table of all DICOM series with BIDS mappings
   - Visualization of mapping statistics and imaging parameters

2. **Aggregated JSON** (`*_summary.json`): Machine-readable metadata including:
   - Summary statistics (total series, mapped/unmapped counts)
   - Processing stage information
   - Applied post-conversion fixes

3. **Aggregated TSV** (`*_summary.tsv`): Tab-separated table with detailed series information

Summary reports are saved in the `results/5_report/` directory with the structure:
```
results/5_report/
└── sub-{subject}/
    └── ses-{session}/
        ├── report.html
        ├── sub-{subject}_ses-{session}_summary.json
        └── sub-{subject}_ses-{session}_summary.tsv
```


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
│   └──sub-*/ses-*/            # Subject/session data
├── results/                    # Intermediate processing results
│   ├── 0_query/               # Initial DICOM query results
│   ├── 1_filter/              # Filtered study list
│   ├── 2_download/            # Downloaded DICOMs
│   ├── 3_convert/             # Heudiconv conversion outputs
│   │   ├── bids/              # Initial BIDS conversion
│   │   ├── info/              # Conversion metadata
│   │   └── qc/                # QC reports (SVG figures)
│   ├── 4_fix/                 # Post-conversion fixes
│   │   ├── bids/              # Fixed BIDS data
│   │   └── info/              # Fix provenance
│   └── 5_report/              # Summary reports
│       └── sub-*/ses-*/       # Interactive HTML reports
└── sourcedata/                 # Source DICOM data (deprecated)
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

