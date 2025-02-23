import os
import sys
import torch
import subprocess
from transformers import pipeline
import pprint

# 追加: transcript整形用関数
def format_transcript(result):
    if "segments" in result:
        transcript = ""
        current_speaker = None
        for seg in result["segments"]:
            speaker = seg.get("speaker", "Unknown Speaker")  # 話者情報がない場合はデフォルト値を設定
            if speaker != current_speaker:
                transcript += "\n\n" + (f"{speaker}: " if speaker else "")
                current_speaker = speaker
            transcript += seg.get("text", "")
        return transcript.strip()
    else:
        # fallback: 結果全体をデバッグログとして出力
        return pprint.pformat(result)

def main():
    # ffmpegの存在チェック
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: ffmpegが見つかりません。ffmpegをインストールし、PATHに追加してください。")
        sys.exit(1)

    if len(sys.argv) < 3:
        print("Usage: python whisper.py <input_filename.m4a> <output_directory>")
        sys.exit(1)
    
    input_filename = sys.argv[1]
    output_dir = sys.argv[2]
    
    # 入力ファイルはプロジェクトルートのaudioフォルダ内
    audio_path = os.path.join(input_filename)
    if not os.path.exists(audio_path):
        print(f"Audio file not found: {audio_path}")
        sys.exit(1)

    # 設定
    model_id = "kotoba-tech/kotoba-whisper-v2.0"
    torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    device = 0 if torch.cuda.is_available() else -1
    model_kwargs = {"attn_implementation": "sdpa"} if torch.cuda.is_available() else {}

    # モデルのロード（languageパラメータを削除）
    try:
        pipe = pipeline(
            model=model_id,
            torch_dtype=torch_dtype,
            device=device,
            model_kwargs=model_kwargs,
            batch_size=8,
            trust_remote_code=True,
        )
    except ImportError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # 推論の実行（pipe呼び出し時にlanguageを指定、chunk_length_sは15秒）
    result = pipe(audio_path, chunk_length_s=15)
    pprint.pprint(result)
    
    # 出力ディレクトリが存在しない場合は作成
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 結果をテキストとして保存（出力先はプロジェクトルートのtextフォルダ）
    # 修正：basenameを用いてファイル名のみ取得
    output_filename = os.path.splitext(os.path.basename(input_filename))[0] + ".txt"
    output_path = os.path.join(output_dir, output_filename)
    with open(output_path, "w", encoding="utf-8") as f:
        # 出力テキストを整形
        transcript = format_transcript(result)
        f.write(transcript)
    print(f"Transcript saved to: {output_path}")

if __name__ == "__main__":
    main()
