# Texture AI/Problem Audit

- assets checked: 4
- textures checked: 5
- flagged assets: 4
- flagged textures: 4
- severity counts: {'texture_ai_suspect': 3, 'texture_problem': 1}
- issue counts: {'filename_generic_image_0': 2, 'fragmented_generic_uv_atlas': 2, 'fragmented_uv_high_edges': 2, 'filename_palette_marker': 1, 'palette_or_color_chart_texture': 1, 'filename_temp_or_ai_marker': 1, 'fragmented_uv_dark_seams': 1, 'temp_named_fragmented_texture': 1}
- elapsed_sec: 0.847
- PIL available: True

## Folder Summary

| folder | problem | AI suspect | review | total flagged |
|---|---:|---:|---:|---:|
| 动物_不包含PBR和骨骼_写实风_1730(1)(1) | 0 | 1 | 0 | 1 |
| 动物_包含PBR和骨骼_写实风_1454(1) | 1 | 2 | 0 | 3 |

## Top Flagged Assets

- [texture_problem] `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3676/动物_野生动物3676.glb`: ["filename_palette_marker", "palette_or_color_chart_texture"] textures=1/1
- [texture_ai_suspect] `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18066/动物_野生动物18066.glb`: ["filename_generic_image_0", "fragmented_generic_uv_atlas"] textures=1/1
- [texture_ai_suspect] `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4247/动物_野生动物4247.glb`: ["filename_generic_image_0", "fragmented_generic_uv_atlas", "fragmented_uv_dark_seams", "fragmented_uv_high_edges"] textures=1/2
- [texture_ai_suspect] `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4275/动物_野生动物4275.glb`: ["filename_temp_or_ai_marker", "fragmented_uv_high_edges", "temp_named_fragmented_texture"] textures=1/1
