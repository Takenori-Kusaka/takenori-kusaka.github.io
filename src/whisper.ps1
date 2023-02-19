echo 'Start to convert to wav from m4a'
Get-Date -Format "yyyy/MM/dd HH:mm:ss"
$TargetNameRaw = (Get-ChildItem ./audio -File -Recurse -Include *.m4a | Sort-Object name -Descending)[0].BaseName
$TargetNameRaw
$TargetName = $TargetNameRaw.ReplaceLineEndings("")
$TargetName
ffmpeg -i ./audio/$TargetName.m4a ./audio/$TargetName.wav
echo 'Start to upgrade newest whisper'
pip install --upgrade --no-deps --force-reinstall git+https://github.com/openai/whisper.git
echo 'Start to convert wav to text with whisper'
Get-Date -Format "yyyy/MM/dd HH:mm:ss"
whisper ./audio/$TargetName.wav --language Japanese --model large --device cuda --output_dir ./text/
echo 'Delete wav file'
Get-Date -Format "yyyy/MM/dd HH:mm:ss"
Remove-Item -Path ./audio/$TargetName.wav -Force
Remove-Item -Path ./text/$TargetName.wav.txt -Force
Remove-Item -Path ./text/$TargetName.wav.json -Force
Remove-Item -Path ./text/$TargetName.wav.vtt -Force
Remove-Item -Path ./text/$TargetName.wav.srt -Force
echo 'Complete'
Get-Date -Format "yyyy/MM/dd HH:mm:ss"
