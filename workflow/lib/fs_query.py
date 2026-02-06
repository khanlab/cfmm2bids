"""Helper functions for filesystem-based DICOM querying.

This module provides functionality to query DICOM data that has already been
downloaded and is stored as tar/tar.gz files or folders on the filesystem.
"""

import re
from pathlib import Path

import pandas as pd


def query_filesystem(search_specs, base_path=None):
    r"""
    Query filesystem for DICOM data based on filename/folder patterns.

    This function scans the filesystem for tar/tar.gz files or folders
    containing DICOM data, and extracts metadata fields (PatientID, StudyDate,
    StudyDescription, etc.) from the filenames/folder names using regex patterns.

    Parameters
    ----------
    search_specs : list of dict
        List of search specifications, each containing:
        - fs_query : dict with 'path' and 'pattern' keys
        - metadata_mappings : dict mapping field names to extraction rules
    base_path : str or Path, optional
        Base path to resolve relative paths against. If None, uses current directory.

    Returns
    -------
    pd.DataFrame
        DataFrame with extracted metadata fields and file paths.
        Always includes columns: subject, session, path, and extracted fields.

    Examples
    --------
    >>> search_specs = [{
    ...     'fs_query': {
    ...         'path': '/data/dicoms',
    ...         'pattern': r'(?P<PatientID>[^_]+)_(?P<StudyDate>\d{8})\.tar\.gz'
    ...     },
    ...     'metadata_mappings': {
    ...         'subject': {'source': 'PatientID', 'sanitize': True},
    ...         'session': {'source': 'StudyDate'}
    ...     }
    ... }]
    >>> df = query_filesystem(search_specs)
    """
    base_path = Path.cwd() if base_path is None else Path(base_path)

    all_dfs = []

    for spec in search_specs:
        fs_query = spec.get("fs_query", {})
        if not fs_query:
            continue

        # Get search path and pattern
        search_path = Path(fs_query["path"])
        if not search_path.is_absolute():
            search_path = base_path / search_path

        pattern = fs_query["pattern"]

        # Find all matching files and folders
        matches = []
        if search_path.exists():
            # Search for tar/tar.gz files and folders
            for item in search_path.iterdir():
                if (item.is_file() and item.name.endswith((".tar", ".tar.gz"))) or (
                    item.is_dir()
                ):
                    match = re.search(pattern, item.name)
                    if match:
                        matches.append((item, match.groupdict()))

        if not matches:
            continue

        # Create DataFrame from matches
        records = []
        for path, match_dict in matches:
            record = {"path": str(path)}
            record.update(match_dict)
            records.append(record)

        df_ = pd.DataFrame(records)

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
                if source_col not in df_.columns:
                    raise ValueError(
                        f"Source column '{source_col}' not found in extracted fields. "
                        f"Available fields: {list(df_.columns)}"
                    )
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

        # Record query info for traceability
        df_["query_params"] = str(fs_query)

        all_dfs.append(df_)

    # Combine all query results into a single DataFrame
    if len(all_dfs) == 0:
        # Return empty DataFrame with expected columns
        return pd.DataFrame(columns=["subject", "session", "path", "query_params"])

    df = pd.concat(all_dfs, ignore_index=True)

    return df
