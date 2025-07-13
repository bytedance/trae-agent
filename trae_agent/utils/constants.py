# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from pathlib import Path

LOCAL_STORAGE_PATH = Path.home() / ".trae-agent"

CKG_DATABASE_PATH = LOCAL_STORAGE_PATH / "ckg"
CKG_DATABASE_EXPIRY_TIME = 60 * 60 * 24 * 7  # 1 week in seconds


def get_ckg_database_path(codebase_snapshot_hash: str) -> Path:
    """Get the path to the CKG database for a codebase path."""
    return CKG_DATABASE_PATH / f"{codebase_snapshot_hash}.db"
