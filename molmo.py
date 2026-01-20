from transformers import AutoProcessor, AutoModelForImageTextToText
import torch

model_id="allenai/Molmo2-4B"

# load the processor
processor = AutoProcessor.from_pretrained(
    model_id,
    trust_remote_code=True,
    dtype="auto",
    device_map="auto"
)

# load the model
model = AutoModelForImageTextToText.from_pretrained(
    model_id,
    trust_remote_code=True,
    torch_dtype=torch.float16,
    device_map="cuda"
)


# process the video and text
messages = [
    {
        "role": "user",
        "content": [
            dict(type="text", text="Which animal appears in the video?"),
            dict(type="video", video="https://storage.googleapis.com/oe-training-public/demo_videos/many_penguins.mp4"),
        ],
    }
]

inputs = processor.apply_chat_template(
    messages,
    tokenize=True,
    add_generation_prompt=True,
    return_tensors="pt",
    return_dict=True,
)

inputs = {k: v.to(model.device) for k, v in inputs.items()}

# generate output
with torch.inference_mode():
    generated_ids = model.generate(**inputs, max_new_tokens=2048)

# only get generated tokens; decode them to text
generated_tokens = generated_ids[0, inputs['input_ids'].size(1):]
generated_text = processor.tokenizer.decode(generated_tokens, skip_special_tokens=True)

# print the generated text
print(generated_text)

# >>>  Penguins appear in the video.
