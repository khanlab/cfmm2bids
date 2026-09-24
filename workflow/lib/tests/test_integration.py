"""Integration tests for cfmm2bids workflow using Snakemake dry-run."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest
import yaml

# Check if snakemake is available
try:
    subprocess.run(
        ["snakemake", "--version"],
        capture_output=True,
        check=True,
    )
    SNAKEMAKE_AVAILABLE = True
except (subprocess.CalledProcessError, FileNotFoundError):
    SNAKEMAKE_AVAILABLE = False


def _make_test_workdir(tmp_path, config_filename):
    """Helper to create a temporary working directory with necessary files.

    Parameters
    ----------
    tmp_path : Path
        Base temporary directory (from pytest).
    config_filename : str
        Name of the config fixture file to use (e.g. 'test_config.yml').

    Returns
    -------
    Path
        The created working directory.
    """
    workdir = tmp_path / "test_workflow"
    workdir.mkdir()

    repo_root = Path(__file__).parent.parent.parent.parent
    fixtures_dir = Path(__file__).parent / "fixtures"

    # Copy heuristics
    shutil.copytree(repo_root / "heuristics", workdir / "heuristics")

    # Copy resources
    shutil.copytree(repo_root / "resources", workdir / "resources")

    # Copy workflow
    shutil.copytree(repo_root / "workflow", workdir / "workflow")

    # Copy test config
    config_src = fixtures_dir / config_filename
    config_dst = workdir / "config" / config_filename
    config_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(config_src, config_dst)

    # Create pre-populated query results
    query_dir = workdir / "test_results" / "0_query"
    query_dir.mkdir(parents=True)
    shutil.copy(fixtures_dir / "sample_studies.tsv", query_dir / "studies.tsv")

    # Compute query hash from config to prevent re-querying
    with open(config_dst) as f:
        test_config = yaml.safe_load(f)

    search_specs = test_config["search_specs"]
    query_kwargs = test_config.get("query_kwargs", {})
    params_json = json.dumps(
        {"search_specs": search_specs, "query_kwargs": query_kwargs}, sort_keys=True
    )
    query_hash = hashlib.sha256(params_json.encode()).hexdigest()
    (query_dir / "query_hash.txt").write_text(query_hash)

    # Create fake credentials file and update config to reference it
    creds_file = workdir / ".fake_credentials.bd"
    creds_file.write_text("fake_username\nfake_password\n")

    test_config["credentials_file"] = str(creds_file)
    with open(config_dst, "w") as f:
        yaml.dump(test_config, f)

    return workdir


@pytest.fixture
def test_workdir(tmp_path):
    """Create a temporary working directory using the standard test config."""
    yield _make_test_workdir(tmp_path, "test_config.yml")


@pytest.fixture
def test_workdir_gradcorrect(tmp_path):
    """Create a temporary working directory with gradcorrect enabled."""
    yield _make_test_workdir(tmp_path, "test_config_gradcorrect.yml")


@pytest.fixture
def test_workdir_gradcorrect_uncorr(tmp_path):
    """Create a temporary working directory with gradcorrect and create_bids_uncorr enabled."""
    yield _make_test_workdir(tmp_path, "test_config_gradcorrect_uncorr.yml")


@pytest.mark.skipif(not SNAKEMAKE_AVAILABLE, reason="Snakemake not available")
class TestSnakemakeDryRun:
    """Test Snakemake workflow with dry-run mode."""

    def test_workflow_dry_run_with_preloaded_query(self, test_workdir):
        """Test that workflow dry-run succeeds with pre-loaded query data."""
        # Run Snakemake dry-run
        result = subprocess.run(
            [
                "snakemake",
                "--configfile",
                "config/test_config.yml",
                "--dry-run",
                "--quiet",
                "all",
            ],
            cwd=test_workdir,
            capture_output=True,
            text=True,
        )

        # Check that dry-run succeeds
        assert result.returncode == 0, (
            f"Dry-run failed with stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
        )

    def test_workflow_dry_run_download_stage(self, test_workdir):
        """Test that download stage dry-run succeeds."""
        result = subprocess.run(
            [
                "snakemake",
                "--configfile",
                "config/test_config.yml",
                "--dry-run",
                "download",
            ],
            cwd=test_workdir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Download stage dry-run failed with stderr:\n{result.stderr}\n"
            f"stdout:\n{result.stdout}"
        )

    def test_workflow_dry_run_convert_stage(self, test_workdir):
        """Test that convert stage dry-run succeeds."""
        result = subprocess.run(
            [
                "snakemake",
                "--configfile",
                "config/test_config.yml",
                "--dry-run",
                "convert",
            ],
            cwd=test_workdir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Convert stage dry-run failed with stderr:\n{result.stderr}\n"
            f"stdout:\n{result.stdout}"
        )

    def test_workflow_dry_run_fix_stage(self, test_workdir):
        """Test that fix stage dry-run succeeds."""
        result = subprocess.run(
            [
                "snakemake",
                "--configfile",
                "config/test_config.yml",
                "--dry-run",
                "fix",
            ],
            cwd=test_workdir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Fix stage dry-run failed with stderr:\n{result.stderr}\n"
            f"stdout:\n{result.stdout}"
        )

    def test_workflow_dry_run_with_head_filter(self, test_workdir):
        """Test that workflow dry-run with head=1 succeeds."""
        result = subprocess.run(
            [
                "snakemake",
                "--configfile",
                "config/test_config.yml",
                "--config",
                "head=1",
                "--dry-run",
                "--quiet",
                "all",
            ],
            cwd=test_workdir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Head filter dry-run failed with stderr:\n{result.stderr}\n"
            f"stdout:\n{result.stdout}"
        )

    def test_filtered_studies_created(self, test_workdir):
        """Test that filtered studies TSV is created during workflow parsing."""
        # Run workflow to generate filtered studies
        result = subprocess.run(
            [
                "snakemake",
                "--configfile",
                "config/test_config.yml",
                "--dry-run",
                "--quiet",
                "all",
            ],
            cwd=test_workdir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Check that filtered studies file exists
        filtered_tsv = (
            test_workdir / "test_results" / "1_filter" / "studies_filtered.tsv"
        )
        assert filtered_tsv.exists(), "Filtered studies TSV should be created"

        # Check content
        df = pd.read_csv(filtered_tsv, sep="\t", dtype={"subject": str, "session": str})
        assert len(df) == 3, "Should have 3 subjects/sessions"
        assert "subject" in df.columns
        assert "session" in df.columns


class TestDataFixtures:
    """Test data fixtures for integration testing."""

    def test_sample_studies_tsv_exists(self):
        """Test that sample studies TSV fixture exists and is valid."""
        fixtures_dir = Path(__file__).parent / "fixtures"
        tsv_file = fixtures_dir / "sample_studies.tsv"

        assert tsv_file.exists(), "sample_studies.tsv fixture should exist"

        # Load and validate content
        df = pd.read_csv(tsv_file, sep="\t", dtype={"subject": str, "session": str})
        assert len(df) > 0, "TSV should contain data"
        assert "subject" in df.columns
        assert "session" in df.columns
        assert "StudyInstanceUID" in df.columns

    def test_test_config_exists(self):
        """Test that test config fixture exists and is valid."""
        fixtures_dir = Path(__file__).parent / "fixtures"
        config_file = fixtures_dir / "test_config.yml"

        assert config_file.exists(), "test_config.yml fixture should exist"

        # Basic validation that file is readable
        content = config_file.read_text()
        assert "search_specs" in content
        assert "heuristic" in content

    def test_test_config_gradcorrect_exists(self):
        """Test that gradcorrect test config fixture exists and is valid."""
        fixtures_dir = Path(__file__).parent / "fixtures"
        config_file = fixtures_dir / "test_config_gradcorrect.yml"

        assert config_file.exists(), "test_config_gradcorrect.yml fixture should exist"

        content = config_file.read_text()
        assert "search_specs" in content
        assert "heuristic" in content
        assert "gradcorrect" in content
        assert "grad_coeff_file" in content

    def test_test_config_gradcorrect_uncorr_exists(self):
        """Test that gradcorrect+uncorr test config fixture exists and is valid."""
        fixtures_dir = Path(__file__).parent / "fixtures"
        config_file = fixtures_dir / "test_config_gradcorrect_uncorr.yml"

        assert config_file.exists(), (
            "test_config_gradcorrect_uncorr.yml fixture should exist"
        )

        content = config_file.read_text()
        assert "search_specs" in content
        assert "gradcorrect" in content
        assert "create_bids_uncorr: true" in content


@pytest.mark.skipif(not SNAKEMAKE_AVAILABLE, reason="Snakemake not available")
class TestSnakemakeDryRunGradcorrect:
    """Test Snakemake workflow dry-run with gradcorrect enabled."""

    def test_workflow_dry_run_gradcorrect_all(self, test_workdir_gradcorrect):
        """Test that the full workflow dry-run succeeds with gradcorrect enabled."""
        result = subprocess.run(
            [
                "snakemake",
                "--configfile",
                "config/test_config_gradcorrect.yml",
                "--dry-run",
                "--quiet",
                "all",
            ],
            cwd=test_workdir_gradcorrect,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Gradcorrect dry-run failed with stderr:\n{result.stderr}\n"
            f"stdout:\n{result.stdout}"
        )

    def test_workflow_dry_run_gradcorrect_download_stage(
        self, test_workdir_gradcorrect
    ):
        """Test that download stage dry-run succeeds with gradcorrect enabled."""
        result = subprocess.run(
            [
                "snakemake",
                "--configfile",
                "config/test_config_gradcorrect.yml",
                "--dry-run",
                "download",
            ],
            cwd=test_workdir_gradcorrect,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Gradcorrect download stage dry-run failed with stderr:\n{result.stderr}\n"
            f"stdout:\n{result.stdout}"
        )

    def test_workflow_dry_run_gradcorrect_fix_stage(self, test_workdir_gradcorrect):
        """Test that fix stage dry-run succeeds with gradcorrect enabled."""
        result = subprocess.run(
            [
                "snakemake",
                "--configfile",
                "config/test_config_gradcorrect.yml",
                "--dry-run",
                "fix",
            ],
            cwd=test_workdir_gradcorrect,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Gradcorrect fix stage dry-run failed with stderr:\n{result.stderr}\n"
            f"stdout:\n{result.stdout}"
        )

    def test_workflow_dry_run_gradcorrect_with_uncorr_bids(
        self, test_workdir_gradcorrect_uncorr
    ):
        """Test that dry-run succeeds with gradcorrect and create_bids_uncorr enabled."""
        result = subprocess.run(
            [
                "snakemake",
                "--configfile",
                "config/test_config_gradcorrect_uncorr.yml",
                "--dry-run",
                "--quiet",
                "all",
            ],
            cwd=test_workdir_gradcorrect_uncorr,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Gradcorrect+uncorr dry-run failed with stderr:\n{result.stderr}\n"
            f"stdout:\n{result.stdout}"
        )
