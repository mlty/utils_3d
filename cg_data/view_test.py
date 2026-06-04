import os
import glob
from PIL import Image
import random
import numpy as np
from tqdm import tqdm
import subprocess
import re
import argparse
from easydict import EasyDict as edict
import time

def find_min_data(rank):
    root = "/mnt/vast/hongyuan/3d_data_git_step1x/renders_cond/"   # 根目录
    save_path = "merged.png"
    threshold_ratio = 0.02  # 占比低于 5% 就打印出来

    views_per_obj = 4
    objs_per_image = 500   # 每张大图包含多少个文件夹

    sample_size = 2000

    reservoir = []
    index = 0  # 遍历计数
    
    fw = open('step1x_remove_small_'+str(rank)+'.txt', 'w')
    all_dirs = []
    for entry in os.scandir(root):
        if entry.is_dir():
            if index % 10 == rank:
                all_dirs.append(entry.name)
            index += 1
    
    print(f"总文件夹数量: {len(all_dirs)}")
    folders = all_dirs

    images = []
    all_num= 0
    for folder in tqdm(folders, desc="Processing folders"):
        img_paths = sorted(glob.glob(os.path.join(root, folder, "*")))
        img_paths = img_paths[:views_per_obj]

        cur_num= 0
        tmp_images = []
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
                    # print(f"Warning: {p} 非透明占比过小: {ratio:.3f}")
                    # tmp_images.append(img.convert("RGBA"))
                    cur_num += 1
                # ---------------------------

                # 用于拼图：统一 RGBA
        
        # if len(tmp_images) >=3:
        #     images.extend(tmp_images)
        if cur_num >= 3:
            all_num += 1
            fw.write(folder.strip() + '\n')
        # print(p, ' 》》》 ', sum(avg_score) / len(avg_score))  # 平均占比

    print(all_num, ' >> ', objs_per_image, ' >> ', float(all_num) / objs_per_image)
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rank', type=int, default=0)
    opt = parser.parse_args()
    opt = edict(vars(opt))
    find_min_data(opt.rank)


