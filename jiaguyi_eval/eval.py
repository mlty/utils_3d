import os
import re
from collections import Counter, defaultdict

def calc1():
    root_dir = "/mnt/vast/hongyuan/jiaguyi8/raw"

    # 需要统计的文件类型
    exts = {".glb", ".gltf", ".fbx", ".obj"}

    total_count = defaultdict(int)
    first_level_count = defaultdict(lambda: defaultdict(int))

    for root, dirs, files in os.walk(root_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in exts:
                total_count[ext] += 1

                full_path = os.path.join(root, file)
                
                # 获取一级目录
                rel_path = os.path.relpath(full_path, root_dir)
                parts = rel_path.split(os.sep)

                first_level = parts[0] if len(parts) > 1 else "root"

                first_level_count[first_level][ext] += 1

    # 打印总统计
    print("===== 总体统计 =====")
    for ext, count in total_count.items():
        print(f"{ext}: {count}")

    print("\n===== 一级目录统计 =====")
    for folder, counts in first_level_count.items():
        print(f"\n{folder}")
        for ext, count in counts.items():
            print(f"  {ext}: {count}")


def parse_pbr_bone_flags(text):
    text = text.lower().replace(' ', '')

    negative_both_patterns = [
        '不包含pbr和骨骼',
        '不包含pbr与骨骼',
        '不含pbr和骨骼',
        '不含pbr与骨骼',
        '无pbr和骨骼',
        '无pbr与骨骼',
    ]
    positive_both_patterns = [
        '包含pbr和骨骼',
        '包含pbr与骨骼',
        '含pbr和骨骼',
        '含pbr与骨骼',
    ]

    if any(pattern in text for pattern in negative_both_patterns):
        return False, False
    if any(pattern in text for pattern in positive_both_patterns):
        return True, True

    has_pbr = None
    has_bone = None
    if any(pattern in text for pattern in ['不包含pbr', '不含pbr', '无pbr']):
        has_pbr = False
    elif 'pbr' in text:
        has_pbr = True

    if any(pattern in text for pattern in ['不包含骨骼', '不含骨骼', '无骨骼']):
        has_bone = False
    elif '骨骼' in text:
        has_bone = True

    return has_pbr, has_bone


def pbr_bone_category(has_pbr, has_bone):
    if has_pbr is True and has_bone is True:
        return '包含PBR和骨骼'
    if has_pbr is True and has_bone is False:
        return '仅包含PBR'
    if has_pbr is False and has_bone is True:
        return '仅包含骨骼'
    if has_pbr is False and has_bone is False:
        return '不包含PBR和骨骼'
    return '未知'


def print_pbr_bone_stats():
    root_dir = "/mnt/vast/hongyuan/jiaguyi8/raw"
    exts = {".glb", ".gltf", ".fbx", ".obj"}
    category_order = [
        '包含PBR和骨骼',
        '仅包含PBR',
        '仅包含骨骼',
        '不包含PBR和骨骼',
        '未知',
    ]

    total_count = 0
    category_count = defaultdict(int)
    ext_category_count = defaultdict(lambda: defaultdict(int))
    first_level_count = defaultdict(lambda: defaultdict(int))
    unknown_examples = []

    for root, dirs, files in os.walk(root_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in exts:
                continue

            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, root_dir)
            parts = rel_path.split(os.sep)
            first_level = parts[0] if len(parts) > 1 else 'root'

            has_pbr, has_bone = parse_pbr_bone_flags(first_level)
            if has_pbr is None or has_bone is None:
                fallback_pbr, fallback_bone = parse_pbr_bone_flags(rel_path)
                if has_pbr is None:
                    has_pbr = fallback_pbr
                if has_bone is None:
                    has_bone = fallback_bone

            category = pbr_bone_category(has_pbr, has_bone)
            total_count += 1
            category_count[category] += 1
            ext_category_count[ext][category] += 1
            first_level_count[first_level][category] += 1
            if category == '未知' and len(unknown_examples) < 20:
                unknown_examples.append(full_path)

    print('===== PBR / 骨骼 总体统计 =====')
    print('总文件数:', total_count)
    for category in category_order:
        count = category_count[category]
        ratio = count / total_count * 100 if total_count > 0 else 0.0
        print(f'{category}: {count} ({ratio:.2f}%)')

    print('\n===== 按文件类型统计 =====')
    for ext in sorted(ext_category_count.keys()):
        print(ext)
        for category in category_order:
            count = ext_category_count[ext][category]
            if count > 0:
                print(f'  {category}: {count}')

    print('\n===== 一级目录统计 =====')
    for folder in sorted(first_level_count.keys()):
        folder_total = sum(first_level_count[folder].values())
        print(f'\n{folder} (总文件数: {folder_total})')
        for category in category_order:
            count = first_level_count[folder][category]
            if count > 0:
                ratio = count / folder_total * 100 if folder_total > 0 else 0.0
                print(f'  {category}: {count} ({ratio:.2f}%)')

    if unknown_examples:
        print('\n===== 未识别示例 =====')
        for path in unknown_examples:
            print(path)


MATERIAL_IMAGE_EXTS = {
    '.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff', '.tga', '.exr', '.hdr'
}
AI_MATERIAL_KEYWORDS = {
    'meshy',
    'tripo',
    'hunyuan',
    'hunyuan3d',
    'aigc',
    'genai',
    'ai_generated',
    'ai-generated',
    'generated_by_ai',
    'generatedbyai',
    'text_to_3d',
    'text-to-3d',
    'textto3d',
    'txt2img',
    'txt2_3d',
    'rodin',
    '混元',
}
AI_TOKEN_PATTERN = re.compile(r'(^|[^a-z0-9])ai([^a-z0-9]|$)', re.IGNORECASE)


def iter_material_image_names(asset_dir, max_depth=2):
    base_depth = asset_dir.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(asset_dir):
        depth = root.rstrip(os.sep).count(os.sep) - base_depth
        if max_depth >= 0 and depth >= max_depth:
            dirs[:] = []

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in MATERIAL_IMAGE_EXTS:
                full_path = os.path.join(root, file)
                yield os.path.relpath(full_path, asset_dir)


def find_ai_material_image_matches(image_names):
    matches = defaultdict(list)
    for image_name in image_names:
        file_name = os.path.basename(image_name).lower()
        for keyword in AI_MATERIAL_KEYWORDS:
            if keyword.lower() in file_name:
                matches[keyword].append(image_name)
        if AI_TOKEN_PATTERN.search(file_name):
            matches['ai'].append(image_name)
    return {key: sorted(set(value)) for key, value in matches.items()}


def print_ai_asset_stats_by_material_names():
    root_dir = "/mnt/vast/hongyuan/jiaguyi8/raw"
    model_exts = {".glb", ".gltf", ".fbx", ".obj"}
    record_path = 'ai_material_asset_record.txt'

    total_assets = 0
    assets_with_images = 0
    ai_assets = 0
    keyword_count = Counter()
    ext_count = defaultdict(lambda: {'total': 0, 'ai': 0, 'with_images': 0})
    first_level_count = defaultdict(lambda: {'total': 0, 'ai': 0, 'with_images': 0})

    with open(record_path, 'w', encoding='utf-8') as fw:
        for root, dirs, files in os.walk(root_dir):
            model_files = [
                file for file in files
                if os.path.splitext(file)[1].lower() in model_exts
            ]
            if not model_files:
                continue

            image_names = list(iter_material_image_names(root, max_depth=2))
            matches = find_ai_material_image_matches(image_names)
            markers = sorted(matches.keys())
            rel_path = os.path.relpath(root, root_dir)
            parts = rel_path.split(os.sep)
            first_level = parts[0] if rel_path != '.' else 'root'

            for model_file in model_files:
                model_ext = os.path.splitext(model_file)[1].lower()
                model_path = os.path.join(root, model_file)
                total_assets += 1
                ext_count[model_ext]['total'] += 1
                first_level_count[first_level]['total'] += 1

                if image_names:
                    assets_with_images += 1
                    ext_count[model_ext]['with_images'] += 1
                    first_level_count[first_level]['with_images'] += 1

                if not markers:
                    continue

                ai_assets += 1
                ext_count[model_ext]['ai'] += 1
                first_level_count[first_level]['ai'] += 1
                for marker in markers:
                    keyword_count[marker] += 1

                matched_images = []
                for marker in markers:
                    matched_images.extend(matches[marker])
                matched_images = sorted(set(matched_images))
                fw.write(
                    f"{model_path}\tmarkers={','.join(markers)}"
                    f"\tmatched_images={','.join(matched_images)}\n"
                )

    print('===== 材质图片名 AI 资产统计 =====')
    print('总模型文件数:', total_assets)
    print('有材质图片的模型数:', assets_with_images)
    ratio = ai_assets / total_assets * 100 if total_assets > 0 else 0.0
    print(f'疑似 AI 资产数: {ai_assets} ({ratio:.2f}%)')
    print('记录文件:', record_path)

    print('\n===== 关键词命中统计 =====')
    for keyword, count in sorted(keyword_count.items(), key=lambda item: (-item[1], item[0])):
        print(f'{keyword}: {count}')

    print('\n===== 按文件类型统计 =====')
    for ext in sorted(ext_count.keys()):
        stat = ext_count[ext]
        ratio = stat['ai'] / stat['total'] * 100 if stat['total'] > 0 else 0.0
        print(
            f"{ext}: total={stat['total']}, with_images={stat['with_images']}, "
            f"ai={stat['ai']} ({ratio:.2f}%)"
        )

    print('\n===== 一级目录统计 =====')
    for folder in sorted(first_level_count.keys()):
        stat = first_level_count[folder]
        ratio = stat['ai'] / stat['total'] * 100 if stat['total'] > 0 else 0.0
        print(
            f"{folder}: total={stat['total']}, with_images={stat['with_images']}, "
            f"ai={stat['ai']} ({ratio:.2f}%)"
        )
    
import sys
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
from collections import Counter
from dataclasses import dataclass


def calc(image_path):



    img = Image.open(image_path)
    name = image_path.split("\\")[-1].split("/")[-1]
    size = img.size

    # --- 透明度分析 ---
    if img.mode == "RGBA":
        alpha = np.array(img)[:, :, 3]
        transparent_ratio = (alpha == 0).sum() / alpha.size
    else:
        transparent_ratio = 0.0

    # --- 转灰度用于后续分析 ---
    gray = np.array(img.convert("L"), dtype=np.float32)
    rgb = np.array(img.convert("RGB"))

    # --- 空间自相关 (lag=8 on downsampled) ---
    gray_ds = gray[::4, ::4]
    lag = 8
    if gray_ds.shape[1] > lag:
        a = gray_ds[:, :-lag].flatten()
        b = gray_ds[:, lag:].flatten()
        spatial_autocorr = float(np.corrcoef(a, b)[0, 1])
    else:
        spatial_autocorr = 0.0

    return spatial_autocorr


def analysis_for_jiaguyi():
    fw = open('record.txt', 'w')

    hit_num = 0
    all_num= 0
    bad_num = 0
    err_num = 0
    dict = {}
    for i in range(20):
        f = open('/mnt/home/hongyuanzhu/utils_3d/eval_3d_data_from_blender/jiaguyi_8_score'+str(i)+'.txt', 'r')
        for line in f:
            path = line.replace('\n', '').split(' ')[0]
            index = line.replace('\n', '').split(' ')[-7]

            if line.strip() != "":
                all_num += 1
            
            # Image_0.jpg Image_1.png Image_2.jpg

            try:
                num = int(index)
                if num not in dict:
                    dict[num] = 1
                else:
                    dict[num] += 1
                
                if num <= 3:
                    if '动物' in line:

                        print(line)
                        bad_num += 1

                        # tmp = '/'.join(path.split('/')[:-1]) + '/Image_0.jpg'
                        # tmp1 = '/'.join(path.split('/')[:-1]) + '/Image_0.png'
                        # if os.path.exists(tmp):
                        #     score = calc(tmp)

                        #     if score < 0.4:
                        #         print(line.strip().split(' ')[0])
                        #         bad_num += 1
                        #         dict[tmp] = 1
                        #         hit_num += 1
                        #         fw.write('/'.join(line.strip().split(' ')[0].split('/')[:-1]) + '\n')
                        # elif os.path.exists(tmp1):
                        #     score = calc(tmp1)

                        #     if score < 0.4:
                        #         print(line.strip().split(' ')[0])
                        #         bad_num += 1
                        #         dict[tmp1] = 1
                        #         hit_num += 1
                        #         fw.write('/'.join(line.strip().split(' ')[0].split('/')[:-1]) + '\n')
            
            except Exception as e:
                err_num += 1
                print('Err  : ', e)
    
    print('bad num : ', bad_num)

    dict1 = sorted(dict.items(), key=lambda item: item[0])
    cc = 0
    for key in dict1:
        cc += key[1]
    print(dict1)

    print(hit_num)
    print('all : ', all_num)
    print('err : ', err_num)
    print('cc : ', cc)

def print_geo_acc():

    from collections import defaultdict
    import os

    # 精度分类函数
    def classify_faces(faces):
        if faces < 50000:
            return '低精度'
        elif faces <= 150000:
            return '中精度'
        else:
            return '高精度'

    # 整体统计字典，累积 4 个文件的数据
    stats = defaultdict(lambda: {'低精度':0, '中精度':0, '高精度':0})

    for i in range(20):
        file_path = f"/mnt/home/hongyuanzhu/utils_3d/eval_3d_data_from_blender/jiaguyi_8_score{i}.txt"

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 2:
                    continue
                faces = int(parts[-2])
                category = classify_faces(faces)

                path = parts[0]
                path_parts = path.strip(os.sep).split(os.sep)

                # 自动识别顶层目录
                base_marker = "model_jiaguyi_3"
                if base_marker in path_parts:
                    idx = path_parts.index(base_marker)
                    top_dir = path_parts[idx+1]  # 紧跟 base_marker 的目录
                else:
                    top_dir = path_parts[-4]  # 默认倒数第4层

                stats[top_dir][category] += 1

    # 输出统计结果
    for top_dir, counts in stats.items():
        total = sum(counts.values())
        print(f"顶层目录: {top_dir} (总文件数: {total})")
        for category, count in counts.items():
            print(f"  {category}: {count} ({count/total*100:.2f}%)")
    
analysis_for_jiaguyi()

#print_geo_acc()

