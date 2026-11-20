#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${AZCOPY_SOURCE_URL:?Set AZCOPY_SOURCE_URL to the source container or virtual directory URL, including SAS if needed.}"
: "${AZCOPY_DEST_DIR:?Set AZCOPY_DEST_DIR to the local download directory.}"

AZCOPY_LIST_FILE="${AZCOPY_LIST_FILE:-$SCRIPT_DIR/metadata_tex_remove_pbr_azcopy_list_container_root.txt}"

mkdir -p "$AZCOPY_DEST_DIR"

azcopy copy \
  "$AZCOPY_SOURCE_URL" \
  "$AZCOPY_DEST_DIR" \
  --recursive=true \
  --list-of-files="$AZCOPY_LIST_FILE" \
  --overwrite=ifSourceNewer