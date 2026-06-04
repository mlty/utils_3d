# GLB 质量验收报告

## 总览
- 数据集状态: **rejected**
- 扫描目录: `/Users/mlty/Downloads/机甲_不包含PBR和骨骼_写实风_536`
- 输入清单: `None`
- 发现模型数: 475
- 记录总数: 475
- 可解析/可打开数: 475 (100.00%)
- 解析失败数: 0 (0.00%)
- 缺失清单文件数: 0
- 运行耗时: 3.501s

- 期望数量: 536，数量是否匹配: False

## 验收状态

- review: 463 (97.47%)
- rejected: 12 (2.53%)

## 精度分布

- high: 475 (100.00%)

## 主要问题

- review:high_poly_model: 475
- review:violence_keyword_suspect: 15
- review:unused_images: 12
- reject:textures_without_uv: 7
- reject:too_many_faces: 4
- review:ai_asset_suspect: 3
- reject:gore_keyword_suspect: 1

## Rejected 明细

- 明细文件: `rejected_detail.md` / `rejected_detail.csv` / `rejected_detail.jsonl`
- 每条 rejected 都会给出机器原因、中文说明、具体证据和建议处理动作。

## AI 资产识别

- AI 候选数: 3
- 静态关键词命中数: 3
- LLM 判断 AI 数: 0
- LLM 不确定数: 0
- 风险分布: {'no_evidence': 472, 'low': 1, 'high': 2}
- 候选明细: `ai_candidates.md` / `ai_candidates.csv` / `ai_candidates.jsonl`

### AI 候选示例
- `机甲_机器人/机甲_机器人11983/机甲_机器人11983.glb`: score=75, risk=high, evidence=静态关键词命中 `tripo`: tripo_part_5_material
- `机甲_机器人/机甲_机器人11987/机甲_机器人11987.glb`: score=75, risk=high, evidence=静态关键词命中 `tripo`: tripo_mat_4304b6aa-c1de-4988-bcd9-6435020239e8
- `机甲_机器人/机甲_机器人11732/机甲_机器人11732.glb`: score=20, risk=low, evidence=静态关键词命中 `ai`: tank_front_hatch_3_low_ai_tank_3_0

## 贴图抽取

- 抽取贴图总数: 3589
- 状态分布: {'ok': 475}
- 图片位置: 每个 GLB 当前目录下的 `imgs/`

## 抽样示例

### rejected
- `机甲_战舰/机甲_战舰3346/机甲_战舰3346.glb`: textures_without_uv
- `机甲_战舰/机甲_战舰3347/机甲_战舰3347.glb`: textures_without_uv
- `机甲_战舰/机甲_战舰3360/机甲_战舰3360.glb`: too_many_faces
- `机甲_战舰/机甲_战舰3372/机甲_战舰3372.glb`: too_many_faces
- `机甲_战舰/机甲_战舰3447/机甲_战舰3447.glb`: textures_without_uv
- `机甲_机器人/机甲_机器人11643/机甲_机器人11643.glb`: textures_without_uv
- `机甲_机器人/机甲_机器人11652/机甲_机器人11652.glb`: gore_keyword_suspect
- `机甲_机器人/机甲_机器人11703/机甲_机器人11703.glb`: textures_without_uv
- `机甲_机器人/机甲_机器人11721/机甲_机器人11721.glb`: textures_without_uv
- `机甲_机器人/机甲_机器人11731/机甲_机器人11731.glb`: too_many_faces
- `机甲_机器人/机甲_机器人11907/机甲_机器人11907.glb`: too_many_faces
- `机甲_机器人/机甲_机器人11993/机甲_机器人11993.glb`: textures_without_uv

### review
- `机甲_战舰/机甲_战舰3328/机甲_战舰3328.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3329/机甲_战舰3329.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3330/机甲_战舰3330.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3332/机甲_战舰3332.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3333/机甲_战舰3333.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3334/机甲_战舰3334.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3335/机甲_战舰3335.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3336/机甲_战舰3336.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3337/机甲_战舰3337.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3338/机甲_战舰3338.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3339/机甲_战舰3339.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3340/机甲_战舰3340.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3341/机甲_战舰3341.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3343/机甲_战舰3343.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3344/机甲_战舰3344.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3345/机甲_战舰3345.glb`: high_poly_model, unused_images
- `机甲_战舰/机甲_战舰3348/机甲_战舰3348.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3349/机甲_战舰3349.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3350/机甲_战舰3350.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3351/机甲_战舰3351.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3352/机甲_战舰3352.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3353/机甲_战舰3353.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3356/机甲_战舰3356.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3357/机甲_战舰3357.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3358/机甲_战舰3358.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3359/机甲_战舰3359.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3361/机甲_战舰3361.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3362/机甲_战舰3362.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3363/机甲_战舰3363.glb`: high_poly_model
- `机甲_战舰/机甲_战舰3364/机甲_战舰3364.glb`: high_poly_model

## 使用建议

- `rejected` 先修复或剔除：解析失败、缺贴图、贴图不可读、GLTF 引用错误、血腥风险词、面数极端异常会直接影响验收。
- `review` 建议人工抽检：疑似 AI、疑似武器/暴力词、高模、无贴图/无 PBR、无 normal、远程贴图 URI 都不一定错误，但需要业务确认。
- 静态检查不能替代最终渲染审核；上线前建议对 `review` 和少量 `accepted` 样本再用 Blender/three.js 批量渲染缩略图复核。
- 如果项目要求必须贴图/PBR，运行时加 `--require-textures --require-pbr`；如果不允许 AI 资产，加 `--reject-ai`。
