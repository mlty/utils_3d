# utils_3d

用于 3D 训练数据筛选和质量检查的脚本集合。仓库只发布工具源码和说明，不提供数据集、模型、渲染图、批量报告或访问凭据。

| 目录 | 用途 |
| --- | --- |
| [data_filter](./data_filter/) | 跨数据源筛选、去重与微调候选集生成；包含 ObjaverseXL、Step1X 和 TexVerse 工具。 |
| [cg_data](./cg_data/)、[tex_data](./tex_data/)、[step1x](./step1x/) | 按数据来源汇总审核结果，导出可用元数据。 |
| [jiaguyi_eval](./jiaguyi_eval/) | GLB 结构、几何和纹理审核、重复检测及可选视觉复核。 |
| [eval_3d_data_from_blender](./eval_3d_data_from_blender/)、[eval_3d_data_from_vllm](./eval_3d_data_from_vllm/) | 分别从模型文件和多视角渲染图检查资产质量。 |
| [家具数据分析](./家具数据分析/) | 从元数据中提取家具与家居类候选。 |

例如，运行 `python3 jiaguyi_eval/glb_quality_audit.py --help` 查看资产审核选项，或运行 `python3 resize_glb.py --help` 查看 GLB 压缩选项。实际处理前请准备输入数据，并检查各脚本的路径配置；部分历史批处理脚本依赖特定的集群目录、Blender 或 GPU 环境。

可选的 ModelScope 上传工具用法为 `python3 upload_files.py OWNER/MODEL LOCAL_FOLDER`。需安装 `modelscope`，并通过环境变量 `MODELSCOPE_API_TOKEN` 提供令牌。不要将令牌写入源码。