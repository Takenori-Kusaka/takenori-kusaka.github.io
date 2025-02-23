import torch
from transformers import WhisperProcessor, WhisperForConditionalGeneration

# 設定
model_id = "kotoba-tech/kotoba-whisper-v2.0"
device = "cuda" if torch.cuda.is_available() else "cpu"

# プロセッサとモデルのロード
processor = WhisperProcessor.from_pretrained(model_id)
model = WhisperForConditionalGeneration.from_pretrained(model_id).to(device)
