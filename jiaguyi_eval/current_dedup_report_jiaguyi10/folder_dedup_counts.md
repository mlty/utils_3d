# jiaguyi10 Current Dedup Counts

- dataset_dir: /Users/mlty/Data/jiaguyi10
- original_model_file_count: 3766
- dedup_model_file_count: 3766
- removed_duplicate_count: 0
- duplicate_group_count: 0
- top_folder_count: 4

## Folder Counts

| 一级文件夹 | 原始文件数 | 去重后文件数 | 排除重复数 | glb | gltf |
|---|---:|---:|---:|---:|---:|
| 动物_不包含PBR和骨骼_写实风_1730(1)(1) | 1530 | 1530 | 0 | 1530 | 0 |
| 动物_包含PBR和骨骼_写实风_1454(1) | 1218 | 1218 | 0 | 1218 | 0 |
| 机甲_不包含PBR和骨骼_写实风_536(1) | 475 | 475 | 0 | 475 | 0 |
| 真人_不包含PBR和骨骼_写实风_715(1) | 543 | 543 | 0 | 543 | 0 |

## Dedup Rule

- Same relative parent folder + same extension + filename stem after removing download suffixes is treated as duplicate.
- Removed suffix examples: `(1)`, `（1）`, `copy`, `副本`, `拷贝`.
- When duplicates exist, the largest file is kept; ties are resolved by path order.
