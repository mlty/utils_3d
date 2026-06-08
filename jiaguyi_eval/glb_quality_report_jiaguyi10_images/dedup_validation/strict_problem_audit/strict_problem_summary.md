# Strict Problem Audit

- deduplicated assets checked: 21827
- strict problem assets: 76
- strict review assets: 56
- total flagged assets: 132
- issue counts: {'audit_rejected': 76, 'validation_audit_rejected_asset': 76, 'validation_ai_candidate': 42, 'strong_static_ai_evidence': 41, 'audit_errors': 21, 'validation_small_extracted_textures': 12, 'validation_asset_has_no_gltf_images': 2, 'unreadable_source_images': 1, 'validation_fewer_extracted_than_gltf_images': 1, 'static_ai_evidence': 1}

## Folder Summary

| folder | strict problem | strict review | total flagged |
|---|---:|---:|---:|
| 动物_不包含PBR和骨骼_写实风_1730(1)(1) | 11 | 11 | 22 |
| 动物_包含PBR和骨骼_写实风_1454(1) | 34 | 7 | 41 |
| 手办_不包含PBR和骨骼_写实风_2997(1) | 2 | 18 | 20 |
| 手办_不包含PBR和骨骼_写实风_4009(1)(1) | 1 | 10 | 11 |
| 机甲_不包含PBR和骨骼_写实风_536(1) | 12 | 4 | 16 |
| 游戏角色_不包含PBR和骨骼_写实风_4084(2)(1) | 2 | 2 | 4 |
| 游戏角色_不包含PBR和骨骼_写实风_6988(1) | 1 | 2 | 3 |
| 游戏角色_包含PBR和骨骼_写实风_1100(1)(1) | 1 | 1 | 2 |
| 真人_不包含PBR和骨骼_写实风_715(1) | 12 | 1 | 13 |

## Criteria

- problem: hard reject/failure signals only; generic review is excluded.
- strict_review: strong but not final proof, mainly static AI evidence and texture edge cases.
- excluded: duplicate count mismatch, audit_review_asset, high_poly/no_pbr/no_texture alone.

## Top Problem Assets

- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物677/动物_农场动物677.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物17737/动物_野生动物17737.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物17742/动物_野生动物17742.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物17888/动物_野生动物17888.glb`: ["audit_errors", "audit_rejected", "unreadable_source_images", "validation_audit_rejected_asset", "validation_fewer_extracted_than_gltf_images"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物17936/动物_野生动物17936.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物17996/动物_野生动物17996.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18160/动物_野生动物18160.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18337/动物_野生动物18337.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18396/动物_野生动物18396.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18464/动物_野生动物18464.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18543/动物_野生动物18543.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3257/动物_野生动物3257.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3273/动物_野生动物3273.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3303/动物_野生动物3303.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3350/动物_野生动物3350.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3351/动物_野生动物3351.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3435/动物_野生动物3435.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3472/动物_野生动物3472.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3537/动物_野生动物3537.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3539/动物_野生动物3539.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3560/动物_野生动物3560.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3658/动物_野生动物3658.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3662/动物_野生动物3662.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3674/动物_野生动物3674.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3724/动物_野生动物3724.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3732/动物_野生动物3732.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3881/动物_野生动物3881.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3911/动物_野生动物3911.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3913/动物_野生动物3913.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3916/动物_野生动物3916.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3956/动物_野生动物3956.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4039/动物_野生动物4039.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4098/动物_野生动物4098.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4105/动物_野生动物4105.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4109/动物_野生动物4109.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4124/动物_野生动物4124.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4126/动物_野生动物4126.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4146/动物_野生动物4146.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4176/动物_野生动物4176.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4236/动物_野生动物4236.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4238/动物_野生动物4238.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4244/动物_野生动物4244.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4313/动物_野生动物4313.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4388/动物_野生动物4388.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4397/动物_野生动物4397.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象19228/手办_Q版形象19228.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象19858/手办_Q版形象19858.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `手办_不包含PBR和骨骼_写实风_4009(1)(1)/手办_Q版形象/手办_Q版形象16330/手办_Q版形象16330.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_战舰/机甲_战舰3346/机甲_战舰3346.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_战舰/机甲_战舰3347/机甲_战舰3347.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_战舰/机甲_战舰3360/机甲_战舰3360.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_战舰/机甲_战舰3372/机甲_战舰3372.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_战舰/机甲_战舰3447/机甲_战舰3447.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_机器人/机甲_机器人11643/机甲_机器人11643.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_机器人/机甲_机器人11652/机甲_机器人11652.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_机器人/机甲_机器人11703/机甲_机器人11703.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_机器人/机甲_机器人11721/机甲_机器人11721.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_机器人/机甲_机器人11731/机甲_机器人11731.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_机器人/机甲_机器人11907/机甲_机器人11907.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_机器人/机甲_机器人11993/机甲_机器人11993.glb`: ["audit_errors", "audit_rejected", "validation_audit_rejected_asset"]
- `游戏角色_不包含PBR和骨骼_写实风_4084(2)(1)/游戏角色_奇幻类人角色/游戏角色_奇幻类人角色20392/游戏角色_奇幻类人角色20392.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `游戏角色_不包含PBR和骨骼_写实风_4084(2)(1)/游戏角色_风格化类人角色/游戏角色_风格化类人角色20743/游戏角色_风格化类人角色20743.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `游戏角色_不包含PBR和骨骼_写实风_6988(1)/游戏角色_不包含PBR和骨骼_写实风_6988/游戏角色_奇幻类人角色/游戏角色_奇幻类人角色14157/游戏角色_奇幻类人角色14157.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `游戏角色_包含PBR和骨骼_写实风_1100(1)(1)/游戏角色_奇幻类人角色/游戏角色_奇幻类人角色4265/游戏角色_奇幻类人角色4265.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `真人_不包含PBR和骨骼_写实风_715(1)/真人_成人/真人_成人12111/真人_成人12111.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `真人_不包含PBR和骨骼_写实风_715(1)/真人_成人/真人_成人12135/真人_成人12135.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `真人_不包含PBR和骨骼_写实风_715(1)/真人_成人/真人_成人12664/真人_成人12664.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `真人_不包含PBR和骨骼_写实风_715(1)/真人_成人/真人_成人12698/真人_成人12698.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `真人_不包含PBR和骨骼_写实风_715(1)/真人_成人/真人_成人12699/真人_成人12699.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `真人_不包含PBR和骨骼_写实风_715(1)/真人_成人/真人_成人12740/真人_成人12740.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `真人_不包含PBR和骨骼_写实风_715(1)/真人_成人/真人_成人12741/真人_成人12741.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `真人_不包含PBR和骨骼_写实风_715(1)/真人_成人/真人_成人12752/真人_成人12752.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `真人_不包含PBR和骨骼_写实风_715(1)/真人_成人/真人_成人12782/真人_成人12782.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `真人_不包含PBR和骨骼_写实风_715(1)/真人_成人/真人_成人12783/真人_成人12783.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `真人_不包含PBR和骨骼_写实风_715(1)/真人_成人/真人_成人12784/真人_成人12784.glb`: ["audit_rejected", "validation_audit_rejected_asset"]
- `真人_不包含PBR和骨骼_写实风_715(1)/真人_成人/真人_成人12786/真人_成人12786.glb`: ["audit_rejected", "validation_audit_rejected_asset"]

## Top Strict Review Assets

- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物17867/动物_野生动物17867.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物17995/动物_野生动物17995.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18130/动物_野生动物18130.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18428/动物_野生动物18428.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18554/动物_野生动物18554.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18567/动物_野生动物18567.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18645/动物_野生动物18645.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18656/动物_野生动物18656.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18685/动物_野生动物18685.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18775/动物_野生动物18775.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18816/动物_野生动物18816.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3242/动物_野生动物3242.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3252/动物_野生动物3252.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3520/动物_野生动物3520.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3563/动物_野生动物3563.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3831/动物_野生动物3831.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3855/动物_野生动物3855.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物4383/动物_野生动物4383.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象17208/手办_Q版形象17208.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象17252/手办_Q版形象17252.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象17395/手办_Q版形象17395.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象17406/手办_Q版形象17406.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象17413/手办_Q版形象17413.glb`: ["validation_small_extracted_textures"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象17472/手办_Q版形象17472.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象17628/手办_Q版形象17628.glb`: ["validation_asset_has_no_gltf_images"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象18128/手办_Q版形象18128.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象18398/手办_Q版形象18398.glb`: ["validation_small_extracted_textures"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象18833/手办_Q版形象18833.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象18848/手办_Q版形象18848.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象18894/手办_Q版形象18894.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象19157/手办_Q版形象19157.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象19515/手办_Q版形象19515.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象19525/手办_Q版形象19525.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象19536/手办_Q版形象19536.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象19637/手办_Q版形象19637.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象19847/手办_Q版形象19847.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_4009(1)(1)/手办_Q版形象/手办_Q版形象13542/手办_Q版形象13542.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_4009(1)(1)/手办_Q版形象/手办_Q版形象13668/手办_Q版形象13668.glb`: ["validation_small_extracted_textures"]
- `手办_不包含PBR和骨骼_写实风_4009(1)(1)/手办_Q版形象/手办_Q版形象14425/手办_Q版形象14425.glb`: ["validation_small_extracted_textures"]
- `手办_不包含PBR和骨骼_写实风_4009(1)(1)/手办_Q版形象/手办_Q版形象15045/手办_Q版形象15045.glb`: ["validation_small_extracted_textures"]
- `手办_不包含PBR和骨骼_写实风_4009(1)(1)/手办_Q版形象/手办_Q版形象15684/手办_Q版形象15684.glb`: ["validation_small_extracted_textures"]
- `手办_不包含PBR和骨骼_写实风_4009(1)(1)/手办_Q版形象/手办_Q版形象15775/手办_Q版形象15775.glb`: ["validation_asset_has_no_gltf_images"]
- `手办_不包含PBR和骨骼_写实风_4009(1)(1)/手办_Q版形象/手办_Q版形象15917/手办_Q版形象15917.glb`: ["validation_small_extracted_textures"]
- `手办_不包含PBR和骨骼_写实风_4009(1)(1)/手办_Q版形象/手办_Q版形象16331/手办_Q版形象16331.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_4009(1)(1)/手办_Q版形象/手办_Q版形象16332/手办_Q版形象16332.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `手办_不包含PBR和骨骼_写实风_4009(1)(1)/手办_Q版形象/手办_Q版形象16333/手办_Q版形象16333.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_机器人/机甲_机器人11732/机甲_机器人11732.glb`: ["static_ai_evidence", "validation_ai_candidate"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_机器人/机甲_机器人11768/机甲_机器人11768.glb`: ["validation_small_extracted_textures"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_机器人/机甲_机器人11983/机甲_机器人11983.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `机甲_不包含PBR和骨骼_写实风_536(1)/机甲_机器人/机甲_机器人11987/机甲_机器人11987.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `游戏角色_不包含PBR和骨骼_写实风_4084(2)(1)/游戏角色_奇幻类人角色/游戏角色_奇幻类人角色19709/游戏角色_奇幻类人角色19709.glb`: ["validation_small_extracted_textures"]
- `游戏角色_不包含PBR和骨骼_写实风_4084(2)(1)/游戏角色_风格化类人角色/游戏角色_风格化类人角色21178/游戏角色_风格化类人角色21178.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
- `游戏角色_不包含PBR和骨骼_写实风_6988(1)/游戏角色_不包含PBR和骨骼_写实风_6988/游戏角色_奇幻类人角色/游戏角色_奇幻类人角色14141/游戏角色_奇幻类人角色14141.glb`: ["validation_small_extracted_textures"]
- `游戏角色_不包含PBR和骨骼_写实风_6988(1)/游戏角色_不包含PBR和骨骼_写实风_6988/游戏角色_奇幻类人角色/游戏角色_奇幻类人角色14712/游戏角色_奇幻类人角色14712.glb`: ["validation_small_extracted_textures"]
- `游戏角色_包含PBR和骨骼_写实风_1100(1)(1)/游戏角色_奇幻类人角色/游戏角色_奇幻类人角色4117/游戏角色_奇幻类人角色4117.glb`: ["validation_small_extracted_textures"]
- `真人_不包含PBR和骨骼_写实风_715(1)/真人_成人/真人_成人12705/真人_成人12705.glb`: ["strong_static_ai_evidence", "validation_ai_candidate"]
