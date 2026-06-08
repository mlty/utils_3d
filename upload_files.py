# from modelscope.hub.api import HubApi
# from tqdm import tqdm
# import os

# # 1️⃣ 登录
# YOUR_ACCESS_TOKEN = 'ms-e210be08-6fdd-4a42-b1fa-57ea292bcc70'
# api = HubApi()
# api.login(YOUR_ACCESS_TOKEN)

# # 2️⃣ 配置数据集信息
# owner_name = 'zhymlty'  # 你自己的用户名
# dataset_name = '3d_pbr_10k'  # 自己创建的数据集
# local_root = '/mnt/vast/hongyuan/3d_tex_pbr_10k/raw'
# commit_message = 'upload custom 3D textures'

# # 3️⃣ 遍历本地文件，按批次上传
# batch_size = 20
# batch_files = []

# # 收集所有文件
# all_files = []
# for root, _, files in os.walk(local_root):
#     for f in files:
#         all_files.append(os.path.join(root, f))

# all_files = all_files[7000:8000]
# print('len of all files:', len(all_files))

# # 上传并显示进度条
# for file_path in tqdm(all_files, desc="Uploading files", unit="file"):
#     batch_files.append(file_path)
#     if len(batch_files) >= batch_size:
#         api.upload_folder(
#             repo_id=f"{owner_name}/{dataset_name}",
#             folder_path=batch_files,
#             commit_message=commit_message,
#             repo_type='dataset'
#         )
#         batch_files = []

# # 上传剩余文件
# if batch_files:
#     api.upload_folder(
#         repo_id=f"{owner_name}/{dataset_name}",
#         folder_path=batch_files,
#         commit_message=commit_message,
#         repo_type='dataset'
#     )

# print("✅ 上传完成！")

from modelscope.hub.api import HubApi
import os

# 1️⃣ 登录
api = HubApi()
YOUR_ACCESS_TOKEN = 'ms-e210be08-6fdd-4a42-b1fa-57ea292bcc70'
api.login(YOUR_ACCESS_TOKEN)

# 2️⃣ 配置模型仓库信息
owner_name = 'zhymlty'
model_name = 'graver_1.1'   # 模型仓库名（注意不是 dataset）
local_folder = '/Users/mlty/Data/graver1_1'
commit_message = 'upload model files'

# 3️⃣ 直接上传整个文件夹
api.upload_folder(
    repo_id=f"{owner_name}/{model_name}",
    folder_path=local_folder,
    commit_message=commit_message,
    repo_type='model'   # ⚠️ 改成 model
)

print("✅ 模型上传完成！")