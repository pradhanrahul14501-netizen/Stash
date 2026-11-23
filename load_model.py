import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_id = "gpt2"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id, device_map="mps")

print("Model successfully loaded on:", model.device)
