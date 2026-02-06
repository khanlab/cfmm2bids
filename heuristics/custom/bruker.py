import contextlib
import logging
from io import StringIO
from pathlib import Path

import numpy as np
import pydicom

logger = logging.getLogger(__name__)


def reformat(data):
    """
    Convert data into integer or floating point data

    :param data:
    :return:
    """
    with contextlib.suppress(AttributeError):
        data = data.decode("utf-8")

    if data.isdecimal():
        return int(data)
    else:
        try:
            return float(data)
        except ValueError:
            # not a float
            pass

        if data.startswith("(") and data.endswith(")"):
            data = [
                reformat(x.strip()) for x in data.lstrip("(").rstrip(")").split(",")
            ]
        elif data == "Yes":
            return True
        elif data == "No":
            return False

    return data


def jcamp_parse(data):
    jcamp_dict = {}
    variable = None

    for line in data:
        check = line.lstrip()

        # Skip comment lines
        if check.startswith("$$"):
            pass
        # Line starts a new variable
        elif check.startswith("##"):
            lhs, _, rhs = check.strip("##").partition("=")

            # Stop reading when end is found
            if lhs.lower() == "end":
                break

            variable = [rhs.rstrip("\n")]
            jcamp_dict[lhs] = variable
        # Line is a data line to append to the previous variable
        elif variable:
            variable.append(line.rstrip("\n"))

    # All variables have now been read

    # Parse the contents of the variables
    for key, value in jcamp_dict.items():
        # If the variable starts with ( then combine all the lines until the first one that ends with )
        # TODO:
        # Edge case when variable is a struct of structs. A contained struct might end a line and therefore exit
        # prematurely before the containing struct is complete. Fixing requires parsing the entire contents because
        # the struct could contain strings with parenthesis. This requires a char by char parser which is considerably
        # more difficult for an extremely unlikely occurrence.
        has_struct = False
        if value[0].lstrip().startswith("("):
            has_struct = True
            first_line = ""
            line = value[0]

            # Concatenate lines until one that ends in ) is reached
            for line in value:
                first_line += line
                if line.rstrip().endswith(")"):
                    break

            # Combine all the rest of the lines into one long data string
            data = "".join(value[value.index(line) + 1 :])
            value = [first_line, data] if data else [first_line]

        if len(value) == 1:
            # Only one line in data so just parse the data
            jcamp_dict[key] = reformat(value[0])
        elif has_struct:
            # Data has multiple lines, so the first line is the dimensions of the array of data
            # Read the dimensions
            dim = [int(x.strip()) for x in value[0].lstrip("(").rstrip(")").split(",")]

            data = value[1]
            if data.lstrip().startswith("("):
                # Second line starts with ( so there is an array of structs
                data = [
                    [reformat(y.strip()) for y in x.lstrip("(").rstrip(")").split(",")]
                    for x in data.split(") (")
                ]
            elif len(dim) == 1 and data.lstrip().startswith("<"):
                # Second line start with < so it is a string and the dimensions are the maximum length
                jcamp_dict[key] = {"maximum_length": dim[0], "value": data}
                continue
            else:
                # Second line is an array of data. Split on whitespace and reformat each entry.
                data = [reformat(x) for x in data.split()]

            jcamp_dict[key] = {"dim": dim, "value": data}

    return jcamp_dict


def jcamp_read(data):
    if not isinstance(data, bytes) or isinstance(data, str):
        # Try to use data as a filename
        try:
            with open(data) as fh:
                return jcamp_parse(fh)
        except OSError as err:
            if err.errno != 63:
                raise
        except (TypeError, ValueError):
            # Was not a valid filename, so continue trying other options
            pass

    # It was not a filename, so it should be a string
    # Make sure that data is str and not bytes
    try:
        data = data.decode("utf-8")
    except AttributeError:
        # Was not a bytes so it did not have decode attribute
        pass

    # Convert to IO object which permits iterating through string on linebreaks
    try:
        handle = StringIO(data)
    except TypeError:
        # Was not a str object so assume it is a list of lines
        handle = data

    # Parse the data
    return jcamp_parse(handle)


class JCAMPData(dict):
    def __init__(self, data, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update(jcamp_read(data))

    def __str__(self):
        return "\n".join([f"{key} = {value}" for key, value in self.items()])

    def format(self, variable):
        data = self[variable]
        if "dim" in data:
            a = np.empty((len(data["value"]), 1))
            for counter, value in enumerate(data["value"]):
                a[counter] = value
            data = np.reshape(a, data["dim"])
        elif "maximum_length" in data:
            data = str(data["value"])

        return data


def get_bvec_bval(in_dcm_path):
    """
    Extract diffusion gradient directions (bvec) and b-values (bval) from a
    Bruker DICOM file.

    The function expects a Bruker diffusion-weighted DICOM where the private
    tag (0x0177, 0x1100) contains a JCAMP-DX encoded "method" header. From
    this header it reads the following fields:

    - ``"$PVM_DwEffBval"``: 1D sequence of effective b-values (s/mm^2).
    - ``"$PVM_DwDir"``: flat sequence of gradient directions; its length must
      be a multiple of 3 and is reshaped to (3, n_directions).
    - ``"$PVM_DwBMat"``: flat sequence of 3x3 diffusion weighting matrices;
      its length must be a multiple of 9 and is reshaped to (9, n_directions).

    The ``"$PVM_DwDir"`` vectors are used together with the singular value
    decomposition (SVD) of the ``"$PVM_DwBMat"`` matrices to determine the
    final gradient directions. If the number of b-values is larger than the
    number of input direction vectors, additional zero vectors are inserted
    for b0 volumes (except for OGSE protocols with 55 b-values, where the b0
    volume is assumed to be included in ``"$PVM_DwDir"``).

    Parameters
    ----------
    in_dcm_path : str or pathlib.Path
        Path to the Bruker diffusion-weighted DICOM file.

    Returns
    -------
    tuple[numpy.ndarray, numpy.ndarray]
        (bvec, bval) where:

        - bvec: numpy array of shape (3, n_directions) containing the final,
          polarity-corrected gradient directions.
        - bval: numpy array of shape (n_directions,) containing the
          corresponding b-values.
    """
    # Extract bvec/bval information from the Bruker-specific method header
    # encoded in the DICOM private tag (0x0177, 0x1100).
    logger.info(f"Extracting bvec/bval from DICOM: {in_dcm_path}")

    # read dicom header
    H = pydicom.dcmread(in_dcm_path, stop_before_pixels=True)

    # read bruker headers (private tag 0x0177,0x1100 may be absent)
    elem = H.get((0x0177, 0x1100))
    if elem is None or not getattr(elem, "value", None):
        logger.warning(
            "Bruker private tag (0x0177,0x1100) missing or empty in %s; "
            "skipping bvec/bval extraction.",
            in_dcm_path,
        )
        return None, None

    try:
        method = jcamp_parse(elem.value.decode("utf-8").splitlines())
    except (AttributeError, UnicodeDecodeError) as exc:
        logger.warning(
            "Failed to parse Bruker private header in %s: %s; "
            "skipping bvec/bval extraction.",
            in_dcm_path,
            exc,
        )
        return None, None
    # Bvalue information
    bval = method["$PVM_DwEffBval"]["value"]
    bvec = method["$PVM_DwDir"]["value"]
    bvec = np.reshape(bvec, (int(len(bvec) / 3 + 0.5), 3)).T
    bmat = method["$PVM_DwBMat"]["value"]
    bmat = np.reshape(bmat, (int(len(bmat) / 9 + 0.5), 9)).T

    # Determine bvec from bmat
    bmat = np.transpose(bmat)
    bvecFromMat = np.zeros((len(bval), 3))
    for idx, row in enumerate(bmat):
        row = np.reshape(row, (3, 3))
        u, s, vh = np.linalg.svd(row, full_matrices=True)
        bvecFromMat[idx] = vh[0]

    # Get polarity of bvec correct based on input vectors (since polarity is arbitrary after svd)
    bvec = np.transpose(bvec)
    if len(bval) > len(bvec):
        # Fill in b0 acquisitions that were not in input dir vector
        for _n in range(len(bval) - len(bvec)):
            idx = np.argsort(bval)
            if (
                len(bval) != 55
            ):  # if not OGSE -- not needed for OGSE since b0 is included in dir vector
                bvec = np.insert(bvec, idx[0], 0, axis=0)
    for idx, dir_n in enumerate(bvec):
        mind1 = np.argmax(np.abs(dir_n))
        mind2 = np.argmax(np.abs(bvecFromMat[idx]))
        fact = np.sign(dir_n[mind1] * bvecFromMat[idx][mind2])
        if fact < 0:
            bvecFromMat[idx] = fact * bvecFromMat[idx]

    bvecFromMat = np.transpose(bvecFromMat)

    logger.info(f"Extracted {len(bval)} gradient directions")
    return bvecFromMat, bval


def write_bvec_bval(bvec, bval, output_basename):
    """
    Write bvec and bval arrays to BIDS-format files.

    BIDS format:
    - bvec: 3 rows (x, y, z), space-separated values
    - bval: 1 row, space-separated values

    Parameters
    ----------
    bvec : numpy.ndarray
        Array of shape (3, n_directions) with gradient directions
    bval : numpy.ndarray
        Array of shape (n_directions,) with b-values
    output_basename : str or Path
        Base path for output files (without extension)
        Will create {basename}.bvec and {basename}.bval
    """
    output_basename = Path(output_basename)

    # Write bvec file (3 rows, space-separated)
    bvec_file = output_basename.with_suffix(".bvec")
    with open(bvec_file, "w") as f:
        for row in range(3):
            row_values = " ".join(f"{val:.6f}" for val in bvec[row, :])
            f.write(row_values + "\n")
    logger.info(f"Wrote bvec file: {bvec_file}")

    # Write bval file (1 row, space-separated)
    bval_file = output_basename.with_suffix(".bval")
    with open(bval_file, "w") as f:
        bval_values = " ".join(f"{int(val)}" for val in bval)
        f.write(bval_values + "\n")
    logger.info(f"Wrote bval file: {bval_file}")


def process_dwi_bvec_bval(session_path, seqinfo_list):
    """
    Process all DWI files in a session and generate bvec/bval files.

    This function finds all *_dwi.nii* files in the session directory,
    extracts the gradient information from corresponding DICOM files,
    and writes bvec/bval sidecar files.

    Parameters
    ----------
    session_path : str or Path
        Path to the BIDS session directory (e.g., sub-01/ses-01)
    seqinfo_list : list
        List of seqinfo objects from heudiconv containing DICOM metadata
    """
    session_path = Path(session_path)
    logger.info(f"Processing DWI files in session: {session_path}")

    # Find all DWI NIfTI files in the dwi subdirectory
    dwi_dir = session_path / "dwi"
    if not dwi_dir.exists():
        logger.info("No dwi directory found, skipping bvec/bval generation")
        return

    # Process all *_dwi.nii* files
    dwi_files = list(dwi_dir.glob("*_dwi.nii*"))
    logger.info(f"Found {len(dwi_files)} DWI files to process")

    for dwi_file in dwi_files:
        logger.info(f"Processing DWI file: {dwi_file.name}")

        # Extract series ID from the filename or JSON sidecar
        # For now, we'll try to match based on the run number or other metadata
        # In a real implementation, you would parse the JSON sidecar to get
        # the series information

        # Get the basename without extension
        basename = str(dwi_file)
        if basename.endswith(".nii.gz"):
            basename = basename[:-7]
        elif basename.endswith(".nii"):
            basename = basename[:-4]

        # Check if bvec/bval already exist
        if Path(f"{basename}.bvec").exists() and Path(f"{basename}.bval").exists():
            logger.info(f"bvec/bval files already exist for {dwi_file.name}, skipping")
            continue

        # In a real implementation, you would:
        # 1. Read the JSON sidecar to get series information
        # 2. Use get_dicom_path_from_series() to find the DICOM file
        # 3. Extract bvec/bval using get_bvec_bval()

        # For now, we'll use a simplified approach
        # Assuming we can find the DICOM path from seqinfo
        dcm_path = None
        for seq in seqinfo_list:
            # Match based on series description or other criteria
            # This is simplified - real implementation would be more robust
            if hasattr(seq, "example_dcm_file") and "DWI" in str(
                getattr(seq, "series_description", "")
            ):
                dcm_path = seq.example_dcm_file
                break

        if dcm_path:
            logger.info(f"Found DICOM file: {dcm_path}")
            bvec, bval = get_bvec_bval(dcm_path)
            write_bvec_bval(bvec, bval, basename)
        else:
            logger.warning(f"Could not find DICOM file for {dwi_file.name}, skipping")


def custom_callable(prefix, outtypes, item_dicoms):
    """Custom post-processing after conversion"""
    logger.debug("Entered custom_callable hook")
    logger.debug("custom_callable prefix: %s", prefix)
    logger.debug("custom_callable outtypes: %s", outtypes)
    logger.debug("custom_callable item_dicoms: %s", item_dicoms)

    if prefix.split("_")[-1] == "dwi":
        bvec, bval = get_bvec_bval(item_dicoms[0])
        write_bvec_bval(bvec, bval, prefix)

    return
