# GLB 质量验收报告

## 总览
- 数据集状态: **rejected**
- 扫描目录: `/Users/mlty/Data/jiaguyi10`
- 输入清单: `None`
- 发现模型数: 24105
- 记录总数: 24105
- 可解析/可打开数: 24105 (100.00%)
- 解析失败数: 0 (0.00%)
- 缺失清单文件数: 0
- 运行耗时: 67.382s

## 验收状态

- accepted: 11 (0.05%)
- review: 24017 (99.63%)
- rejected: 77 (0.32%)

## 精度分布

- mid: 11 (0.05%)
- high: 24094 (99.95%)

## 主要问题

- review:high_poly_model: 24094
- review:violence_keyword_suspect: 220
- review:unused_images: 80
- reject:too_many_faces: 47
- review:ai_asset_suspect: 42
- reject:textures_without_uv: 20
- review:small_texture: 13
- reject:gore_keyword_suspect: 9
- review:no_pbr: 5
- review:no_texture: 2
- review:missing_normals: 2
- reject:unreadable_images: 1
- review:file_size_too_large: 1

## Rejected 明细

- 明细文件: `rejected_detail.md` / `rejected_detail.csv` / `rejected_detail.jsonl`
- 每条 rejected 都会给出机器原因、中文说明、具体证据和建议处理动作。

## AI 资产识别

- AI 候选数: 42
- 静态关键词命中数: 42
- LLM 判断 AI 数: 0
- LLM 不确定数: 0
- 风险分布: {'no_evidence': 24063, 'high': 41, 'low': 1}
- 候选明细: `ai_candidates.md` / `ai_candidates.csv` / `ai_candidates.jsonl`

### AI 候选示例
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3831/动物_野生动物3831.glb`: score=100, risk=high, evidence=静态关键词命中 `ai`: meshy_ai_the_cricket_from_aes_1217155258_texture; 静态关键词命中 `meshy`: meshy_ai_the_cricket_from_aes_1217155258_texture
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象18128/手办_Q版形象18128.glb`: score=100, risk=high, evidence=静态关键词命中 `ai`: meshy_ai_pink_polka_dot_bow_0301191820_texture; 静态关键词命中 `meshy`: meshy_ai_pink_polka_dot_bow_0301191820_texture
- `手办_不包含PBR和骨骼_写实风_2997(1)/手办_Q版形象/手办_Q版形象19637/手办_Q版形象19637.glb`: score=100, risk=high, evidence=静态关键词命中 `ai`: meshy_ai_mario_hat_0321171241_texture; 静态关键词命中 `meshy`: meshy_ai_mario_hat_0321171241_texture
- `手办_不包含PBR和骨骼_写实风_4009(1)(1)/手办_Q版形象/手办_Q版形象13542/手办_Q版形象13542.glb`: score=100, risk=high, evidence=静态关键词命中 `ai`: meshy_ai_mario_hat_0321171241_texture; 静态关键词命中 `meshy`: meshy_ai_mario_hat_0321171241_texture
- `游戏角色_不包含PBR和骨骼_写实风_4084(2)(1)/游戏角色_风格化类人角色/游戏角色_风格化类人角色21178/游戏角色_风格化类人角色21178.glb`: score=100, risk=high, evidence=静态关键词命中 `ai`: meshy_ai_prismatic_crown_0408150810_texture_fbx; 静态关键词命中 `meshy`: meshy_ai_prismatic_crown_0408150810_texture_fbx
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物17867/动物_野生动物17867.glb`: score=75, risk=high, evidence=静态关键词命中 `tripo`: tripo_node_c5951e99-e4bd-4f05-b260-b654760ebc4c_0
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物17995/动物_野生动物17995.glb`: score=75, risk=high, evidence=静态关键词命中 `tripo`: sheep_tripo_mat_a8d75da6_0.002
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18130/动物_野生动物18130.glb`: score=75, risk=high, evidence=静态关键词命中 `tripo`: tripo_mat_8f4d3c56-6492-4513-9b33-397714b84be9
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18428/动物_野生动物18428.glb`: score=75, risk=high, evidence=静态关键词命中 `tripo`: tripo_mat_b5827c0c-9b93-471a-8e6a-146ddaa7406d.002
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18554/动物_野生动物18554.glb`: score=75, risk=high, evidence=静态关键词命中 `tripo`: tripo_node_3add7022-87a1-4253-8d03-5f4656edf0e1_0

## 抽样示例

### rejected
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物677/动物_农场动物677.glb`: gore_keyword_suspect
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物17737/动物_野生动物17737.glb`: too_many_faces
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物17742/动物_野生动物17742.glb`: too_many_faces
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物17888/动物_野生动物17888.glb`: unreadable_images
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物17936/动物_野生动物17936.glb`: too_many_faces
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物17996/动物_野生动物17996.glb`: too_many_faces
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18160/动物_野生动物18160.glb`: too_many_faces
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18337/动物_野生动物18337.glb`: too_many_faces
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18396/动物_野生动物18396.glb`: too_many_faces
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18464/动物_野生动物18464.glb`: too_many_faces
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_野生动物/动物_野生动物18543/动物_野生动物18543.glb`: too_many_faces
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3257/动物_野生动物3257.glb`: too_many_faces
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3273/动物_野生动物3273.glb`: too_many_faces
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3303/动物_野生动物3303.glb`: textures_without_uv
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3350/动物_野生动物3350.glb`: textures_without_uv
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3351/动物_野生动物3351.glb`: textures_without_uv
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3435/动物_野生动物3435.glb`: textures_without_uv
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3472/动物_野生动物3472.glb`: textures_without_uv
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3537/动物_野生动物3537.glb`: textures_without_uv
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3539/动物_野生动物3539.glb`: textures_without_uv
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3560/动物_野生动物3560.glb`: textures_without_uv
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3658/动物_野生动物3658.glb`: textures_without_uv
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3662/动物_野生动物3662.glb`: textures_without_uv
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3674/动物_野生动物3674.glb`: textures_without_uv
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3724/动物_野生动物3724.glb`: textures_without_uv
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3732/动物_野生动物3732.glb`: textures_without_uv
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3881/动物_野生动物3881.glb`: too_many_faces
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3911/动物_野生动物3911.glb`: too_many_faces
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3913/动物_野生动物3913.glb`: too_many_faces
- `动物_包含PBR和骨骼_写实风_1454(1)/动物_野生动物/动物_野生动物3916/动物_野生动物3916.glb`: too_many_faces

### review
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物608/动物_农场动物608.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物609/动物_农场动物609.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物610/动物_农场动物610.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物611/动物_农场动物611.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物612/动物_农场动物612.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物613/动物_农场动物613.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物614/动物_农场动物614.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物615/动物_农场动物615.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物616/动物_农场动物616.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物617/动物_农场动物617.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物618/动物_农场动物618.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物619/动物_农场动物619.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物620/动物_农场动物620.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物621/动物_农场动物621.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物622/动物_农场动物622.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物623/动物_农场动物623.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物624/动物_农场动物624.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物625/动物_农场动物625.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物626/动物_农场动物626.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物627/动物_农场动物627.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物628/动物_农场动物628.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物629/动物_农场动物629.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物630/动物_农场动物630.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物631/动物_农场动物631.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物632/动物_农场动物632.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物633/动物_农场动物633.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物639/动物_农场动物639.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物640/动物_农场动物640.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物641/动物_农场动物641.glb`: high_poly_model
- `动物_不包含PBR和骨骼_写实风_1730(1)(1)/动物_农场动物/动物_农场动物642/动物_农场动物642.glb`: high_poly_model

## 使用建议

- `rejected` 先修复或剔除：解析失败、缺贴图、贴图不可读、GLTF 引用错误、血腥风险词、面数极端异常会直接影响验收。
- `review` 建议人工抽检：疑似 AI、疑似武器/暴力词、高模、无贴图/无 PBR、无 normal、远程贴图 URI 都不一定错误，但需要业务确认。
- 静态检查不能替代最终渲染审核；上线前建议对 `review` 和少量 `accepted` 样本再用 Blender/three.js 批量渲染缩略图复核。
- 如果项目要求必须贴图/PBR，运行时加 `--require-textures --require-pbr`；如果不允许 AI 资产，加 `--reject-ai`。
