import subprocess
import os
import re
from tqdm import tqdm
import argparse
from easydict import EasyDict as edict
import time

def score_glb(rank):
    blender_path = r"/mnt/home/hongyuanzhu/blender-3.0.1-linux-x64/blender"
    script_path = r"/mnt/home/hongyuanzhu/utils_3d/eval_3d_data_from_blender/script_score.py"
    folder_path = r'/mnt/vast/hongyuan/jiaguyi8/raw/' # /mnt/vast/hongyuan/CG_data/raw/model_jiaguyi_4

    input_list = []
    num = 0
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".glb") or file.endswith(".gltf") or file.endswith(".fbx") or file.endswith(".blend") or file.endswith(".obj"):
                if num % 20 == rank:
                    input_path = os.path.join(root, file)
                    input_list.append(input_path)
                num += 1
    
    print('size of input : ', len(input_list))
    fw = open('jiaguyi_8_score'+str(rank)+'.txt', 'w')
    
    # 假设 input_list 已经定义
    chunk_size = 100
    num_chunks = len(input_list) // chunk_size + (1 if len(input_list) % chunk_size else 0)

    for i in tqdm(range(num_chunks), desc="Processing", unit="batch"):
        input_path_list = input_list[i*chunk_size:(i+1)*chunk_size]
        if not input_path_list:
            continue

        # 构造命令
        command = [
            blender_path,
            "--background",     # 可选：不打开界面
            "--python", script_path,
            "--", '|'.join(input_path_list),
            'output',
        ]

        # subprocess.run(command)
        # 捕获输出
        result = subprocess.run(
            command,
            capture_output=True,  # 等价于 stdout=subprocess.PIPE, stderr=subprocess.PIPE
            text=True             # 以字符串形式返回，而不是字节
        )

        # 打印 Blender 的标准输出和错误输出
        res = result.stdout
        out = re.findall('data \[(.+?)\]', res)

        if len(out) > 0:
            for j in range(len(out)):
                fw.write(out[j].strip() + '\n')
        
def score_quad(rank):
    blender_path = r"/mnt/home/hongyuanzhu/blender-3.0.1-linux-x64/blender"
    script_path = r"/mnt/home/hongyuanzhu/hy_3d/extend_utils/data_utils_v3/quad_score.py"
    folder_path = r'/mnt/vast/hongyuan/trellis_data/TexVerse/glbs/glbs_1k'
    
    input_list = []

    # num = 0
    # for root, _, files in os.walk(folder_path):
    #     for file in files:
    #         if file.endswith(".glb"):
    #             if num % 10 == rank:
    #                 input_path = os.path.join(root, file)
    #                 input_list.append(input_path)
    #             num += 1

    f = open('/mnt/home/hongyuanzhu/hy_3d/prompt_section/tex_data_remove.txt', 'r')
    for num, line in enumerate(f):
        tmp = line.replace('\n', '').strip()
        if os.path.exists(tmp):
            if num % 20 == rank:
                input_list.append(line)
    

    print('size of input : ', len(input_list))
    fw = open('/mnt/home/hongyuanzhu/hy_3d/extend_utils/data_utils_v3/tmp_tex1k_quad_glb'+str(rank)+'.txt', 'a+')
    
    # 假设 input_list 已经定义
    chunk_size = 50
    num_chunks = len(input_list) // chunk_size + (1 if len(input_list) % chunk_size else 0)

    for i in tqdm(range(num_chunks), desc="Processing", unit="batch"):
        input_path_list = input_list[i*chunk_size:(i+1)*chunk_size]

        if not input_path_list:
            continue

        # 构造命令
        command = [
            blender_path,
            "--background",     # 可选：不打开界面
            "--python", script_path,
            "--", '|'.join(input_path_list),
            'output',
        ]

        # subprocess.run(command)
        # 捕获输出
        result = subprocess.run(
            command,
            capture_output=True,  # 等价于 stdout=subprocess.PIPE, stderr=subprocess.PIPE
            text=True             # 以字符串形式返回，而不是字节
        )

        # 打印 Blender 的标准输出和错误输出
        res = result.stdout
        out = re.findall('data \[(.+?)\]', res)

        if len(out) > 0:
            for j in range(len(out)):
                fw.write(out[j].strip() + '\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rank', type=int, default=0)
    opt = parser.parse_args()
    opt = edict(vars(opt))
    score_glb(opt.rank)
