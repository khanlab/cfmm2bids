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
- Link SPIM (lightsheet microscopy) datasets to the BIDS output *(experimental, under active development)*

## Workflow Stages

The workflow is organized into 5 main processing stages (plus optional gradcorrect and SPIM linkage stages) and a final copy stage, each producing intermediate outputs:

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
Downloads DICOM studies from CFMM using `cfmm2tar`. The workflow uses a centralized download cache to avoid re-downloading the same data:

- **Download Cache** (`results/download_cache` by default): Downloaded tar files are stored here, indexed by `StudyInstanceUID`
- **Subject/Session Directories** (`dicoms/sub-*/ses-*/`): These contain symlinks to the cached tar files

This two-tier structure ensures that:
- If the same study (UID) is needed for multiple subject/session combinations, it's only downloaded once
- When `merge_duplicate_studies: true` is enabled, multiple studies for the same subject/session are linked as separate tar files in the subject/session directory

Output: 
- `download_cache/{StudyInstanceUID}/` - Cached tar archives indexed by UID
- `dicoms/sub-*/ses-*/` - Subject/session directories with symlinks to cached tar files

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
- **gen_mp2rage_uni_den**: Generate a noise-robust MP2RAGE UNI-DEN T1w image from UNI, INV1, and INV2

Outputs:
- `bids-staging/sub-*/ses-*/` - Intermediate fixed BIDS data per subject/session
- `bids/` - Assembled fixed BIDS dataset (all subjects combined)
- `qc/sub-*/ses-*/sub-*_ses-*_provenance.json` - Fix provenance tracking
- `qc/bids_validator.json` - Post-fix BIDS validation results
- `qc/aggregate_report.html` - Aggregate QC report including fix provenance

### 6. Gradcorrect Stage (`results/5_gradcorr`) (optional)
Applies gradient nonlinearity correction using the [gradcorrect BIDS app](https://github.com/khanlab/gradcorrect).
Enabled via the `gradcorrect.enable: true` config option. Requires Singularity/Apptainer and a
gradient coefficient file (`gradcorrect.grad_coeff_file`).

When enabled, the corrected per-subject/session directories replace the fix-stage directories
as input for the final BIDS assembly.

Outputs:
- `bids-staging/sub-*/ses-*/` - Gradient-corrected BIDS data per subject/session

#### Uncorrected BIDS dataset (optional)
When gradcorrect is enabled, you can also request that the uncorrected (fix-stage) BIDS dataset
be assembled alongside the gradient-corrected one by setting `gradcorrect.create_bids_uncorr: true`.
This is useful because:
- The gradient-corrected dataset has been resampled, so the raw data may be needed for some analyses.
- Some series are dropped by gradcorrect (e.g. series with online distortion correction applied by
  the scanner), and these will still be present in the uncorrected dataset.

The uncorrected dataset is written to `final_bids_uncorr_dir` (default: `bids_uncorr`).

### 7. SPIM Linkage (optional, experimental)

> **⚠️ Note:** This feature is still under active development and may change in future versions.

The workflow supports linking SPIM (Single-Plane Illumination Microscopy / lightsheet) datasets
into the final MRI BIDS output directory. This is useful for studies where the same subjects
have both MRI and ex-vivo lightsheet microscopy data, and you want a single unified BIDS dataset.

When enabled (`link_to_spim: true`), the workflow will:
1. Query the specified SPIM BIDS directory for each configured session using [snakebids](https://github.com/akhanlab/snakebids)
2. Find subjects that exist in both the MRI and SPIM datasets
3. Create symlinks in the final BIDS output directory pointing to the SPIM files
   (e.g., OME-Zarr image files and their JSON sidecar metadata)

The `spim` config is a dictionary keyed by **session label**. Multiple sessions (e.g., different
ex-vivo acquisition batches) can be defined, each pointing to a separate SPIM BIDS directory.

**Requirements:**
- The SPIM data must already be organized in BIDS format (e.g., produced by a lightsheet pipeline)
- Subject IDs must match between the MRI and SPIM BIDS datasets
- The `snakebids` Python package must be available (included in the pixi environment)

**Example configuration:**
```yaml
link_to_spim: true

spim:
  exvivo:
    # Output path template relative to sub-{subject}/ses-{session}/ in the final BIDS dir
    out_path: micr/sub-{subject}_ses-{session}_sample-brain_acq-imaris4x_SPIM

    # Path to the SPIM BIDS dataset directory
    bids_dir: /path/to/spim/bids

    # pybids input specifications to locate the SPIM files
    pybids_inputs:
      ome_zarr:
        filters:
          suffix: 'SPIM'
          extension: 'ome.zarr'
          sample: brain
          acquisition: 'imaris4x'
        wildcards:
          - subject
      json:
        filters:
          suffix: 'SPIM'
          extension: 'json'
          sample: brain
          acquisition: 'imaris4x'
        wildcards:
          - subject
```

For a working example, see `config/trident/ki3.yml`.

### 8. Final Stage (`bids/`)
Copies the validated and fixed BIDS dataset to the final output directory.
When gradcorrect is enabled, gradient-corrected data is used. If `gradcorrect.create_bids_uncorr`
is also enabled, the uncorrected data is additionally copied to `bids_uncorr/` (or the path set
by `final_bids_uncorr_dir`).

Note: the workflow will not automatically clean-up subjects/sessions in the final output folder. To do this explicitly, run with the `--forcerun clean`, or `-R clean` option.

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

#### Using Format Strings

You can use the `format` option to reformat the extracted (and sanitized/remapped) value with additional text. Use `{value}` as the placeholder for the current processed value. This is applied after all other processing steps (`premap`, `pattern`, `sanitize`, `map`, `fillna`).

```yaml
metadata_mappings:
  subject:
    source: PatientID
    pattern: '_([^_]+)$'    # Regex to extract subject ID
    sanitize: true          # Remove non-alphanumeric characters
    format: "AA{value}"     # Prepend "AA" to the extracted subject ID
  session:
    source: StudyDate
    sanitize: true
    format: "{value}T"      # Append "T" to the session value
```

This is useful when you need to add a prefix, suffix, or otherwise reformat the extracted value. For example, `format: "AA{value}"` would turn `"001"` into `"AA001"`.

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
- `download_cache`: Centralized cache directory for downloaded tar files, indexed by StudyInstanceUID (default: `results/download_cache`)

#### Download Cache

The workflow uses a centralized download cache to optimize performance and avoid redundant downloads:

- **Cache Location**: By default `results/download_cache`, configurable via the `download_cache` config option
- **Indexing**: Tar files are stored by their `StudyInstanceUID`, not by subject/session
- **Symlinking**: Subject/session directories (`dicoms/sub-*/ses-*/`) contain symlinks to cached tar files
- **Benefit**: If the same study (UID) appears with different subject/session mappings, it's only downloaded once

Example scenario where caching helps:
- Study UID `1.2.3.4` originally mapped to `sub-01/ses-01`
- Config is updated to map the same UID to `sub-pilot/ses-scanner01`
- The tar file is reused from cache without re-downloading

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

  - name: gen_mp2rage_uni_den
    pattern: "anat/*_UNIT1.nii.gz"
    action: gen_mp2rage_uni_den
    multiplying_factor: 6   # optional, default 6 (range 1-10)
    output_acq: MP2RAGEpostproc  # optional, controls acq- entity in output filename

  - name: import_offline_sp2d
    action: copy_from_path
    src: "/path/to/recons/*_SNSX_{subject}/cb_sp2d_diff.nii.gz"
    dst: "dwi/sub-{subject}_ses-{session}_acq-sp2d_dwi.nii.gz"
    required: true

  - name: import_offline_sp2d_bundle
    action: copy_from_path
    src:
      - "/path/to/recons/*_SNSX_{subject}/cb_sp2d_diff.nii.gz"
      - "/path/to/recons/*_SNSX_{subject}/cb_sp2d_diff.bval"
      - "/path/to/recons/*_SNSX_{subject}/cb_sp2d_diff.bvec"
    dst:
      - "dwi/sub-{subject}_ses-{session}_acq-sp2d_dwi.nii.gz"
      - "dwi/sub-{subject}_ses-{session}_acq-sp2d_dwi.bval"
      - "dwi/sub-{subject}_ses-{session}_acq-sp2d_dwi.bvec"
    required: true
```

For most fixes, `pattern` is required and matching files are searched in the BIDS
session directory. Session-scoped fixes such as `copy_from_path` do not use
`pattern`; they run once per subject/session, format `{subject}`/`{session}` in
`src` and `dst`, then expand glob wildcards in `src`. Globs follow shell-style
rules (`*`, `?`, `[abc]`/`[0-9]`), and recursive matching requires `**`. Curly
braces are reserved for `{subject}` and `{session}` template variables (literal
brace matching is not supported; if needed, point `src` at a directory/symlink
without braces). `src` should be an absolute path. `src` and `dst` can each be
either a string or a list of strings; list mode uses zipped `src[i] -> dst[i]`.

### Other Options
- `final_bids_dir`: Final output directory (default: `bids`)
- `stages`: Customize intermediate stage directories

### SPIM Linkage Configuration (`link_to_spim` / `spim`)

> **⚠️ Note:** This feature is still under active development and may change in future versions.

Enable SPIM linkage to include lightsheet microscopy data alongside MRI data in the BIDS output:

```yaml
link_to_spim: true

spim:
  # Key is the session label for SPIM subjects in the output BIDS dataset
  exvivo:
    # Output path template relative to sub-{subject}/ses-{session}/ in final BIDS dir
    # Only {subject} and {session} wildcards are supported
    out_path: micr/sub-{subject}_ses-{session}_sample-brain_acq-imaris4x_SPIM

    # Path to the SPIM BIDS dataset directory
    bids_dir: /path/to/spim/bids

    # pybids input specifications to locate the SPIM files
    pybids_inputs:
      ome_zarr:
        filters:
          suffix: 'SPIM'
          extension: 'ome.zarr'
          sample: brain
          acquisition: 'imaris4x'
        wildcards:
          - subject
      json:
        filters:
          suffix: 'SPIM'
          extension: 'json'
          sample: brain
          acquisition: 'imaris4x'
        wildcards:
          - subject
```

Multiple sessions (e.g., different acquisition batches) can be defined under the `spim` key.
Subjects with no matching MRI data will generate a warning but will not cause the workflow to fail.
See `config/trident/ki3.yml` for a real-world example with multiple batches.

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
│   ├── config_cogms.yml       # Example: CogMS study configuration
│   └── trident/               # Example configs with SPIM linkage (experimental)
│       └── ki3.yml            # Example: Trident 15T + SPIM linkage configuration
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
