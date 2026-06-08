# Cross Dataset Base Color Duplicate Report

- left_name: jiaguyi10
- right_name: jiaguyi9
- left_assets_csv: /Users/mlty/Coding/utils_3d/jiaguyi_eval/glb_quality_report_jiaguyi10_images/assets.csv
- right_assets_csv: /Users/mlty/Coding/utils_3d/jiaguyi_eval/glb_quality_report_jiaguyi9_images/assets.csv
- require_asset_exists: True
- jiaguyi10_loaded_basecolor_texture_count: 11553
- jiaguyi9_loaded_basecolor_texture_count: 139397
- jiaguyi10_valid_basecolor_texture_count: 11552
- jiaguyi9_valid_basecolor_texture_count: 139392
- jiaguyi10_asset_with_valid_basecolor_count: 3698
- jiaguyi9_asset_with_valid_basecolor_count: 12997
- jiaguyi10_load_stats: {'asset_rows': 24105, 'texture_paths_total': 15298, 'texture_paths_skipped_non_color': 3684, 'texture_paths_skipped_palette': 61, 'asset_rows_skipped_missing_asset': 20339}
- jiaguyi9_load_stats: {'asset_rows': 13003, 'texture_paths_total': 142322, 'texture_paths_skipped_non_color': 2925}
- exact_texture_pair_count: 347
- exact_asset_pair_count: 182
- perceptual_texture_pair_count: 3725
- perceptual_asset_pair_count: 3046
- candidate_asset_pair_count: 3126
- exact_stats: {'skipped_common_pixel_hash_groups': 6, 'cross_pixel_hash_groups': 148}
- perceptual_stats: {'skipped_large_lsh_buckets': 4373}
- dhash_distance: 4
- min_dimension_ratio: 0.85
- min_dimension: 64
- max_hash_asset_count: 20
- include_palettes: False
- elapsed_sec: 374.491

## Candidate Strength Counts

- weak_perceptual_basecolor: 2930
- strong_exact_basecolor: 92
- medium_exact_basecolor: 90
- medium_perceptual_basecolor: 14

## Interpretation

- `strong_exact_basecolor`: base-color pixel hashes match with high coverage or multiple matching textures.
- `medium_exact_basecolor`: at least one exact base-color pixel hash is shared; useful candidate, not final proof.
- `medium_perceptual_basecolor` / `weak_perceptual_basecolor`: visually similar dHash candidates; inspect with geometry/normal renders before rejecting.

## Output Files

- `basecolor_manifest.csv`: all inspected base-color texture records.
- `exact_basecolor_texture_pairs.csv`: exact decoded-pixel texture matches.
- `exact_basecolor_asset_pairs.csv`: asset pairs aggregated from exact texture matches.
- `perceptual_basecolor_texture_pairs.csv`: dHash-similar texture matches.
- `perceptual_basecolor_asset_pairs.csv`: asset pairs aggregated from dHash matches.
- `candidate_duplicate_asset_pairs.csv`: merged asset-level candidate list.
