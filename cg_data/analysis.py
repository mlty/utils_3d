import os
from collections import defaultdict

def count_3d_files(folder_path):
    # 要统计的扩展名
    exts = ['.glb', '.gltf', '.fbx', '.blend', '.obj', '.stl']
    counts = defaultdict(int)

    for root, dirs, files in os.walk(folder_path):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in exts:
                counts[ext] += 1

    return counts


def read_from_csv():
    
    import csv
    from tqdm import tqdm

    all_num, hit_num = 0, 0

    file_path = '/mnt/vast/hongyuan/CG_data/metadata.csv'
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

            file_path = '/mnt/vast/hongyuan/CG_data/' + local_path.strip()

            if os.path.exists(file_path) and '.blend' in file_path:
                all_num += 1

                size = float(os.path.getsize(file_path)  / (1024 * 1024))

                if size > 200:
                    hit_num += 1
                    # print('-------------------大文件--------------------> ')
                    # print(file_path)
                    # print(size)
                    # print('\n\n')
    
    print(hit_num, ' / ', all_num)


def analysis():

    all_data_list = []
    for i in range(25):
        f = open('/mnt/home/hongyuanzhu/utils_3d/eval_3d_data_from_vllm/cg_score'+str(i)+'_list.txt', 'r')
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
    
    # /mnt/vast/hongyuan/3d_data_new_tex_large/renders_cond/00ae86c7df6b40875858400056dc8cadc3370884c4e13b9660573226237a14e3|```json
# {
#   "是什么": "无法识别",
#   "形状碎片化": "No",
#   "破损": "No",
#   "只有白色": "No",
#   "岩石/石头/碎片": "No"
# }

# {
#   "是什么": "立方体",
#   "形状碎片化": "No",
#   "破损": "No",
#   "大地板/平面": "No",
#   "是个立方体": "Yes"
# }

    no_what = 0
    color_err = 0
    shape_err = 0
    broken_err = 0
    floor_err = 0
    all_num = 0

    tag = 0
    bad_dict = {}

    for data in all_data_list:
        line = ','.join(data)

        if '"是什么": "立方体"' in line or '"是个立方体": "Yes"' in line:
            no_what += 1
            
        if '"形状碎片化": "Yes"' in line:
            shape_err += 1
            print(line)
        if '"破损": "Yes"' in line:
            broken_err += 1
        all_num += 1
    
    print('立方体:', no_what)
    print('形状碎片化:', shape_err)
    print('破损:', broken_err)
    print('总数:', all_num)
    # rewrite csv data


    return bad_dict


def merge_data_csv():

    import csv
    from tqdm import tqdm

    bad_dict = analysis()
    remove_dict, file_path_dict = get_bad_dict()
    for item in remove_dict:
        bad_dict[item] = 1
    
    hit_num = 0
    file_path = '/mnt/vast/hongyuan/CG_data/metadata.csv'
    dataList = []
    all_num = 0

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
            
            if sha256 in bad_dict or '/mnt/vast/hongyuan/CG_data/'+local_path in file_path_dict:
                hit_num += 1
                if '/mnt/vast/hongyuan/CG_data/'+local_path in file_path_dict:
                    print('!!!!')
            else:
                dataList.append([sha256, local_path, rendered, cond_rendered, occ8_num_blocks, occ8_block_status])
            
            all_num += 1

            if all_num < 100:
                print(local_path)
    
    print('hit num: ', hit_num)
    print('filter num: ', len(dataList))
    print('all num : ', all_num)

    # 构建新的数据    
    import pandas as pd
    # 设置列名
    columns = ['sha256', 'local_path', 'rendered', 'cond_rendered', '64_15_occ8_num_blocks', '64_15_occ8_block_status']

    # 创建 DataFrame 并写入
    df = pd.DataFrame(dataList, columns=columns)
    df.to_csv('/mnt/vast/hongyuan/CG_data/metadata_filter.csv', index=False)


def analysis_for_jiaguyi():

    import csv
    from tqdm import tqdm

    bad_dict = analysis()
    hit_num = 0
    file_path = '/mnt/vast/hongyuan/CG_data/metadata_all.csv'
    dataList = []

    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        rows = list(reader)
        for row in tqdm(rows, desc="Processing rows"):
            sha256 = str(row['sha256']).strip()
            local_path = row['local_path']
            rendered = row['rendered']
            cond_rendered = row['cond_rendered']
            occ8_num_blocks = row['64_15_occ8_num_blocks']
            occ8_block_status = row['64_15_occ8_block_status']
            # print(sha256, ' >> ', local_path)

            if sha256 in bad_dict and 'jiaguyi_4' in local_path:
                hit_num += 1
                print(local_path)

    
    print('hit num: ', hit_num)


from collections import defaultdict

def eval_data():
    print('ok')

    stats = defaultdict(lambda: {
        "low": 0,
        "mid": 0,
        "high": 0
    })
    all_total = 0
    low_num, mid_num, high_num = 0, 0, 0

    for i in range(4):
        with open('/mnt/home/hongyuanzhu/utils_3d/eval_3d_data_from_blender/jiaguyi_4_data_score_glb'+str(i)+'.txt', 'r') as f:
            for line in f:
                tmp = line.strip().split(' ')
                file_path = tmp[0]

                faces = int(tmp[7])
                # 提取一级类目
                category = file_path.split('/')[7]

                # 分类统计
                if faces < 50000:
                    stats[category]["low"] += 1
                elif 50000 <= faces < 150000:
                    stats[category]["mid"] += 1
                elif 150000 <= faces:
                    stats[category]["high"] += 1
    
    # 打印结果
    for cat, v in stats.items():
        if '动物' in cat:
            total = v["low"] + v["mid"] + v["high"]
            print(cat)
            print("Low:", v["low"])
            print("Mid:", v["mid"])
            print("High:", v["high"])
            print("Total:", total)
            print("-" * 40)

            low_num += v["low"]
            mid_num += v["mid"]
            high_num += v["high"]
            all_total += total
    
    print('all_total : ', all_total)
    print(' low rate : ', low_num, float(low_num) / all_total)
    print(' mid rate : ', mid_num, float(mid_num) / all_total)
    print(' high rate : ', high_num, float(high_num) / all_total)


def find_min_data():

    import os
    import glob
    from PIL import Image
    import random
    import numpy as np
    from tqdm import tqdm

    fw = open('cg_record.txt', 'w')

    root = "/mnt/vast/hongyuan/3d_data_new_tex/renders_cond/"   # 根目录
    threshold_ratio = 0.01  # 占比低于 5% 就打印出来
    
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
        


def read_ply_file_size():

    import os
    from tqdm import tqdm
    root_dir = "/mnt/vast/hongyuan/CG_data/renders_cond"

    fw = open('cg_block_record.txt', 'w')

    results = []
    index = 0
    folders = os.listdir(root_dir)
    for folder in tqdm(folders, desc="Processing folders"):
        folder_path = os.path.join(root_dir, folder)

        if not os.path.isdir(folder_path):
            continue

        # 找这个文件夹里的 .ply
        ply_files = [f for f in os.listdir(folder_path) if f.endswith(".ply")]

        if len(ply_files) == 0:
            continue

        ply_path = os.path.join(folder_path, ply_files[0])
        # 获取文件大小（字节 → MB）
        size_bytes = os.path.getsize(ply_path)
        size_mb = size_bytes / (1024 * 1024)

        if size_mb < 0.01:
            # results.append((root_dir+'/'+folder, size_mb))
            index += 1
            fw.write(folder.strip() + '\n')
    # 输出
    print('index : ', index)


def get_ai_assets():
    
    fw = open('remove_ai_jiayuyi_1.txt', 'w')
    hit_num = 0
    dict = {}
    for i in range(4):
        f = open('/mnt/home/hongyuanzhu/utils_3d/eval_3d_data_from_blender/jiaguyi_1_score'+str(i)+'.txt', 'r')
        for line in f:
            # /mnt/vast/hongyuan/CG_data/raw/model_jiaguyi_4/手办_不包含PBR和骨骼_写实风_8200/手办_玩偶/手办_玩偶1512/Image_0.png
            img_num = line.replace('\n', '').strip().split(' ')[1]
            try:
                img_num = int(img_num)
                if img_num == 1:
                    tmp = '/'.join(line.strip().split(' ')[0].split('/')[:-1]) + '/Image_0.png'
                    print(' >>> ', tmp)
                    if os.path.exists(tmp):
                        if '动物' not in tmp and tmp not in dict:
                            dict[tmp] = 1
                            hit_num += 1
                            print(line.replace('\n', '').split(' ')[0].strip())
                            fw.write(line.replace('\n', '').split(' ')[0].strip() + '\n')
            except Exception as e:
                print('Error processing line:', line)
                print('Exception:', e)
            
    print(hit_num)

def get_bad_dict():
    bad_dict = {}
    file_path = {}

    for i in range(20):
        f = open(f'/mnt/home/hongyuanzhu/utils_3d/cg_data/remove_small_{i}.txt', 'r')
        for line in f:
            data = line.replace('\n', '').strip()
            bad_dict[data] = 1
    
    f = open('/mnt/home/hongyuanzhu/utils_3d/cg_data/cg_block_record.txt', 'r')
    for line in f:
            data = line.replace('\n', '').strip()
            bad_dict[data] = 1
    
    for i in range(4):
        f = open(f'remove_ai_jiayuyi_{i+1}.txt', 'r')
        for line in f:
            data = line.replace('\n', '').strip()
            file_path[data] = 1


    print('len of bad dict : ', len(bad_dict))
    print('len of file path : ', len(file_path))

    return bad_dict, file_path


def filter_jiaguyi():

    import csv
    from tqdm import tqdm

    hit_num = 0
    img_num = 0
    file_path = '/mnt/vast/hongyuan/CG_data/metadata.csv'
    dataList = []

    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        rows = list(reader)
        for row in tqdm(rows, desc="Processing rows"):
            sha256 = str(row['sha256']).strip()
            local_path = row['local_path']
            rendered = row['rendered']
            cond_rendered = row['cond_rendered']
            occ8_num_blocks = row['64_15_occ8_num_blocks']
            occ8_block_status = row['64_15_occ8_block_status']

            if 'jiaguyi' in local_path:
                file_path = '/mnt/vast/hongyuan/CG_data/' + '/'.join(local_path.strip().split('/')[:-1]) + '/Image_0.png'
                if os.path.exists(file_path):
                    print(local_path)
                    img_num += 1
                hit_num += 1
    
    print('hit num: ', hit_num)
    print('img num: ', img_num)
    
if __name__ == "__main__":
    #eval_data()
    #find_min_data()
    filter_jiaguyi()
    #analysis_for_jiaguyi()
    #merge_data_csv()

    # dir_list = ["model_0630", "model_0707", "model_0721", "model_0729", "model_0805", "model_0812", "model_0819", 
    # "model_0826", "model_0902", "model_0908", "model_0916", "model_1015", "model_jiaguyi_1", "model_jiaguyi_2", 
    # "model_jiaguyi_3", "model_jiaguyi_4"]
    
    # for dir_name in dir_list:
    #     folder = os.path.join(r"/mnt/vast/hongyuan/CG_data/", dir_name)   # 修改为你的目录
    #     result = count_3d_files(folder)

    #     total = 0
    #     for ext in ['.glb', '.gltf', '.fbx', '.blend', '.obj', '.stl']:
    #         num = result.get(ext, 0)
    #         total += num
    #         print(f"{ext}: {num}")
        
    #     print(f"\nTotal for {dir_name}: {total}\n")

# 统计 边数量/ 面数量 / 文件大小 / 材质 / 长/宽/高 / mesh 数量 / 等

