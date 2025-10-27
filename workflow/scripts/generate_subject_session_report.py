"""
Generate subject/session summary report.

This script aggregates information from various stages (query, filter, convert, fix)
and creates:
1. An aggregated JSON file with metadata
2. An aggregated TSV file with series-level information
3. An interactive HTML report using datavzrd

The report includes information about:
- DICOM series and their BIDS mappings
- Conversion statistics
- Post-conversion fixes applied
"""

import json
import yaml
from pathlib import Path
from datetime import datetime
import pandas as pd
from lib import utils

log_file = snakemake.log[0] if snakemake.log else None
logger = utils.setup_logger(log_file)



def load_dicominfo(dicominfo_path):
    """Load dicominfo.tsv file."""
    df = pd.read_csv(dicominfo_path, sep='\t')
    return df


def load_filegroup(filegroup_path):
    """Load filegroup.json file."""
    with open(filegroup_path, 'r') as f:
        return json.load(f)


def load_provenance(prov_path):
    """Load provenance.json file."""
    try:
        with open(prov_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Provenance file not found: {prov_path}")
        return {}


def parse_auto_txt(auto_txt_path):
    """
    Parse the *.auto.txt file to extract BIDS mappings.
    
    Returns:
        dict: Mapping of series_id to BIDS path
    """
    import ast
    
    with open(auto_txt_path, 'r') as f:
        data_str = f.read()
    
    data = ast.literal_eval(data_str)
    
    # Invert mapping from bids pattern to series id
    series_to_bids = {}
    
    for key, series_id_list in data.items():
        # Use the full BIDS filename pattern from the last element
        # key structure: (modality, suffix, ..., filename_pattern)
        bids_pattern = key[-1] if len(key) > 0 else str(key)
        
        for item, series_id in enumerate(series_id_list, 1):
            if isinstance(series_id, dict):
                series_id = series_id['item']
            if series_id in series_to_bids:
                raise ValueError(f"Duplicate series ID found: {series_id!r}")
            series_to_bids[series_id] = bids_pattern
    
    return dict(sorted(series_to_bids.items(), key=lambda x: x[0]))


def create_aggregated_tsv(dicominfo_df, mappings, prov_data, output_path):
    """
    Create aggregated TSV with series information.
    
    Args:
        dicominfo_df: DataFrame with DICOM info
        mappings: dict mapping series_id to BIDS path
        prov_data: dict with provenance information
        output_path: Path to save the TSV file
    """
    summary_data = []
    
    for _, row in dicominfo_df.iterrows():
        series_id = row['series_id']
        bids_path = mappings.get(series_id, 'NOT MAPPED')
        is_mapped = 'Yes' if series_id in mappings else 'No'
        
        summary_data.append({
            'series_id': series_id,
            'series_description': row['series_description'],
            'protocol_name': row['protocol_name'],
            'dimensions': f"{row['dim1']}×{row['dim2']}×{row['dim3']}×{row['dim4']}",
            'TR_ms': row['TR'],
            'TE_ms': row['TE'],
            'num_files': row['series_files'],
            'is_mapped': is_mapped,
            'bids_path': bids_path,
        })
    
    summary_df = pd.DataFrame(summary_data)
    summary_df.to_csv(output_path, sep='\t', index=False)
    logger.info(f"Saved aggregated TSV to {output_path}")
    
    return summary_df


def create_aggregated_json(subject, session, dicominfo_df, mappings, 
                          filegroup_data, prov_data, output_path):
    """
    Create aggregated JSON with metadata.
    
    Args:
        subject: Subject ID
        session: Session ID
        dicominfo_df: DataFrame with DICOM info
        mappings: dict mapping series_id to BIDS path
        filegroup_data: dict with filegroup information
        prov_data: dict with provenance information
        output_path: Path to save the JSON file
    """
    total_series = len(dicominfo_df)
    mapped_series = len([s for s in dicominfo_df['series_id'] if s in mappings])
    unmapped_series = total_series - mapped_series
    
    metadata = {
        'subject': subject,
        'session': session,
        'report_generated': datetime.now().isoformat(),
        'summary': {
            'total_series': total_series,
            'mapped_series': mapped_series,
            'unmapped_series': unmapped_series,
            'mapping_rate': f"{(mapped_series/total_series*100):.1f}%" if total_series > 0 else "N/A"
        },
        'stages': {
            'convert': {
                'filegroup_count': len(filegroup_data) if isinstance(filegroup_data, list) else 0,
            },
            'fix': {
                'fixes_applied': prov_data.get('fixes_used', []),
                'files_modified': prov_data.get('files_modified', 0)
            }
        }
    }
    
    with open(output_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    logger.info(f"Saved aggregated JSON to {output_path}")
    
    return metadata


def create_datavzrd_config(tsv_path, json_path, output_path):
    """
    Create datavzrd configuration file.
    
    Args:
        tsv_path: Path to the aggregated TSV file
        json_path: Path to the aggregated JSON file
        output_path: Path to save the config file
    """
    # Read JSON to include metadata in the report description
    with open(json_path, 'r') as f:
        metadata = json.load(f)
    
    # Create description with JSON metadata
    description = f"""
# Subject/Session Summary Report

**Subject:** {metadata['subject']}  
**Session:** {metadata['session']}  
**Report Generated:** {metadata['report_generated']}

## Summary Statistics
- Total Series: {metadata['summary']['total_series']}
- Mapped Series: {metadata['summary']['mapped_series']}
- Unmapped Series: {metadata['summary']['unmapped_series']}
- Mapping Rate: {metadata['summary']['mapping_rate']}

## Post-Conversion Fixes
- Fixes Applied: {', '.join(metadata['stages']['fix']['fixes_applied']) if metadata['stages']['fix']['fixes_applied'] else 'None'}
- Files Modified: {metadata['stages']['fix']['files_modified']}

---
"""
    
    config = {
        'name': 'Subject/Session Summary Report',
        'description': description,
        'datasets': {
            'series_info': {
                'path': str(Path(tsv_path).name),
                'separator': '\t'
            }
        },
        'views': {
            'series_table': {
                'dataset': 'series_info',
                'page-size': 50,
                'render-table': {
                    'columns': {
                        'is_mapped': {
                            'display-mode': 'detail',
                            'plot': {
                                'heatmap': {
                                    'scale': 'ordinal',
                                    'color-scheme': 'category10'
                                }
                            }
                        },
                        'TR_ms': {
                            'display-mode': 'detail',
                            'plot': {
                                'bars': {}
                            }
                        },
                        'TE_ms': {
                            'display-mode': 'detail',
                            'plot': {
                                'bars': {}
                            }
                        }
                    }
                }
            }
        }
    }
    
    with open(output_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    logger.info(f"Saved datavzrd config to {output_path}")





# Main execution
logger.info("Starting subject/session report generation")

# Get inputs
subject = snakemake.wildcards.subject
session = snakemake.wildcards.session

dicominfo_path = snakemake.input.dicominfo_tsv
auto_txt_path = snakemake.input.auto_txt
filegroup_path = snakemake.input.filegroup_json
prov_path = snakemake.input.prov_json

# Load data
logger.info("Loading input data...")
dicominfo_df = load_dicominfo(dicominfo_path)
mappings = parse_auto_txt(auto_txt_path)
filegroup_data = load_filegroup(filegroup_path)
prov_data = load_provenance(prov_path)

# Create outputs
logger.info("Creating aggregated outputs...")
aggregated_tsv = snakemake.output.aggregated_tsv
aggregated_json = snakemake.output.aggregated_json
datavzrd_config = snakemake.output.datavzrd_config

# Generate aggregated files
summary_df = create_aggregated_tsv(dicominfo_df, mappings, prov_data, aggregated_tsv)
metadata = create_aggregated_json(subject, session, dicominfo_df, mappings, 
                                   filegroup_data, prov_data, aggregated_json)

# Create datavzrd config (pass full path to json for reading, but use just filename in config)
create_datavzrd_config(aggregated_tsv, aggregated_json, datavzrd_config)

logger.info(f"Report generation complete for sub-{subject}/ses-{session}")
logger.info(f"  Total series: {metadata['summary']['total_series']}")
logger.info(f"  Mapped: {metadata['summary']['mapped_series']}")
logger.info(f"  Unmapped: {metadata['summary']['unmapped_series']}")
