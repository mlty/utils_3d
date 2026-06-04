import os
import glob
from PIL import Image
import random
import numpy as np
from tqdm import tqdm

root = "/mnt/vast/hongyuan/3d_data_new_tex/renders_cond/"   # 根目录
save_path = "merged.png"
threshold_ratio = 0.02  # 占比低于 5% 就打印出来

views_per_obj = 4
objs_per_image = 500   # 每张大图包含多少个文件夹

sample_size = 2000

reservoir = []
n = 0  # 遍历计数

# fw = open('../cg_data/remove_small.txt', 'w')
for entry in os.scandir(root):  # scandir 是比 os.listdir 更高效的迭代方法
    if entry.is_dir():
        n += 1
        if len(reservoir) < sample_size:
            reservoir.append(entry.name)  # 前 sample_size 个直接放入
        else:
            # 以 sample_size/n 的概率替换 reservoir 中的随机元素
            s = random.randint(0, n-1)
            if s < sample_size:
                reservoir[s] = entry.name

folders = reservoir
print(len(folders))  # 3000

# all_dirs = []
# for entry in os.scandir(root):
#     if entry.is_dir():
#         all_dirs.append(entry.name)

# print(f"总文件夹数量: {len(all_dirs)}")

# 取前16个
# folders = all_dirs

# 取前16个
folders = folders[:objs_per_image]

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
                print(f"Warning: {p} 非透明占比过小: {ratio:.3f}")
                tmp_images.append(img.convert("RGBA"))
                cur_num += 1
            # ---------------------------

            # 用于拼图：统一 RGBA
    
    if len(tmp_images) >=3:
        images.extend(tmp_images)
    if cur_num >= 3:
        all_num += 1
        # fw.write(folder.strip() + '\n')
    # print(p, ' 》》》 ', sum(avg_score) / len(avg_score))  # 平均占比

print(all_num, ' >> ', objs_per_image, ' >> ', float(all_num) / objs_per_image)

# 假设所有图片尺寸相同
w, h = images[0].size

cols = views_per_obj
rows = all_num #len(folders)

canvas = Image.new("RGB", (cols*w, rows*h))

for i, img in enumerate(images):
    r = i // cols
    c = i % cols
    canvas.paste(img, (c*w, r*h))

canvas.save(save_path)
print("saved to", save_path)


