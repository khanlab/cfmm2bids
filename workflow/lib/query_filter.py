import hashlib
import json

import numpy as np
import pandas as pd

# Import cfmm2tar conditionally - only needed for actual queries
try:
    from cfmm2tar import query_metadata
except ImportError:
    query_metadata = None


def compute_query_hash(search_specs, query_kwargs=None):
    """
    Compute a deterministic hash of the query parameters.

    This hash is used to detect if query parameters have changed since
    the last query, allowing us to skip re-querying if nothing changed.

    Parameters
    ----------
    search_specs : list
        The search specifications from the config.
    query_kwargs : dict, optional
        Additional query keyword arguments.

    Returns
    -------
    str
        A hex digest hash of the query parameters.
    """
    if query_kwargs is None:
        query_kwargs = {}
    params = {"search_specs": search_specs, "query_kwargs": query_kwargs}
    # Use sort_keys=True for deterministic ordering
    params_json = json.dumps(params, sort_keys=True)
    return hashlib.sha256(params_json.encode()).hexdigest()


def should_skip_query(
    query_tsv_path, query_hash_path, current_hash, force_requery=False
):
    """
    Determine if the query can be skipped.

    The query can be skipped if:
    1. The query TSV file already exists
    2. The hash file exists and matches the current hash
    3. force_requery is not set

    Parameters
    ----------
    query_tsv_path : Path
        Path to the query results TSV file.
    query_hash_path : Path
        Path to the query hash file.
    current_hash : str
        The current computed hash of query parameters.
    force_requery : bool, default=False
        If True, always perform a new query.

    Returns
    -------
    bool
        True if the query can be skipped, False otherwise.
    """
    if force_requery:
        return False

    if not query_tsv_path.exists():
        return False

    if not query_hash_path.exists():
        return False

    try:
        stored_hash = query_hash_path.read_text().strip()
        return stored_hash == current_hash
    except OSError:
        return False


# Function to validate a column
def validate_column(df, col):
    # Non-blank: not null and not whitespace
    non_blank = df[col].notna() & df[col].str.strip().ne("")

    # Alphanumeric check
    pattern = r"^[A-Za-z0-9]+$"
    alphanumeric = df[col].str.match(pattern, na=False)

    # Combine both conditions
    valid = non_blank & alphanumeric

    return valid


def query_dicoms(search_specs, **query_metadata_kwargs):
    if query_metadata is None:
        raise ImportError(
            "cfmm2tar is required for querying DICOM metadata. "
            "Install it with: pip install cfmm2tar"
        )

    all_dfs = []

    for spec in search_specs:
        # Query DICOM metadata
        df_ = query_metadata(
            return_type="dataframe", **query_metadata_kwargs, **spec["dicom_query"]
        )

        # Skip if empty
        if df_.empty:
            continue

        # Apply metadata extraction settings
        mappings = spec.get("metadata_mappings", {})
        for target, mapping in mappings.items():
            # Check if a constant value is specified
            if "constant" in mapping:
                # Use constant value for all rows
                series = pd.Series(mapping["constant"], index=df_.index, dtype=object)
            else:
                # Extract from source column
                source_col = mapping["source"]
                series = df_[source_col]

                # Optional remapping of specific values
                if "premap" in mapping:
                    series = series.replace(mapping["premap"])

                # Optional regex extraction
                if "pattern" in mapping:
                    series = series.str.extract(mapping["pattern"], expand=False)

                # Optional cleaning / sanitization
                if mapping.get("sanitize", True):
                    series = series.str.replace(r"[^A-Za-z0-9]", "", regex=True)

                # Optional remapping of specific values
                if "map" in mapping:
                    series = series.replace(mapping["map"])

                if "fillna" in mapping:
                    series = series.fillna(mapping["fillna"])

            # Assign to target field
            df_[target] = series

        # Record query info for traceability (optional)
        df_["query_params"] = str(spec["dicom_query"])

        all_dfs.append(df_)

    # Combine all query results into a single DataFrame
    if len(all_dfs) == 0:
        raise LookupError("No matching studies found!")

    df = pd.concat(all_dfs, ignore_index=True)

    return df


def remap_sessions_by_date(
    df,
    subject_col="subject",
    session_col="session",
    session_format="%Y%m%d",
    units="months",
    round_step=6,
    time_to_label=None,
    reference_col=None,
    reference_format="%Y%m%d",
    zero_pad=False,
):
    """
    Remap session IDs based on study date ordering with time intervals.

    This function takes a dataframe with subject and session columns, computes
    time differences from a reference date, rounds them to specified intervals,
    and remaps the session column to meaningful labels.

    The reference date can be either:
    - The first session per subject (baseline, when reference_col is None)
    - A specific date column (e.g., PatientBirthDate for age at scan)

    Parameters
    ----------
    df : pd.DataFrame
        Must include subject_col and session_col columns.
    subject_col : str, default='subject'
        Name of subject identifier column.
    session_col : str, default='session'
        Name of session/date column (string or datetime).
    session_format : str, default='%Y%m%d'
        Format of session column if string (e.g. '%Y%m%d').
    units : {'days', 'months', 'years'}, default='months'
        Units for time difference calculation.
    round_step : float, default=6
        Step size for rounding (e.g. 6 for 6 months).
    time_to_label : dict, optional
        Mapping from numeric rounded time (e.g. 0, 6, 12) to label
        (e.g. '0m', '6m', '12m'). If None, uses default mapping
        with numeric labels (e.g., '0m', '6m', '12m').
    reference_col : str, optional
        Name of column containing reference date (e.g., 'PatientBirthDate').
        If None, uses first session per subject as reference (baseline).
    reference_format : str, default='%Y%m%d'
        Format of reference_col if string (e.g. '%Y%m%d').
    zero_pad : bool, default=False
        If True, zero-pad session labels to the width of the largest number.
        For example, if the largest value is 100, labels will be '000m', '006m', '012m', etc.
        If False, labels will be '0m', '6m', '12m', etc.

    Returns
    -------
    pd.DataFrame
        Original dataframe with session column remapped to time-based labels.
    """
    df = df.copy()

    # Convert session col to datetime if needed
    if not np.issubdtype(df[session_col].dtype, np.datetime64):
        session_date = pd.to_datetime(df[session_col], format=session_format)
    else:
        session_date = df[session_col]

    # Create temporary dataframe with original index preserved
    temp_df = pd.DataFrame(
        {subject_col: df[subject_col], "session_date": session_date}, index=df.index
    )

    # Sort by subject and date
    temp_df = temp_df.sort_values([subject_col, "session_date"])

    # Determine reference date based on reference_col parameter
    if reference_col is None:
        # Use first session per subject (baseline behavior)
        reference_date = temp_df.groupby(subject_col)["session_date"].transform("first")
    else:
        # Use specified reference column (e.g., PatientBirthDate)
        if reference_col not in df.columns:
            raise ValueError(f"reference_col '{reference_col}' not found in dataframe")

        # Convert reference col to datetime if needed
        if not np.issubdtype(df[reference_col].dtype, np.datetime64):
            reference_date = pd.to_datetime(
                df[reference_col], format=reference_format
            ).reindex(temp_df.index)
        else:
            reference_date = df[reference_col].reindex(temp_df.index)

    # Compute difference in days from reference date
    diff_days = (temp_df["session_date"] - reference_date).dt.days

    # Convert to desired units
    if units == "days":
        time_diff = diff_days
    elif units == "months":
        time_diff = diff_days / 30.44
    elif units == "years":
        time_diff = diff_days / 365.25
    else:
        raise ValueError("units must be one of {'days', 'months', 'years'}")

    # Round to nearest increment
    time_rounded = (np.round(time_diff / round_step) * round_step).astype(float)

    # Apply label mapping
    if time_to_label is None:
        # Use default numeric labels with unit suffix (e.g., '0m', '6m', '12m')
        # or with zero-padding if requested (e.g., '000m', '006m', '012m')
        time_to_label = {}

    # Map custom labels first, then fill remaining with default labels
    time_label = time_rounded.map(time_to_label)

    # For unmapped values, create default labels
    unmapped_mask = time_label.isna()
    if unmapped_mask.any():
        time_rounded_int = time_rounded.astype(int)

        if zero_pad:
            # Calculate the width needed for zero-padding
            max_value = time_rounded_int.max()
            width = len(str(max_value))
            # Create zero-padded labels
            default_labels = time_rounded_int.astype(str).str.zfill(width) + units[0]
        else:
            # Create regular labels without padding
            default_labels = time_rounded_int.astype(str) + units[0]

        # Fill in the unmapped values with default labels
        time_label = time_label.fillna(default_labels)

    # Remap the session column in the original dataframe
    df[session_col] = time_label

    return df


def post_filter(df, post_filter_specs):
    if not post_filter_specs:
        return df

    for q in post_filter_specs.get("include") or []:
        df = df.query(q)

    for q in post_filter_specs.get("exclude") or []:
        df = df.query(f"not ({q})")

    # Apply session remapping if configured
    remap_config = post_filter_specs.get("remap_sessions_by_date")
    if remap_config and remap_config.get("enable", False):
        df = remap_sessions_by_date(
            df,
            subject_col=remap_config.get("subject_col", "subject"),
            session_col=remap_config.get("session_col", "session"),
            session_format=remap_config.get("session_format", "%Y%m%d"),
            units=remap_config.get("units", "months"),
            round_step=remap_config.get("round_step", 6),
            time_to_label=remap_config.get("time_to_label"),
            reference_col=remap_config.get("reference_col"),
            reference_format=remap_config.get("reference_format", "%Y%m%d"),
            zero_pad=remap_config.get("zero_pad", False),
        )

    for q in post_filter_specs.get("exclude_post_remap") or []:
        df = df.query(f"not ({q})")

    return df
