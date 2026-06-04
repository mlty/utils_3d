

def analysis():

    all_data_list = []
    for i in range(20):
        f = open('/mnt/home/hongyuanzhu/utils_3d/eval_3d_data_from_vllm/tex_score'+str(i)+'_list.txt', 'r')
        tmp = []

        for line in f:
            data = line.replace('\n', '').strip()

            if '/mnt/vast' not in data:
                tmp.append(data)
            else:
                if len(tmp) == 0:
                    tmp.append(data)
                else:
                    all_data_list.append(tmp)
                    tmp = []
                    tmp.append(data)
    
    all_num = 0
    tag = 0
    bad_dict = {}

    for data in all_data_list:
        line = ','.join(data)

        if '"形状碎片化": "Yes"' in line or '"破损": "Yes"' in line or '石' in line:
            if '石' in line:
                tag += 1
            bad_dict[line.split('|')[0].split('/')[-1].strip()] = 1

            if tag < 10:
                print(line.split('|')[0].split('/')[-1].strip())

        all_num += 1

    # print('无法识别:', no_what)
    # print('大小异常:', size_err)
    # print('形状碎片化:', shape_err)
    # print('破损:', broken_err)
    # print('大地板/平面:', floor_err)
    print('石:', tag)
    # print('总数:', all_num)
    # rewrite csv data

    return bad_dict


def merge_data_csv():

    import csv
    from tqdm import tqdm

    bad_dict = analysis()
    print('size of bad dict: ', len(bad_dict))
    for i in range(4):
        f = open('/mnt/home/hongyuanzhu/utils_3d/cg_data/tex_remove_small_'+str(i)+'.txt', 'r')
        n = 0
        for line in f:
            key = line.replace('\n', '').strip()
            if key not in bad_dict:
                bad_dict[key] = 1
                n += 1
    
    print('>>>>>>>>>>>>>>>> : ', n)
    print('after size of bad dict: ', len(bad_dict))

    hit_num = 0
    file_path = '/mnt/vast/hongyuan/3d_data_new_tex/metadata.csv'
    dataList = []
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        rows = list(reader)
        for row in tqdm(rows, desc="Processing rows"):
            sha256 = row['sha256']
            local_path = row['local_path']
            rendered = row['rendered']
            cond_rendered = row['cond_rendered']
            occ8_num_blocks = row['64_15_occ8_num_blocks']
            occ8_block_status = row['64_15_occ8_block_status']
            
            if sha256 in bad_dict:
                hit_num += 1
            else:
                dataList.append([sha256, local_path, rendered, cond_rendered, occ8_num_blocks, occ8_block_status])
    
    print('hit num: ', hit_num)
    print('filter num: ', len(dataList))

    # 构建新的数据    
    import pandas as pd
    # 设置列名
    columns = ['sha256', 'local_path', 'rendered', 'cond_rendered', '64_15_occ8_num_blocks', '64_15_occ8_block_status']

    # 创建 DataFrame 并写入
    df = pd.DataFrame(dataList, columns=columns)
    df.to_csv('/mnt/vast/hongyuan/3d_data_new_tex/metadata_filter.csv', index=False)

# merge_data_csv()

import json
import random
from tqdm import tqdm
import shutil
import os

def find_pbr_data():

    all_data = []
    #exist_glbs = find_exist_glbs()
    file_name = '/mnt/vast/hongyuan/TexVerse/metadata.json'

    tex_record = {}
    tag_record = {}
    user_record = {}

    bad_list = ['scan', 'createdwithai', 'meshy', 'photogrammetry', 'csm', 'polycam', 'tripo3d', 'lumalabs', 'ai', 'tripo',
                    'masterpiecestudio', 'womboart', 'withpoly', 'agisoft', 'metashape', 'realitycapture', '3df-zephyr', 
                    'tiltbrush', 'qlone', 'trnio', '3dlivescanner', 'itseez3d', 'openbrush', 'stair', 'pamir']
    
    # 逐行读取文件
    with open(file_name, 'r') as f:
        metadata = json.load(f)
        metadata_dict = {}
        for idx, item in enumerate(metadata):
            # if idx % 100 == rank:
            metadata_dict[item] = metadata[item]
        
        print('size of meta : ', len(metadata_dict))

        # 假设 metadata 是一个包含多个条目的列表
        index = 0
        okk = 0
        num = 0
        pbr_num = 0
        rint = random.randint(0, 49)

        for item in tqdm(metadata_dict, desc="Processing"):
            tag_flag = False
            vertex_flag = False
            exist_flag = False

            try:

                glb_paths = metadata_dict[item].get('glb_paths')  # 假设每项都有 'glb_paths' 键 # .get('glb_paths')
                vertexCount = metadata_dict[item].get('vertexCount')
                faceCount = metadata_dict[item].get('faceCount')
                user = metadata_dict[item].get('user')
                thumbnail_url = metadata_dict[item].get('thumbnail_url')
                pbrType = metadata_dict[item].get('pbrType')

                if user not in user_record:
                    user_record[user] = 1
                else:
                    user_record[user] += 1
                
                if vertexCount is not None and (faceCount > 500000 or faceCount < 1000):
                    vertex_flag = True
                
                tags = metadata_dict[item].get('tags')

                for tag in tags:
                    for j in bad_list:
                        if j in tag:
                            tag_flag = True
                            break
                    
                    if tag in ['scaniverse', 'realityscan', '3dscannerapp', 'photoscan', 'realitycapture', 'scan', 'stone', 'qlone', 'trnio', 'sculpture', 
                               '3dlivescanner', '3dscan', '3d-scan', '3dscanning', 'scanning', 'scanned', 'escultura', 'estatua', 'statue', 'sculpture', 'rock', 
                               'stone', 'fossil', 'elevationapi', 'archaeology', 'gdh', 'petroglyphs', 'rock-art', 'lidar', 'geology', 
                               'ai', 'cc0']:
                        tag_flag = True
                    
                    if not tag_flag:
                        if tag not in tag_record:
                            tag_record[tag] = 1
                        else:
                            tag_record[tag] += 1
                    
                # print(glb_paths)
                for glb_path in glb_paths:
                    tmp_data = '/'.join(glb_path.split('/')[2:]).replace('_1024', '').replace('_2048', '').replace('_4096', '').replace('_8192', '').strip()
                    #print(tmp_data)
                    tex_record[tmp_data] = 1
                    
                    if 'substance-painter' in tags and num < 20 and '1024' in glb_path and index % 50 == rint and not tag_flag:
                        #print('>>>>  ', glb_paths, ' >> ', tags)
                        #shutil.copy('/mnt/vast/hongyuan/trellis_data/TexVerse/'+glb_path, '/mnt/home/hongyuanzhu/'+glb_path.split('/')[-1])
                        num += 1
                    
                    # if tmp_data in exist_glbs:
                    #     exist_flag = True
                    
                    # if faceCount > 500000 and faceCount < 600000 and num < 20 and '1024' in glb_path and index % 50 == rint and not tag_flag:
                    #     print(thumbnail_url)
                    #     shutil.copy('/mnt/vast/hongyuan/trellis_data/TexVerse/'+glb_path, '/mnt/home/hongyuanzhu/'+glb_path.split('/')[-1])
                    #     index += 1
            
            except Exception as e:
                print(f"Error processing item {index}: {e}")
            
            if not tag_flag and not vertex_flag: #and not exist_flag:
                if pbrType is not None and pbrType != 'null':
                    pbr_num += 1
                    if pbr_num < 10:
                        shutil.copy('/mnt/vast/hongyuan/trellis_data/TexVerse/'+glb_paths[-1], '/mnt/home/hongyuanzhu/'+glb_paths[-1].split('/')[-1])
                        print('/mnt/vast/hongyuan/trellis_data/TexVerse/' + glb_paths[-1])
                
                okk += 1
                all_data.append(glb_paths[-1])

            index += 1
        
        print('okk : ', okk)
        print('pbr num : ', pbr_num)
    
    sorted_dict = sorted(tag_record.items(), key=lambda x: x[1], reverse=True)
    num = 0
    for key in sorted_dict:
        print(key[0], ' >> ', key[1])
        num += 1

        if num > 30:
            break

    return all_data #tex_record, tag_record

#find_pbr_data()

# def find_min_data():

#     import os
#     import glob
#     from PIL import Image
#     import random
#     import numpy as np

#     fw = open('tex_large_record.txt', 'w')

#     root = "/mnt/vast/hongyuan/3d_data_new_tex_large/renders_cond/"   # 根目录
#     threshold_ratio = 0.01  # 占比低于 5% 就打印出来

#     views_per_obj = 4
#     all_dirs = []
#     for entry in os.scandir(root):
#         if entry.is_dir():
#             all_dirs.append(entry.name)

#     print(f"总文件夹数量: {len(all_dirs)}")

#     # 取前16个
#     folders = all_dirs
#     images = []
#     all_num= 0
#     for folder in tqdm(folders, desc="Processing folders"):
#         img_paths = sorted(glob.glob(os.path.join(root, folder, "*")))
#         img_paths = img_paths[:views_per_obj]

#         cur_num= 0
#         for p in img_paths:
#             if '.png' in p:
#                 img = Image.open(p)  # 不转 RGB
#                 arr = np.array(img)
#                 if arr.shape[2] == 4:
#                     # 有 alpha 通道
#                     alpha = arr[:, :, 3]
#                     non_transparent = np.sum(alpha > 0)
#                     total = alpha.size
#                 else:
#                     # 没有 alpha，整张图非透明（或者用白色判断占比）
#                     non_transparent = arr.shape[0] * arr.shape[1]
#                     total = non_transparent
                
#                 ratio = non_transparent / total
#                 if ratio < threshold_ratio:
#                     cur_num += 1
#                 # ---------------------------

#                 # 用于拼图：统一 RGBA
        
#         if cur_num >=3:
#             images.append(folder)
#             fw.write(folder+'\n')
        


def find_min_data():

    import os
    import glob
    from PIL import Image
    import random
    import numpy as np
    from tqdm import tqdm

    fw = open('tex_min_record.txt', 'w')
    
    root = "/mnt/vast/hongyuan/3d_data_new_tex/renders_cond/"   # 根目录
    threshold_ratio = 0.02  # 占比低于 5% 就打印出来

    views_per_obj = 4
    all_dirs = []
    for entry in os.scandir(root):
        if entry.is_dir():
            all_dirs.append(entry.name)

    print(f"总文件夹数量: {len(all_dirs)}")

    # 取前16个
    folders = all_dirs[:500]
    images = []
    all_num= 0
    for folder in tqdm(folders, desc="Processing folders"):
        img_paths = sorted(glob.glob(os.path.join(root, folder, "*")))
        img_paths = img_paths[:views_per_obj]

        cur_num= 0
        for p in img_paths:
            if '.png' in p:
                img = Image.open(p)  # 不转 RGB
                arr = np.array(img)
                if arr.shape[2] == 4:
                    # 有 alpha 通道
                    alpha = arr[:, :, 3]
                    non_transparent = np.sum(alpha > 0)
                    total = alpha.size
                else:
                    # 没有 alpha，整张图非透明（或者用白色判断占比）
                    non_transparent = arr.shape[0] * arr.shape[1]
                    total = non_transparent
                
                ratio = non_transparent / total
                if ratio < threshold_ratio:
                    cur_num += 1
                # ---------------------------

                # 用于拼图：统一 RGBA
        
        if cur_num >=3:
            images.append(folder)
            fw.write(folder+'\n')

def print_csv():

    import csv
    from tqdm import tqdm

    hit_num = 0
    all_num= 0
    file_path = '/mnt/vast/hongyuan/3d_data_git_step1x/metadata.csv'
    dataList = []

    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        rows = list(reader)
        for row in tqdm(rows, desc="Processing rows"):
            sha256 = row['sha256']
            local_path = row['local_path']
            rendered = row['rendered']
            cond_rendered = row['cond_rendered']
            occ8_num_blocks = row['64_15_occ8_num_blocks']
            occ8_block_status = row['64_15_occ8_block_status']
            
            if cond_rendered == 'True':
                hit_num += 1
            all_num += 1
    
    print('hit num: ', hit_num)
    print('all num: ', all_num)

print_csv()
