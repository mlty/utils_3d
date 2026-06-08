# Cross Dataset GLB Duplicate Report

- left_name: jiaguyi10
- left_dir: /Users/mlty/Data/jiaguyi10
- right_name: jiaguyi9
- right_dir: /Users/mlty/Data/jiaguyi9
- extensions: ['.glb', '.gltf']
- jiaguyi10_file_count: 3766
- jiaguyi9_file_count: 13003
- total_file_count: 16769
- cross_size_candidate_file_count: 28
- cross_quick_hash_candidate_file_count: 12
- error_count: 0
- extension_counts: {'.glb': 16769}
- duplicate_group_count: 6
- duplicate_pair_count: 6
- duplicate_jiaguyi10_file_count: 6
- duplicate_jiaguyi9_file_count: 6
- elapsed_sec: 7.629

## Largest Duplicate Groups

| sha256 | size bytes | jiaguyi10 count | jiaguyi9 count |
|---|---:|---:|---:|
| ee4883ccfa5b7cf7168a68e5948d4fe38fe269768db0d055ed3dd270476c2fcc | 5784776 | 1 | 1 |
| 2a25554d3c06fc497745c64ad857debd49ec3fe9e521480ed8468b8efdc905a0 | 5709584 | 1 | 1 |
| 9b6368f49f3c1aa15d9336d735b52d61c536dc458059057aed1b4c65a6b34f6a | 4563608 | 1 | 1 |
| 279c9a6e259ddcc90d3f399061f01a7841eb06f14e23d7154323a4e60ecfa773 | 3598588 | 1 | 1 |
| f065eed8785268be2db9b0f6b20a3ad34034d7099994c47ac3a4d4372818a9f1 | 3596784 | 1 | 1 |
| 8ab5b7e177884702796cebf52f50034e248bce7ced56c37b673ba6bf1b38bd80 | 1855204 | 1 | 1 |

## Output Files

- `duplicate_groups.csv`: one row per exact SHA-256 duplicate group.
- `duplicate_pairs.csv`: all cross-dataset duplicate path pairs.
- `duplicate_jiaguyi10_paths.txt`: jiaguyi10 files duplicated in jiaguyi9.
- `duplicate_jiaguyi9_paths.txt`: jiaguyi9 files duplicated in jiaguyi10.
- `manifest.csv`: scanned files with size and computed hashes.
