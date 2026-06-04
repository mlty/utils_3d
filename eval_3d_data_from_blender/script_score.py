# import bpy
# import os
# import sys
# from mathutils import Vector

# def check_transparency(file_path):
#     # 获取场景中的所有对象
#     num = 0
#     all_num = 0
#     for obj in bpy.context.scene.objects:
#         if obj.type == 'MESH':  # 只对网格对象进行操作
#             for material_slot in obj.material_slots:  # 遍历每个材质
#                 material = material_slot.material
#                 if material and material.use_nodes:  # 确保材质使用节点
#                     for node in material.node_tree.nodes:
#                         if node.type == 'BSDF_PRINCIPLED':  # 使用 Principled BSDF 节点
#                             # 检查是否有透明纹理
#                             if 'Alpha' in node.inputs:
#                                 if node.inputs['Alpha'].is_linked:
#                                     print(f"Material {material.name} has a transparency texture linked.")
#                                     num += 1
#                             all_num += 1
    
#     record = []
#     issues = []

#     for mat in bpy.data.materials:
#         if not mat.use_nodes:
#             continue

#         blend_mode = mat.blend_method
#         for node in mat.node_tree.nodes:
#             if node.type == 'BSDF_PRINCIPLED':
#                 alpha = node.inputs['Alpha'].default_value
#                 alpha_linked = node.inputs['Alpha'].is_linked
#                 if blend_mode == 'OPAQUE':
#                     # 只允许 Alpha 接近 1
#                     if alpha < 0.99 and not alpha_linked:
#                         issues.append((mat.name, blend_mode, alpha, "OPAQUE but Alpha<0.99"))
#                 if blend_mode in ('BLEND', 'CLIP'):
#                     if not alpha_linked and alpha >= 0.99:
#                         issues.append((mat.name, blend_mode, alpha, "Has no transparency but Blend/Clip mode"))
#                     else:
#                         issues.append((mat.name, blend_mode, alpha, "Using transparency (valid or intentional)"))
    
#     if issues:
#         for mat_name, mode, alpha, desc in issues:
#             record.append(file_path)
#     else:
#         return 0, 0, 0
    
#     return num, all_num, len(record)

# def analyze_materials(file_path):
#     if not bpy.data.materials:
#         return 0.0, 0.0
    
#     color_tag, material_tag, color_num, material_num = 0, 0, 0, 0
#     for mat in bpy.data.materials:

#         if not mat.use_nodes:
#             continue

#         bsdf_nodes = [n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED']
#         tex_nodes = [n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE']

#         # 读取 Base Color
#         if bsdf_nodes:
#             base_color = bsdf_nodes[0].inputs['Base Color'].default_value
#             base_color_tuple = tuple(base_color[:3])  # 只获取 RGB 部分
#             alpha = base_color[3]  # 获取 Alpha 值
            
#             # 判断是否为白色
#             if base_color_tuple != (1.0, 1.0, 1.0) and alpha != 0.0:
#                 color_tag += 1
#             color_num += 1
        
#         if tex_nodes:
#             for tex_node in tex_nodes:
#                 image = tex_node.image
#                 if image:
#                     filepath = bpy.path.abspath(image.filepath)
#                     exists = os.path.isfile(filepath)
#                     if exists:
#                         material_tag += 1
#                 material_num += 1
    
#     return color_num, color_tag

# def find_paintings_in_gltf():
#     """
#     在指定的 GLB/glTF 文件中查找可能代表“画作”的网格对象。
#     """

#     try:

#         # 找到所有网格对象
#         mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
        
#         if not mesh_objects:
#             return

#         # 获取场景单位设置（例如：米、毫米、厘米）
#         unit_system = bpy.context.scene.unit_settings.system
#         scale_factor = bpy.context.scene.unit_settings.scale_length
        
#         # 计算全局边界框
#         min_coords = [float('inf')] * 3
#         max_coords = [float('-inf')] * 3
        
#         for obj in mesh_objects:
#             # 获取对象的世界矩阵，用于将局部坐标转换为全局坐标
#             matrix_world = obj.matrix_world
            
#             # 遍历对象边界框的八个角点
#             for corner in obj.bound_box:
#                 global_corner = matrix_world @ Vector(corner)
#                 for i in range(3):
#                     min_coords[i] = min(min_coords[i], global_corner[i])
#                     max_coords[i] = max(max_coords[i], global_corner[i])
                    
#         # 计算尺寸
#         length = max_coords[0] - min_coords[0]
#         width = max_coords[1] - min_coords[1]
#         height = max_coords[2] - min_coords[2]

#         # 将尺寸转换为真实单位
#         length_real = length * scale_factor
#         width_real = width * scale_factor
#         height_real = height * scale_factor

#         return length_real, width_real, height_real

#     except Exception as e:
#         print(f"处理文件时出错: {e}")
    
# if __name__ == "__main__":

#     argv = sys.argv
#     if "--" in argv:
#         argv = argv[argv.index("--") + 1:]
#     else:
#         argv = []

#     if len(argv) < 2:
#         print("用法: blender --background --python script.py -- 输入.blend 输出.glb")
#         sys.exit(1)
    
#     file_path_list = [p.strip() for p in os.path.abspath(argv[0]).split('|')]

#     for file_path in file_path_list:

#         bpy.ops.wm.read_homefile(use_empty=True)
#         bpy.ops.import_scene.gltf(filepath=file_path)

#         # 使用方法：先导入 glb 模型，再运行
#         num, all_num, score = check_transparency(file_path) # 检查透明度问题
#         color_num, color_tag = analyze_materials(file_path) # 分析材质 （检测白模）
#         length_real, width_real, height_real = find_paintings_in_gltf() # 检测卡片状
#         print('data [',file_path, num, all_num, score, color_num, color_tag, length_real, width_real, height_real, ']')
        
import bpy
import os
import sys
from mathutils import Vector

def check_transparency(file_path):
    num = 0
    all_num = 0
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
            for material_slot in obj.material_slots:
                material = material_slot.material
                if material and material.use_nodes:
                    for node in material.node_tree.nodes:
                        if node.type == 'BSDF_PRINCIPLED':
                            if 'Alpha' in node.inputs:
                                if node.inputs['Alpha'].is_linked:
                                    print(f"Material {material.name} has a transparency texture linked.")
                                    num += 1
                            all_num += 1
    
    record = []
    issues = []

    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue

        blend_mode = mat.blend_method
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                alpha = node.inputs['Alpha'].default_value
                alpha_linked = node.inputs['Alpha'].is_linked
                if blend_mode == 'OPAQUE':
                    if alpha < 0.99 and not alpha_linked:
                        issues.append((mat.name, blend_mode, alpha, "OPAQUE but Alpha<0.99"))
                if blend_mode in ('BLEND', 'CLIP'):
                    if not alpha_linked and alpha >= 0.99:
                        issues.append((mat.name, blend_mode, alpha, "Has no transparency but Blend/Clip mode"))
                    else:
                        issues.append((mat.name, blend_mode, alpha, "Using transparency (valid or intentional)"))
    
    if issues:
        for mat_name, mode, alpha, desc in issues:
            record.append(file_path)
    else:
        return 0, 0, 0
    
    return num, all_num, len(record)

def analyze_materials(file_path):
    color_tag, material_tag, color_num, material_num = 0, 0, 0, 0
    for mat in bpy.data.materials:

        if not mat.use_nodes:
            continue

        bsdf_nodes = [n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED']
        tex_nodes = [n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE']

        if bsdf_nodes:
            base_color = bsdf_nodes[0].inputs['Base Color'].default_value
            base_color_tuple = tuple(base_color[:3])
            alpha = base_color[3]
            if base_color_tuple != (1.0, 1.0, 1.0) and alpha != 0.0:
                color_tag += 1
            color_num += 1
        
        if tex_nodes:
            for tex_node in tex_nodes:
                image = tex_node.image
                if image:
                    filepath = bpy.path.abspath(image.filepath)
                    if os.path.isfile(filepath):
                        material_tag += 1
                material_num += 1
    
    return color_num, color_tag, material_tag, material_num

def export_textures_to_glb_dir(glb_path):

    save_dir = os.path.dirname(glb_path)
    img_num = 0
    for img in bpy.data.images:

        # 跳过没有数据的图片
        if img.size[0] == 0:
            continue

        # 取原始文件名
        name = os.path.basename(img.filepath)
        if name == "":
            name = img.name + ".png"

        save_path = os.path.join(save_dir, name)

        try:
            img.save_render(save_path)
            img_num += 1
        except Exception as e:
            print("Failed:", img.name, e)
    
    return img_num

def find_paintings_in_gltf():
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    if not mesh_objects:
        return 0, 0, 0, 0, 0
    
    scale_factor = bpy.context.scene.unit_settings.scale_length

    min_coords = [float('inf')] * 3
    max_coords = [float('-inf')] * 3

    total_edges = 0
    total_faces = 0

    for obj in mesh_objects:
        matrix_world = obj.matrix_world
        for corner in obj.bound_box:
            global_corner = matrix_world @ Vector(corner)
            for i in range(3):
                min_coords[i] = min(min_coords[i], global_corner[i])
                max_coords[i] = max(max_coords[i], global_corner[i])
        
        if obj.data:
            total_edges += len(obj.data.edges)
            total_faces += len(obj.data.polygons)

    length = (max_coords[0] - min_coords[0]) * scale_factor
    width = (max_coords[1] - min_coords[1]) * scale_factor
    height = (max_coords[2] - min_coords[2]) * scale_factor

    mesh_count = len(mesh_objects)

    return length, width, height, total_edges, total_faces, mesh_count

def get_file_size(file_path):
    if os.path.isfile(file_path):
        return os.path.getsize(file_path)
    return 0

if __name__ == "__main__":

    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    if len(argv) < 1:
        print("用法: blender --background --python script.py -- 输入.glb|输入.glb")
        sys.exit(1)
    
    file_path_list = [p.strip() for p in os.path.abspath(argv[0]).split('|')]

    for file_path in file_path_list:

        bpy.ops.wm.read_homefile(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=file_path)
        
        # 检查透明度
        # num, all_num, score = check_transparency(file_path)

        # find path
        img_num = export_textures_to_glb_dir(file_path)

        # 分析材质
        # color_num, color_tag, material_tag, material_num = analyze_materials(file_path)

        # 检查尺寸和边/面数量
        length_real, width_real, height_real, total_edges, total_faces, mesh_count = find_paintings_in_gltf()
        
        print('data [', file_path, img_num, length_real, width_real, height_real,
              total_edges, total_faces, mesh_count, ']')
        