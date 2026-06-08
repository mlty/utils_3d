# Final Problem Audit - jiaguyi9

- dedup assets: 13003
- texture bad cases: 1620 (problem=0, ai_suspect=1620, review excluded=0)
- PBR map mismatch: 2457
- skin mismatch: 8565
- category mismatch: 0
- name PBR/skin problem union: 10686
- final problem count, texture OR any PBR/skin name mismatch: 11366
- final problem count, texture OR required-missing-only: 1620
- required missing PBR/skin only: 0
- overlap texture and name PBR/skin: 940

## Folder Counts: Texture OR PBR/Skin Name Mismatch

| folder | problem count |
|---|---:|
| 动漫角色_不包含PBR和骨骼_写实风_2216 | 1944 |
| 动物_不包含PBR和骨骼_写实风_2114 | 1168 |
| 手办_不包含PBR和骨骼_写实风_5405 | 4048 |
| 游戏角色_不包含PBR和骨骼_写实风_5093 | 4206 |

## Output Files

- texture_ai_audit_le4_basecolor/bad_cases.txt: texture problem + texture AI suspect paths.
- final_problem_audit/name_pbr_skin_problem_paths.txt: any PBR map or skin mismatch against folder name.
- final_problem_audit/problem_paths_texture_or_name_pbr_skin.txt: union of texture bad cases and PBR/skin name mismatches.
- final_problem_audit/problem_paths_texture_or_required_missing.txt: narrower union matching the previous required-missing-only口径.
