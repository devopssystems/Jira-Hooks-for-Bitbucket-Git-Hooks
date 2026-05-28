#!/usr/bin/env python3
"""Test script: validate a single commit from a JSON test-data file."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jhfb_hooks.runner import load_config_or_skip, run_check
from jhfb_hooks.testdata import load_commits_from_json

config = load_config_or_skip(Path(__file__).resolve().parent)
if config is None:
    sys.exit(0)
commits, branch, trigger_type = load_commits_from_json(Path(sys.argv[1]))
sys.exit(run_check(commits, branch, config, trigger_type=trigger_type))
