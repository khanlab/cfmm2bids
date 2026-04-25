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
            # Check if a constant value is specified without a map (pure constant behavior).
            # When 'map' is also present, 'constant' acts as a catch-all default instead
            # (see below), so we only take the all-rows-constant path when 'map' is absent.
            if "constant" in mapping and "map" not in mapping:
                # Use constant value for all rows
                series = pd.Series(mapping["constant"], index=df_.index, dtype=object)
            else:
                # Extract from source column.
                # 'source' may refer to an original DICOM column OR to a previously-derived
                # column (e.g. 'subject') created earlier in this same mappings loop.
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
                    # Track which rows are explicitly covered by the map before replacing.
                    # series.replace() returns a copy, so no extra .copy() is needed.
                    mapped_mask = series.isin(mapping["map"].keys())
                    series = series.replace(mapping["map"])

                    # Apply a catch-all default to rows not explicitly mapped.
                    # 'default' takes precedence; when absent, 'constant' is treated as
                    # an alias for the catch-all default (backwards-compatible).
                    if "default" in mapping:
                        series.loc[~mapped_mask] = mapping["default"]
                    elif "constant" in mapping:
                        series.loc[~mapped_mask] = mapping["constant"]

                if "fillna" in mapping:
                    series = series.fillna(mapping["fillna"])

                # Optional format string to reformat value, e.g. "AA{value}"
                if "format" in mapping:
                    fmt = mapping["format"]
                    series = series.apply(
                        lambda v, f=fmt: f.format(value=v) if pd.notna(v) else v
                    )

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

    Only rows whose session value parses as a date (and whose reference date is
    available/parses when reference_col is provided) are remapped.
    All other rows keep the original session value untouched.
    """
    df = df.copy()

    # Keep originals so we can "leave untouched" where parsing/deltas fail
    original_session = df[session_col]

    # --- Parse session dates; non-parsable -> NaT ---
    if not pd.api.types.is_datetime64_any_dtype(df[session_col]):
        session_date = pd.to_datetime(
            df[session_col],
            format=session_format,
            errors="coerce",
        )
    else:
        session_date = df[session_col]

    # Only attempt remap for rows with valid session dates
    valid_session_mask = session_date.notna()
    if not valid_session_mask.any():
        return df

    # Work only on valid session rows
    temp_df = pd.DataFrame(
        {
            subject_col: df.loc[valid_session_mask, subject_col],
            "session_date": session_date.loc[valid_session_mask],
        },
        index=df.index[valid_session_mask],
    ).sort_values([subject_col, "session_date"])

    # --- Determine reference dates aligned to temp_df.index ---
    if reference_col is None:
        reference_date = temp_df.groupby(subject_col)["session_date"].transform("first")
    else:
        if reference_col not in df.columns:
            raise ValueError(f"reference_col '{reference_col}' not found in dataframe")

        if not pd.api.types.is_datetime64_any_dtype(df[reference_col]):
            ref_parsed = pd.to_datetime(
                df[reference_col],
                format=reference_format,
                errors="coerce",
            )
        else:
            ref_parsed = df[reference_col]

        reference_date = ref_parsed.reindex(temp_df.index)

        # If reference_date is missing/unparsable for some rows, those rows should remain untouched
        valid_ref_mask = reference_date.notna()
        if not valid_ref_mask.all():
            temp_df = temp_df.loc[valid_ref_mask]
            reference_date = reference_date.loc[valid_ref_mask]

        if temp_df.empty:
            return df

    # --- Compute time deltas ---
    diff_days = (temp_df["session_date"] - reference_date).dt.days

    if units == "days":
        time_diff = diff_days.astype(float)
    elif units == "months":
        time_diff = diff_days.astype(float) / 30.44
    elif units == "years":
        time_diff = diff_days.astype(float) / 365.25
    else:
        raise ValueError("units must be one of {'days', 'months', 'years'}")

    if isinstance(round_step, (list, tuple, np.ndarray)):
        breakpoints = np.asarray(round_step, dtype=float)
        diffs = np.abs(time_diff.values[:, np.newaxis] - breakpoints[np.newaxis, :])
        nearest_idx = np.argmin(diffs, axis=1)
        time_rounded = pd.Series(
            breakpoints[nearest_idx], index=time_diff.index, dtype=float
        )
    else:
        time_rounded = (np.round(time_diff / round_step) * round_step).astype(float)

    # Label mapping (custom first)
    if time_to_label is None:
        time_to_label = {}

    # Use object dtype to allow mixed NaN/string values regardless of pandas version
    time_label = time_rounded.map(time_to_label).astype(object)

    # Fill unmapped finite values with default labels
    finite_mask = np.isfinite(time_rounded.to_numpy())
    if finite_mask.any():
        finite_idx = time_rounded.index[finite_mask]
        finite_vals = time_rounded.loc[finite_idx]

        rounded_int = finite_vals.round().astype(int)

        if zero_pad:
            max_value = int(rounded_int.max())
            width = len(str(max_value))
            default_labels = rounded_int.astype(str).str.zfill(width) + units[0]
        else:
            default_labels = rounded_int.astype(str) + units[0]

        unmapped = time_label.loc[finite_idx].isna()
        time_label.loc[finite_idx[unmapped]] = default_labels.loc[finite_idx[unmapped]]

    # --- Write back only for rows we successfully processed; others stay original ---
    df[session_col] = original_session
    df.loc[time_label.index, session_col] = time_label

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
