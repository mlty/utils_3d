from transformers import Qwen2_5_VLForConditionalGeneration, AutoTokenizer, AutoProcessor
from qwen_vl_utils import process_vision_info
import re
import argparse
from easydict import EasyDict as edict
from tqdm import tqdm


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

    import os
    index = 0
    file_dir = {}
    folder_path = '/mnt/vast/hongyuan/jiaguyi_tmp/renders_cond/'
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if index % world_size == rank:
            file_dir[file_path] = 1
        index += 1
    
    print(world_size, ' > ', rank, 'size of file_dir: ', len(file_dir))
    fw = open('tex_large_score'+str(rank)+'_list.txt', 'a+')

    for tmp_dir in tqdm(file_dir):
        try:
            messages = [
                {
                    "role": "user",
                    "content": [
                        *[
                        {"type": "image", "image": f"{tmp_dir}/{(i):03d}.png"}
                        for i in range(0, 6)
                        ],
                        {"type": "text", "text": "以上是物体多个视角的图片，判断图片中的物体: 1.是什么物体 2.是否形状碎片 3.存在损坏/破损的情况 4.只有白色 5.只有岩石/石头/碎块/砖块 6.只有一个平面，返回判断结果，返回json格式 {'是什么': 'XXX/无法识别', '形状碎片化': 'Yes' or 'No', '破损': 'Yes' or 'No', '只有白色': 'Yes' or 'No', '只有岩石/石头/碎片': 'Yes' or 'No', '只有一个平面': 'Yes' or 'No'}，只返回json格式，不要返回其他内容"},
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
            if 'Yes' in result_text or '无法识别' in result_text:
                print('-------------------NO--------------------> ')
                print(tmp_dir)
                print(result_text)
                print('\n\n')
                fw.write(tmp_dir.strip()+'|'+result_text.strip()+'\n')
            # else:
            #     print('*******************OK*********************> ')
            #     print(tmp_dir)
            #     print(result_text)
            #     print('\n\n')
            
        except Exception as e:
            print(f"Error processing directory {tmp_dir}: {e}")
        
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rank', type=int, default=0)
    parser.add_argument('--world_size', type=int, default=980)
    opt = parser.parse_args()
    opt = edict(vars(opt))
    init_model(opt.rank, opt.world_size)