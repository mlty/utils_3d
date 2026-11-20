import csv
import argparse
from easydict import EasyDict as edict
import os

def find_exist_glbs():

    file_path = '/mnt/vast/hongyuan/3d_data_git/metadata.csv'
    dataList = {}
    index = 0
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        rows = list(reader)
        for row in tqdm(rows, desc="Processing rows"):
            # captions = row['captions']
            # score = float(row['aesthetic_score'])  
            # sha256 = row['sha256']
            local_path = row['local_path'].split('glbs/')[-1].strip() # raw/hf-objaverse-v1/glbs/000-086/6eba14662bd048f9bc1ca10e63b5622f.glb
            dataList[local_path] = 1
            
            index += 1
    
    return dataList

    return exist_glbs


from tqdm import tqdm
import json
import shutil
import random

def get_tex_data():

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
                    okk += 1
                    all_data.append(glb_paths[-1])

            index += 1
        
        print('okk : ', okk)
    
    sorted_dict = sorted(tag_record.items(), key=lambda x: x[1], reverse=True)
    num = 0
    for key in sorted_dict:
        print(key[0], ' >> ', key[1])
        num += 1

        if num > 30:
            break
    
    return all_data #tex_record, tag_record


def get_bad_ccases(data_map):

    data = {}
    for i in range(30):
        f = open('/mnt/home/hongyuanzhu/hy_3d/prompt_section/hvscore'+str(i)+'_list.txt', 'r')
        
        for line in f:
            tmp = line.replace('\n','')
            if '|' in tmp:
                tmp = tmp.split('|')[0].split('/')[-1].strip()
                data[data_map[tmp]] = 1
    
    return data

def find_bad_plane():
    data = {}
    for i in range(10):
        f = open('/mnt/home/hongyuanzhu/hy_3d/extend_utils/data_utils_v3/tex1k_score_glb'+str(i)+'.txt', 'r')

        index = 0
        count = 0
        for line in f:
            tmp = line.replace('\n', '').strip().split(' ')

            file_path, num, all_num, score, color_num, color_tag, length_real, width_real, height_real = tmp[0], tmp[1], tmp[2], tmp[3], int(tmp[4]), int(tmp[5]), float(tmp[6]), float(tmp[7]), float(tmp[8])

            min_dimension = min(length_real, width_real, height_real)
            mid_dimension = sorted([length_real, width_real, height_real])[1]

            if min_dimension > 0 and float(mid_dimension) / min_dimension >= 10: # color_num > 0 and color_tag == 0: #
                index += 1
                data[file_path.split('/')[-1].split('_1024')[0].strip()] = 1
    
    return data

def read_csv_file():
    data_mapping = {}
    root_data = '/mnt/vast/hongyuan/trellis_data/Tex/metadata_back.csv'

    f = open(root_data, 'r')
    for line in f:
        tmp = line.replace('\n', '').split(',')
        sha256 = tmp[0].strip()
        idx = tmp[1].split('/')[-1].split('_1024')[0].strip()
        data_mapping[sha256] = idx
    
    return data_mapping

def copy_data(rank, world_size):
    data_mapping = read_csv_file()
    data = get_bad_ccases(data_mapping)
    data1 = find_bad_plane()
    result = get_tex_data()
    print(' >>> >>> >>> ', len(result))

    random.shuffle(result)

    for i in tqdm(range(min(10000, len(result))), desc="Processing"):
        if i % world_size != rank:
            continue
        item = result[i]

        tmp = os.path.basename(item).split('_1024')[0].strip()

        if tmp not in data and tmp not in data1:
            src = os.path.join('/mnt/vast/hongyuan/trellis_data/TexVerse', item)
            dst = os.path.join('/mnt/vast/hongyuan/3d_data_new_tex_pbr/raw', os.path.basename(item))

            if os.path.exists(dst):
                continue
            
            try:
                shutil.copy(src, dst)
            except Exception as e:
                print(f"Error copying file {item}: {e}")
            
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rank', type=int, default=0)
    parser.add_argument('--world_size', type=int, default=1)
    opt = parser.parse_args()
    opt = edict(vars(opt))    
    copy_data(opt.rank, opt.world_size)