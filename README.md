# cfmm2bids

A Snakemake workflow for converting CFMM DICOM data to BIDS format using heudiconv.

## Features

- Query DICOM studies from CFMM with flexible search specifications
- Filter studies with include/exclude rules
- Download DICOM studies from CFMM
- Convert DICOM to BIDS format using heudiconv
- Apply post-conversion fixes (remove files, update JSON metadata, fix NIfTI orientation)
- Validate BIDS datasets
- Generate quality control (QC) reports for each subject/session

## Workflow Stages

The workflow is organized into 5 main processing stages plus a final copy stage, each producing intermediate outputs:

**Note on BIDS staging:** The convert and fix stages use a two-step assembly process:
1. Individual subject/session data is first written to `bids-staging/sub-*/ses-*/` directories
2. All requested subjects are then assembled into a single `bids/` directory
This ensures the BIDS dataset is always clean and matches the requested subjects, making it easier to add/remove subjects without leftover files.

### 1. Query Stage (`results/0_query`)
Queries DICOM studies from CFMM using search specifications defined in `config/config.yaml`. Features include:
- Multiple search specifications with different query parameters
- Flexible metadata mapping (e.g., extract subject/session from PatientID, StudyDate)
- Pattern matching with regex extraction
- Automatic sanitization of subject/session IDs
- Validation of subject/session ID format (alphanumeric only)
- **Query caching**: Queries are cached based on a hash of the query parameters. If the `studies.tsv` file already exists and query parameters haven't changed, the query is skipped. This is especially useful when using remote executors like SLURM, where multiple jobs querying simultaneously can cause issues.
- Use `--config force_requery=true` to force a fresh query when new scans may have been acquired

Output: `studies.tsv` - Complete list of matched studies

### 2. Filter Stage (`results/1_filter`)
Post-filters the queried studies based on include/exclude rules. Features include:
- Include/exclude filters using pandas query syntax
- Optional `--config head=N` to process only first N subjects for testing

Output: `studies_filtered.tsv` - Filtered list of studies to process

### 3. Download Stage (`results/2_download`)
Downloads DICOM studies from CFMM using `cfmm2tar`. When `merge_duplicate_studies: true` is enabled, multiple studies for the same subject/session are downloaded as separate tar files in the same directory.

Output: `dicoms/sub-*/ses-*/` - Downloaded DICOM files (tar archives)

### 4. Convert Stage (`results/3_convert`)
Converts DICOMs to BIDS format using heudiconv and generates QC reports. Features include:
- BIDS conversion with heudiconv and custom heuristic
- Automatic handling of duplicate studies (when `merge_duplicate_studies: true`):
  - Each tar file (study) is processed separately with heudiconv
  - Outputs are automatically merged into a single session
  - A `study_uid` column is added to dicominfo.tsv to track series origin
- QC report generation (series list and unmapped summary)
- BIDS validation with `bids-validator-deno`
- Metadata preservation (auto.txt, dicominfo.tsv)

Outputs:
- `bids-staging/sub-*/ses-*/` - Intermediate BIDS-formatted data per subject/session
- `bids/` - Assembled BIDS dataset (all subjects combined)
- `qc/sub-*/ses-*/` - Heudiconv metadata and QC reports (auto.txt, dicominfo.tsv, series.svg, unmapped.svg)
- `qc/bids_validator.json` - BIDS validation results
- `qc/aggregate_report.html` - Aggregate QC report for all sessions

### 5. Fix Stage (`results/4_fix`)
Applies post-conversion fixes to the BIDS dataset. Available fix actions:
- **remove**: Remove files matching a pattern (e.g., unwanted fieldmaps)
- **update_json**: Update JSON sidecar metadata (e.g., add PhaseEncodingDirection)
- **fix_orientation**: Reorient NIfTI files to canonical RAS+ orientation

Outputs:
- `bids-staging/sub-*/ses-*/` - Intermediate fixed BIDS data per subject/session
- `bids/` - Assembled fixed BIDS dataset (all subjects combined)
- `qc/sub-*/ses-*/sub-*_ses-*_provenance.json` - Fix provenance tracking
- `qc/bids_validator.json` - Post-fix BIDS validation results
- `qc/aggregate_report.html` - Aggregate QC report including fix provenance

### 6. Final Stage (`bids/`)
Copies the validated and fixed BIDS dataset to the final output directory.

## QC Reports

The workflow automatically generates QC reports for each subject/session after heudiconv conversion. The reports include:

1. **Series List** (`*_series.svg`): A detailed table showing each series with:
   - Series ID and description
   - Protocol name
   - Image dimensions
   - TR and TE values
   - Corresponding BIDS filename (or "NOT MAPPED" if unmapped)
   - For merged studies: includes `study_uid` to identify which study each series came from

2. **Unmapped Summary** (`*_unmapped.svg`): A summary of series that were not mapped to BIDS, helping identify potential missing data or heuristic issues

QC reports are saved in: `results/3_convert/qc/sub-{subject}/ses-{session}/`

**Note:** The QC report generation is integrated into the Snakemake workflow as a script directive and cannot be run manually as a standalone CLI tool.

### Aggregate HTML Report

After the fix stage, an aggregate HTML report is automatically generated that consolidates QC information from all subjects and sessions. The report includes:

- **Overview Statistics**: Total subjects, sessions, series, and unmapped series count
- **BIDS Validation Results**: Validation results from both convert and fix stages
- **Aggregated Series Table**: All series data sorted by subject and session
- **Post-Conversion Fix Provenance**: Details of fixes applied to each session
- **Heudiconv Filegroup Metadata**: Detailed metadata from heudiconv conversion (collapsible)

The aggregate report is located at: `results/4_fix/qc/aggregate_report.html`

This report provides a comprehensive overview of the entire dataset conversion process and is useful for quality control and troubleshooting.

## Configuration

The workflow is configured via `config/config.yaml`. Key configuration sections include:

For working examples, see:
- `config/config_trident15T.yml` - Configuration for Trident 15T scanner
- `config/config_cogms.yml` - Configuration for CogMS study

### Query Configuration (`search_specs`)
Define one or more DICOM queries with metadata mappings:
```yaml
search_specs:
  - dicom_query:
      study_description: YourStudy^*
      study_date: 20230101-
    metadata_mappings:
      subject:
        source: PatientID        # Extract from PatientID field
        pattern: '_([^_]+)$'    # Regex to extract subject ID
        sanitize: true          # Remove non-alphanumeric characters
      session:
        source: StudyDate       # Use StudyDate as session ID
```

#### Using Constant Values

You can use the `constant` option to set all subjects or sessions to a fixed value instead of extracting from DICOM fields. This is useful when:
- All data should use the same session label (e.g., all scans from the same scanner like "15T")
- Running a single-subject study where all data belongs to the same subject (e.g., "pilot")

```yaml
metadata_mappings:
  subject:
    source: PatientID
    pattern: '_([^_]+)$'
    sanitize: true
  session:
    constant: '15T'  # All sessions will be labeled as 'ses-15T'
```

When `constant` is specified, it takes precedence over any `source` field, which can be omitted or will be ignored. The constant value is applied to all matching studies.

### Filter Configuration (`study_filter_specs`)
Post-filter studies with include/exclude rules:
```yaml
study_filter_specs:
  include:
    - "subject.str.startswith('sub')"  # Include only subjects starting with 'sub'
  exclude:
    - "StudyInstanceUID == '1.2.3.4.5'"  # Exclude specific study
```

### Download Configuration
- `cfmm2tar_download_options`: Options passed to cfmm2tar (e.g., `--skip-derived`)
- `credentials_file`: Path to CFMM credentials file
- `merge_duplicate_studies`: If `true`, automatically merge multiple studies for the same subject/session (default: `false`)

#### Merging Duplicate Studies

When `merge_duplicate_studies: true` is enabled and multiple studies match the same subject/session:
- All study tar files are downloaded to the same directory
- Each study's DICOM tar file is processed separately with heudiconv
- Outputs from each study are automatically merged into a single session:
  - BIDS NIfTI and JSON files from all studies are combined
  - The `auto.txt` files are merged (all series info concatenated)
  - The `dicominfo.tsv` files are merged with a `study_uid` column added to track which series came from which study
- This is useful when subjects have multiple scan sessions on the same day (e.g., due to console reboot or scanner issues)
- If disabled and duplicates are found, the workflow will fail with an error message

### Convert Configuration
- `heuristic`: Path to heudiconv heuristic file
- `dcmconfig_json`: Path to dcm2niix configuration
- `heudiconv_options`: Additional heudiconv options

#### Available Heuristics

The workflow includes several heuristic files for different scanner configurations:

- **`heuristics/cfmm_base.py`**: Base CFMM heuristic supporting standard sequences including:
  - MP2RAGE, MEMP2RAGE, Sa2RAGE
  - T2 TSE (Turbo Spin Echo)
  - T2 SPACE, T2 FLAIR
  - Multi-echo GRE
  - TOF Angiography
  - Diffusion-weighted imaging
  - BOLD fMRI (multiband, psf-dico)
  - Field mapping (EPI-PA, GRE)
  - **DIS2D/DIS3D distortion-corrected reconstructions** - Improved detection that robustly identifies distortion-corrected images regardless of their position in the DICOM image_type metadata
  
- **`heuristics/trident_15T.py`**: Trident 15T scanner-specific heuristic
- **`heuristics/Menon_CogMSv2.py`**: CogMS study-specific heuristic

The heuristics automatically detect and label distortion-corrected (DIS2D/DIS3D) reconstructions using the `rec-DIS2D` or `rec-DIS3D` BIDS suffix.

### Fix Configuration (`post_convert_fixes`)
Define fixes to apply after conversion:
```yaml
post_convert_fixes:
  - name: remove_fieldmaps
    pattern: "fmap/*dir-AP*"
    action: remove
    
  - name: add_phase_encoding
    pattern: "func/*bold.json"
    action: update_json
    updates:
      PhaseEncodingDirection: "j-"
      
  - name: reorient_nifti
    pattern: "anat/*T1w.nii.gz"
    action: fix_orientation
```

### Other Options
- `final_bids_dir`: Final output directory (default: `bids`)
- `stages`: Customize intermediate stage directories

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
4. Configure your search specifications by editing the `config/config.yaml`
   
   **Note:** Example configurations are available:
   - `config/config_trident15T.yml` - Trident 15T scanner setup
   - `config/config_cogms.yml` - CogMS study setup
   
   You can use these as starting points or use the template in `config/config.yaml`.
   
   To use one of the example configs directly:
   ```bash
   pixi run snakemake --configfile config/config_trident15T.yml --dry-run
   ```

5. Run the workflow as a dry-run to see what will be executed:
   ```bash
   pixi run snakemake --dry-run
   ```

6. Run specific workflow stages or the full workflow:
   
   **Run all stages (query → filter → download → convert → fix → final)**:
   ```bash
   pixi run snakemake --cores all
   ```
   
   **Run only download stage**:
   ```bash
   pixi run snakemake download --cores all
   ```
   
   **Run only convert stage** (includes QC reports):
   ```bash
   pixi run snakemake convert --cores all
   ```
   
   **Run only fix stage**:
   ```bash
   pixi run snakemake fix --cores all
   ```
   
   **Process only the first subject** (useful for testing):
   ```bash
   pixi run snakemake --config head=1 --cores all
   ```
   
   **Process only first N subjects** (e.g., first 3):
   ```bash
   pixi run snakemake -C head=3 --cores all
   ```

7. Run the workflow on a SLURM cluster:
   ```bash
   pixi run snakemake --executor slurm --jobs 10
   ```   

## Output Directory Structure

### Final BIDS Output
```
bids/                           # Final BIDS-formatted output
├── dataset_description.json    # BIDS dataset metadata
└── sub-*/
    └── ses-*/                  # Subject/session data (anat/, func/, fmap/, etc.)
```

### Intermediate Stages
```
results/
├── 0_query/
│   └── studies.tsv                              # All queried studies
├── 1_filter/
│   └── studies_filtered.tsv                     # Filtered studies to process
├── 2_download/
│   └── dicoms/
│       └── sub-*/ses-*/                         # Downloaded DICOM tar files
├── 3_convert/
│   ├── bids-staging/
│   │   ├── dataset_description.json            # BIDS dataset metadata
│   │   ├── .bidsignore                         # BIDS ignore file
│   │   └── sub-*/ses-*/                        # Per-subject/session BIDS data (intermediate)
│   ├── bids/                                   # Assembled BIDS dataset (all subjects)
│   └── qc/
│       ├── sub-*/ses-*/                        # Per-subject/session QC and metadata
│       │   ├── sub-*_ses-*_auto.txt           # Heudiconv auto conversion info
│       │   ├── sub-*_ses-*_dicominfo.tsv      # Heudiconv DICOM metadata table
│       │   ├── sub-*_ses-*_series.tsv         # Series info table
│       │   ├── sub-*_ses-*_series.svg         # Series QC visualization
│       │   ├── sub-*_ses-*_unmapped.svg       # Unmapped series visualization
│       │   └── sub-*_ses-*_report.html        # Individual subject/session report
│       ├── bids_validator.json                # BIDS validation results
│       └── aggregate_report.html              # Aggregate QC report
└── 4_fix/
    ├── bids-staging/
    │   ├── dataset_description.json            # BIDS dataset metadata
    │   ├── .bidsignore                         # BIDS ignore file
    │   └── sub-*/ses-*/                        # Per-subject/session fixed BIDS data (intermediate)
    ├── bids/                                   # Assembled fixed BIDS dataset (all subjects)
    └── qc/
        ├── sub-*/ses-*/                        # Per-subject/session provenance
        │   ├── sub-*_ses-*_provenance.json    # Fix provenance tracking
        │   └── sub-*_ses-*_report.html        # Individual subject/session report with fixes
        ├── bids_validator.json                # Post-fix validation results
        ├── final_bids_validator.txt           # Final validation (must pass)
        └── aggregate_report.html              # Aggregate QC report with fix provenance
```

## Repository Directory Structure
```
├── workflow/                   # Workflow files
│   ├── Snakefile              # Main Snakemake workflow
│   ├── lib/                   # Python modules
│   │   ├── query_filter.py   # DICOM query and filtering functions
│   │   ├── bids_fixes.py     # Post-conversion fix implementations
│   │   ├── convert.py        # Heudiconv conversion helpers (single/multi-study)
│   │   └── utils.py          # Utility functions
│   └── scripts/               # Workflow scripts
│       ├── run_heudiconv.py                   # Run heudiconv (handles single/multi-study)
│       ├── generate_convert_qc_figs.py       # QC report generation
│       ├── generate_subject_report.py        # Individual subject/session reports
│       ├── generate_aggregate_all_report.py  # Aggregate QC report
│       └── post_convert_fix.py               # Post-conversion fix application
├── heuristics/                 # Heudiconv heuristic files
│   ├── cfmm_base.py           # Base CFMM heuristic (supports DIS2D/DIS3D reconstruction)
│   ├── trident_15T.py         # Trident 15T scanner-specific heuristic
│   └── Menon_CogMSv2.py       # CogMS study-specific heuristic
├── resources/                  # Resource files
│   ├── dcm2niix_config.json   # dcm2niix configuration
│   └── dataset_description.json  # BIDS dataset metadata template
├── heuristics/                 # Heudiconv heuristics
│   ├── cfmm_base.py           # Base heuristic for CFMM data
│   ├── trident_15T.py         # Example: Trident 15T scanner heuristic
│   └── Menon_CogMSv2.py       # Example: CogMS study heuristic
├── config/                     # Configuration files
│   ├── config.yml             # Configuration template (customize this)
│   ├── config_trident15T.yml  # Example: Trident 15T scanner configuration
│   └── config_cogms.yml       # Example: CogMS study configuration
└── pixi.toml                  # Pixi project configuration and dependencies
```

## Available Target Rules

The workflow provides several target rules for running specific stages:

- `all` (default): Run all stages from query to final BIDS output
- `head`: Process only the first subject (useful for testing)
- `download`: Run only query, filter, and download stages
- `convert`: Run through convert stage (includes download, conversion, and QC)
- `fix`: Run through fix stage (includes all above plus post-conversion fixes)

Example usage:
```bash
# Test with first subject only
pixi run snakemake -C head=1 --cores all

# Download all DICOMs without conversion
pixi run snakemake download --cores all

# Convert and generate QC reports
pixi run snakemake convert --cores all
```

## Testing

The repository includes unit and integration tests to ensure code quality and workflow correctness.

### Running Tests

```bash
# Run all tests
pytest workflow/lib/tests/ -v

# Run unit tests only (test individual functions)
pytest workflow/lib/tests/test_bids_fixes.py -v

# Run integration tests (test workflow with Snakemake dry-run)
pytest workflow/lib/tests/test_integration.py -v
```

### Test Structure

- **Unit tests** (`test_bids_fixes.py`): Test individual functions in the bids_fixes module
- **Integration tests** (`test_integration.py`): Test the complete Snakemake workflow using dry-run mode
- **Test fixtures** (`workflow/lib/tests/fixtures/`): Sample data for testing
  - `sample_studies.tsv`: Mock query results 
  - `test_config.yml`: Test configuration file

### Integration Testing Approach

The integration tests use Snakemake's dry-run mode (`--dry-run` flag) to validate that:
- The workflow can parse successfully without errors
- All stages (query, filter, download, convert, fix) can be planned
- The workflow correctly handles pre-generated TSV query outputs

This approach allows testing the workflow without requiring:
- CFMM server access or credentials
- Actual DICOM data
- Full workflow execution (which would be time-consuming)

The tests use pre-populated query results (TSV files) to simulate the query stage, allowing the workflow to proceed through planning all subsequent stages.

### CI/CD

Tests run automatically on every push and pull request via GitHub Actions:
- Lint checks (ruff)
- Code formatting checks (ruff, snakefmt)
- Unit tests
- Integration tests (dry-run)

