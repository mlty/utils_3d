
def analysis():

    all_data_list = []
    for i in range(25):
        f = open('/mnt/home/hongyuanzhu/utils_3d/eval_3d_data_from_vllm/step1x_score'+str(i)+'_list.txt', 'r')
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
    
    bad_dict = {}

    for data in all_data_list:
        line = ','.join(data)

        if '"形状碎片化": "Yes"' in line or '"破损": "Yes"' in line or '"只有白色": "Yes"' in line or '"岩石/石头/碎片": "Yes"' in line:
            bad_dict[line.split('|')[0].split('/')[-1].strip()] = 1
    
    return bad_dict

def merge_data_csv():

    import csv
    from tqdm import tqdm

    bad_dict = analysis()
    print('size of bad dict: ', len(bad_dict))
    n = 0
    for i in range(10):
        f = open('/mnt/home/hongyuanzhu/utils_3d/cg_data/step1x_remove_small_'+str(i)+'.txt', 'r')
        for line in f:
            key = line.replace('\n', '').strip()
            if key not in bad_dict:
                bad_dict[key] = 1
                n += 1
    
    print('>>>>>>>>>>>>>>>> : ', n)
    print('after size of bad dict: ', len(bad_dict))
    
    hit_num = 0
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
    df.to_csv('/mnt/vast/hongyuan/3d_data_git_step1x/metadata_filter.csv', index=False)


merge_data_csv()

