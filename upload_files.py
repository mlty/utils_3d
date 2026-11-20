"""Upload a local model directory to a ModelScope model repository."""

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_id", help="Destination model repository (owner/name)")
    parser.add_argument("folder", type=Path, help="Local model directory to upload")
    args = parser.parse_args()
    if not args.folder.is_dir():
        parser.error("folder must be an existing directory")
    token = os.environ.get("MODELSCOPE_API_TOKEN")
    if not token:
        parser.error("set MODELSCOPE_API_TOKEN before uploading")

    from modelscope.hub.api import HubApi

    api = HubApi()
    api.login(token)
    api.upload_folder(
        repo_id=args.repo_id,
        folder_path=str(args.folder),
        repo_type="model",
        commit_message="upload model files",
    )


if __name__ == "__main__":
    main()
