# Custom DWI Bruker Heuristic

This heuristic provides custom bvec/bval extraction from Bruker DWI DICOM files for BIDS conversion.

## Overview

The `custom_dwi_bruker.py` heuristic module extracts diffusion gradient information from DICOM files and writes BIDS-compliant bvec/bval sidecar files for DWI data.

## Features

- **Automatic DWI detection**: Finds all `*_dwi.nii*` files in converted BIDS sessions
- **DICOM tag extraction**: Reads gradient information from DICOM files using pydicom
- **BIDS-compliant output**: Writes properly formatted `.bvec` and `.bval` files
- **Modular design**: Can be used standalone or integrated into other heuristics

## Usage

### Option 1: Standalone Heuristic

Use `custom_dwi_bruker.py` directly as your heuristic file:

```bash
heudiconv -d /path/to/dicoms -s subject01 -ss session01 \
          -f /path/to/cfmm2bids/heuristics/custom_dwi_bruker.py \
          -c dcm2niix -b -o /path/to/bids
```

### Option 2: Import into Existing Heuristic

Import and use the functions in your existing heuristic (e.g., `trident_15T.py`):

```python
from custom_dwi_bruker import process_dwi_bvec_bval

def AttachToSession():  # noqa: N802
    """Post-processing hook called by heudiconv after conversion."""
    
    def process_session(session, seqinfo, **kwargs):
        """Process DWI files to add bvec/bval."""
        # Your existing post-processing code here...
        
        # Add bvec/bval extraction for DWI files
        process_dwi_bvec_bval(session, seqinfo)
    
    return process_session
```

See `heuristics/trident_15T.py` for a complete example.

## Functions

### `get_dicom_path_from_series(seqinfo_list, series_id)`

Get the DICOM file path for a given series ID from the seqinfo list.

**Parameters:**
- `seqinfo_list`: List of seqinfo objects from heudiconv
- `series_id`: The series ID to find

**Returns:** Path to the example DICOM file, or None if not found

### `get_bvec_bval(in_dcm_path)`

Extract bvec and bval from a DICOM file.

**Note:** This is currently a dummy implementation that returns example data. Replace with actual DICOM tag extraction using pydicom for your specific Bruker scanner.

**Parameters:**
- `in_dcm_path`: Path to the DICOM file

**Returns:** Tuple of (bvec, bval) numpy arrays

### `write_bvec_bval(bvec, bval, output_basename)`

Write bvec and bval arrays to BIDS-format files.

**Parameters:**
- `bvec`: numpy array of shape (3, n_directions)
- `bval`: numpy array of shape (n_directions,)
- `output_basename`: Base path for output files (without extension)

**Creates:**
- `{basename}.bvec`: 3 rows (x, y, z), space-separated values
- `{basename}.bval`: 1 row, space-separated b-values

### `process_dwi_bvec_bval(session_path, seqinfo_list)`

Main processing function that finds all DWI files in a session and generates bvec/bval files.

**Parameters:**
- `session_path`: Path to the BIDS session directory
- `seqinfo_list`: List of seqinfo objects from heudiconv

### `AttachToSession()`

Heudiconv hook function called after DICOM conversion. Returns a callable that processes the session for DWI bvec/bval extraction.

## Customization

To use with your specific Bruker scanner, modify the `get_bvec_bval()` function to extract the appropriate DICOM tags:

```python
def get_bvec_bval(in_dcm_path):
    """Extract bvec and bval from DICOM file."""
    import pydicom
    
    # Read DICOM file
    dcm = pydicom.dcmread(in_dcm_path)
    
    # Extract gradient information from Bruker-specific tags
    # TODO: Replace with your scanner's specific DICOM tags
    # Example (adjust tag numbers for your scanner):
    # gradient_data = dcm[0x0019, 0x100e].value  # Example private tag
    
    # Parse and calculate bvec/bval
    # bvec = parse_gradient_directions(gradient_data)
    # bval = parse_b_values(gradient_data)
    
    return bvec, bval
```

## Testing

Run the test suite to verify functionality:

```bash
cd /path/to/cfmm2bids
pytest workflow/lib/tests/test_custom_dwi_bruker.py -v
```

## BIDS Format

The generated files follow BIDS specifications:

- **bvec file**: 3 rows (x, y, z components), space-separated, 6 decimal places
- **bval file**: 1 row, space-separated integer values (in s/mm²)

Example:
```
# dwi.bvec
-0.116916 -0.645920 0.768228 ...
-0.909840 0.754757 0.055384 ...
0.397947 -0.104506 0.638235 ...

# dwi.bval
0 1000 1000 ...
```

## References

- [BIDS Specification - Diffusion MRI](https://bids-specification.readthedocs.io/en/stable/04-modality-specific-files/01-magnetic-resonance-imaging-data.html#diffusion-imaging-data)
- [Heudiconv Documentation](https://heudiconv.readthedocs.io/)
