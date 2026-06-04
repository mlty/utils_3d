from transformers import Qwen2_5_VLForConditionalGeneration, AutoTokenizer, AutoProcessor
from qwen_vl_utils import process_vision_info
import re
import argparse
from easydict import EasyDict as edict
from tqdm import tqdm
import os


def analysis_for_jiaguyi():

    dataList = []
    hit_num = 0
    for i in range(20):
        f = open('/mnt/home/hongyuanzhu/utils_3d/eval_3d_data_from_blender/jiaguyi_7_score'+str(i)+'.txt', 'r')
        for line in f:
            num = int(line.replace('\n', '').split(' ')[1])
            if num <= 4:
                
                path = os.path.join('/'.join(line.replace('\n', '').split(' ')[0].split('/')[:-1]), 'Image_0.png')
                if os.path.exists(path):
                    dataList.append(path)
                    hit_num += 1
    # /mnt/vast/hongyuan/CG_data/raw/model_jiaguyi_4/动物_不包含PBR和骨骼_写实风_2299/动物_野生动物/动物_野生动物1147/动物_野生动物1147.glb 3 18.243518829345703 
    print('hit_num : ', hit_num)
    
    return dataList

def init_model(rank, world_size):
    # default: Load the model on the available device(s)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        "/mnt/vast/hongyuan/qvl_2.5", torch_dtype="auto", device_map="auto"
    )

    # We recommend enabling flash_attention_2 for better acceleration and memory saving, especially in multi-image and video scenarios.
    # model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    #     "Qwen/Qwen2.5-VL-7B-Instruct",
    #     torch_dtype=torch.bfloat16,
    #     attn_implementation="flash_attention_2",
    #     device_map="auto",
    # )

    # default processer
    processor = AutoProcessor.from_pretrained("/mnt/vast/hongyuan/qvl_2.5")

    # The default range for the number of visual tokens per image in the model is 4-16384.
    # You can set min_pixels and max_pixels according to your needs, such as a token range of 256-1280, to balance performance and cost.
    # min_pixels = 256*28*28
    # max_pixels = 1280*28*28
    # processor = AutoProcessor.from_pretrained("Qwen/Qwen2.5-VL-7B-Instruct", min_pixels=min_pixels, max_pixels=max_pixels)

    dataList = analysis_for_jiaguyi()
    fw = open('cg_jgy7_text_score'+str(rank)+'_list.txt', 'a+')
    index = 0

    for tmp_dir in tqdm(dataList):
        if index % world_size == rank:
            try:
                messages = [
                    {
                        "role": "user",
                        "content": [
                            *[
                            {"type": "image", "image": f"{tmp_dir}"}
                            ],
                            {"type": "text", "text": f"以上是物体的图片，判断图片: 是不是碎片状，是否有具体的部件(如眼睛/嘴巴/四肢，等)，是否有矩形/方形/块状/圆形等形状？返回判断结果，返回json格式 {{'碎片状': 'Yes' or 'No', '具体部件': 'Yes' or 'No', '特定形状': 'Yes' or 'No'}}，只返回json格式，不要返回其他内容"},
                        ],
                    }
                ]
                
                # Preparation for inference
                text = processor.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                image_inputs, video_inputs = process_vision_info(messages)
                inputs = processor(
                    text=[text],
                    images=image_inputs,
                    videos=video_inputs,
                    padding=True,
                    return_tensors="pt",
                )
                inputs = inputs.to("cuda")

                # Inference: Generation of the output
                generated_ids = model.generate(**inputs, max_new_tokens=128)
                generated_ids_trimmed = [
                    out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
                ]
                output_text = processor.batch_decode(
                    generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
                )

                result_text = output_text[0]
                # {"碎片状": "Yes", "具体部件": "No", "特定形状": "No"}

                if '"碎片状": "Yes"' in result_text and '"具体部件": "No"' in result_text and '"特定形状": "No"' in result_text:
                    print('-------------------NO--------------------> ')
                    print(tmp_dir)
                    print(result_text)
                    print('\n\n')
                    fw.write(tmp_dir.strip() + '\n')
                # else:
                #     print('*******************OK*********************> ')
                #     print(tmp_dir)
                #     print(result_text)
                #     print('\n\n')
            
            except Exception as e:
                print(f"Error processing directory {tmp_dir}: {e}")
        
        index += 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rank', type=int, default=0)
    parser.add_argument('--world_size', type=int, default=300)
    opt = parser.parse_args()
    opt = edict(vars(opt))
    init_model(opt.rank, opt.world_size)