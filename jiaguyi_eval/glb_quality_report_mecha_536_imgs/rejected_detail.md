# Rejected 资产明细

每条记录包含拒收原因、可读说明、具体证据和建议处理动作。

## 机甲_战舰/机甲_战舰3346/机甲_战舰3346.glb
- 状态: rejected，LOD: high，faces: 325242，file_mb: 43.3302
- 拒收原因: textures_without_uv
- 原因说明: textures_without_uv: 贴图缺 UV - 材质使用了贴图，但对应 primitive 缺少 TEXCOORD，贴图无法正确映射。
- 具体证据: mesh[0].primitive[3] material[3] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[3] material[3] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[3] material[3] normalTexture needs TEXCOORD_0; mesh[0].primitive[81] material[81] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[81] material[81] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[81] material[81] normalTexture needs TEXCOORD_0; mesh[0].primitive[82] material[82] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[82] material[82] metallicRoughnessTexture needs TEXCOORD_0
- 处理建议: textures_without_uv: 补 UV 后重新导出；如果不需要贴图，应移除材质里的贴图引用。
- 错误: mesh[0].primitive[3] material[3] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[3] material[3] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[3] material[3] normalTexture needs TEXCOORD_0; mesh[0].primitive[81] material[81] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[81] material[81] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[81] material[81] normalTexture needs TEXCOORD_0; mesh[0].primitive[82] material[82] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[82] material[82] metallicRoughnessTexture needs TEXCOORD_0

## 机甲_战舰/机甲_战舰3347/机甲_战舰3347.glb
- 状态: rejected，LOD: high，faces: 834938，file_mb: 59.1706
- 拒收原因: textures_without_uv
- 原因说明: textures_without_uv: 贴图缺 UV - 材质使用了贴图，但对应 primitive 缺少 TEXCOORD，贴图无法正确映射。
- 具体证据: mesh[0].primitive[0] material[0] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] normalTexture needs TEXCOORD_0; mesh[0].primitive[9] material[9] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[9] material[9] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[9] material[9] normalTexture needs TEXCOORD_0; mesh[0].primitive[12] material[12] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[12] material[12] metallicRoughnessTexture needs TEXCOORD_0
- 处理建议: textures_without_uv: 补 UV 后重新导出；如果不需要贴图，应移除材质里的贴图引用。
- 错误: mesh[0].primitive[0] material[0] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] normalTexture needs TEXCOORD_0; mesh[0].primitive[9] material[9] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[9] material[9] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[9] material[9] normalTexture needs TEXCOORD_0; mesh[0].primitive[12] material[12] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[12] material[12] metallicRoughnessTexture needs TEXCOORD_0

## 机甲_战舰/机甲_战舰3360/机甲_战舰3360.glb
- 状态: rejected，LOD: high，faces: 2369536，file_mb: 87.1267
- 拒收原因: too_many_faces
- 原因说明: too_many_faces: 面数过高 - 三角面数量超过验收上限，会带来加载、渲染和存储风险。
- 具体证据: face_count=2369536, max_faces=2000000
- 处理建议: too_many_faces: 做减面/LOD，或把高模作为源资产，交付实时资产时使用优化版本。

## 机甲_战舰/机甲_战舰3372/机甲_战舰3372.glb
- 状态: rejected，LOD: high，faces: 2369536，file_mb: 86.9953
- 拒收原因: too_many_faces
- 原因说明: too_many_faces: 面数过高 - 三角面数量超过验收上限，会带来加载、渲染和存储风险。
- 具体证据: face_count=2369536, max_faces=2000000
- 处理建议: too_many_faces: 做减面/LOD，或把高模作为源资产，交付实时资产时使用优化版本。

## 机甲_战舰/机甲_战舰3447/机甲_战舰3447.glb
- 状态: rejected，LOD: high，faces: 157137，file_mb: 13.6931
- 拒收原因: textures_without_uv
- 原因说明: textures_without_uv: 贴图缺 UV - 材质使用了贴图，但对应 primitive 缺少 TEXCOORD，贴图无法正确映射。
- 具体证据: mesh[0].primitive[1] material[1] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[4] material[4] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[5] material[5] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[6] material[6] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[9] material[9] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[19] material[19] metallicRoughnessTexture needs TEXCOORD_0
- 处理建议: textures_without_uv: 补 UV 后重新导出；如果不需要贴图，应移除材质里的贴图引用。
- 错误: mesh[0].primitive[1] material[1] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[4] material[4] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[5] material[5] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[6] material[6] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[9] material[9] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[19] material[19] metallicRoughnessTexture needs TEXCOORD_0

## 机甲_机器人/机甲_机器人11643/机甲_机器人11643.glb
- 状态: rejected，LOD: high，faces: 211270，file_mb: 33.8679
- 拒收原因: textures_without_uv
- 原因说明: textures_without_uv: 贴图缺 UV - 材质使用了贴图，但对应 primitive 缺少 TEXCOORD，贴图无法正确映射。
- 具体证据: mesh[0].primitive[0] material[0] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] normalTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] normalTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] metallicRoughnessTexture needs TEXCOORD_0
- 处理建议: textures_without_uv: 补 UV 后重新导出；如果不需要贴图，应移除材质里的贴图引用。
- 错误: mesh[0].primitive[0] material[0] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] normalTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] normalTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] metallicRoughnessTexture needs TEXCOORD_0

## 机甲_机器人/机甲_机器人11652/机甲_机器人11652.glb
- 状态: rejected，LOD: high，faces: 208848，file_mb: 6.5757
- 拒收原因: gore_keyword_suspect
- 原因说明: gore_keyword_suspect: 疑似血腥违规 - 路径或模型元数据命中血腥/尸体/伤口等关键词。
- 具体证据: flesh: ghidorah_flesh.002
- 处理建议: gore_keyword_suspect: 优先人工检查六视角渲染图；确认命中后剔除。

## 机甲_机器人/机甲_机器人11703/机甲_机器人11703.glb
- 状态: rejected，LOD: high，faces: 568392，file_mb: 28.417
- 拒收原因: textures_without_uv
- 原因说明: textures_without_uv: 贴图缺 UV - 材质使用了贴图，但对应 primitive 缺少 TEXCOORD，贴图无法正确映射。
- 具体证据: mesh[0].primitive[1] material[1] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] normalTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] normalTexture needs TEXCOORD_0
- 处理建议: textures_without_uv: 补 UV 后重新导出；如果不需要贴图，应移除材质里的贴图引用。
- 错误: mesh[0].primitive[1] material[1] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] normalTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] normalTexture needs TEXCOORD_0

## 机甲_机器人/机甲_机器人11721/机甲_机器人11721.glb
- 状态: rejected，LOD: high，faces: 1503176，file_mb: 54.2935
- 拒收原因: textures_without_uv
- 原因说明: textures_without_uv: 贴图缺 UV - 材质使用了贴图，但对应 primitive 缺少 TEXCOORD，贴图无法正确映射。
- 具体证据: mesh[0].primitive[0] material[0] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] normalTexture needs TEXCOORD_0; mesh[0].primitive[70] material[70] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[70] material[70] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[70] material[70] normalTexture needs TEXCOORD_0
- 处理建议: textures_without_uv: 补 UV 后重新导出；如果不需要贴图，应移除材质里的贴图引用。
- 错误: mesh[0].primitive[0] material[0] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] normalTexture needs TEXCOORD_0; mesh[0].primitive[70] material[70] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[70] material[70] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[70] material[70] normalTexture needs TEXCOORD_0

## 机甲_机器人/机甲_机器人11731/机甲_机器人11731.glb
- 状态: rejected，LOD: high，faces: 3882829，file_mb: 177.6637
- 拒收原因: too_many_faces
- 原因说明: too_many_faces: 面数过高 - 三角面数量超过验收上限，会带来加载、渲染和存储风险。
- 具体证据: face_count=3882829, max_faces=2000000
- 处理建议: too_many_faces: 做减面/LOD，或把高模作为源资产，交付实时资产时使用优化版本。

## 机甲_机器人/机甲_机器人11907/机甲_机器人11907.glb
- 状态: rejected，LOD: high，faces: 2945376，file_mb: 11.582
- 拒收原因: too_many_faces
- 原因说明: too_many_faces: 面数过高 - 三角面数量超过验收上限，会带来加载、渲染和存储风险。
- 具体证据: face_count=2945376, max_faces=2000000
- 处理建议: too_many_faces: 做减面/LOD，或把高模作为源资产，交付实时资产时使用优化版本。

## 机甲_机器人/机甲_机器人11993/机甲_机器人11993.glb
- 状态: rejected，LOD: high，faces: 178062，file_mb: 20.8815
- 拒收原因: textures_without_uv
- 原因说明: textures_without_uv: 贴图缺 UV - 材质使用了贴图，但对应 primitive 缺少 TEXCOORD，贴图无法正确映射。
- 具体证据: mesh[0].primitive[0] material[0] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] normalTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] normalTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] metallicRoughnessTexture needs TEXCOORD_0
- 处理建议: textures_without_uv: 补 UV 后重新导出；如果不需要贴图，应移除材质里的贴图引用。
- 错误: mesh[0].primitive[0] material[0] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[0] material[0] normalTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] metallicRoughnessTexture needs TEXCOORD_0; mesh[0].primitive[1] material[1] normalTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] baseColorTexture needs TEXCOORD_0; mesh[0].primitive[2] material[2] metallicRoughnessTexture needs TEXCOORD_0
