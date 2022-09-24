echo 'Start to convert to wav from m4a'
Get-Date -Format "yyyy/MM/dd HH:mm:ss"
$TargetNameRaw = (Get-ChildItem . -File -Recurse -Include *.m4a | Sort-Object name -Descending)[0].BaseName
$TargetName = $TargetNameRaw.ReplaceLineEndings("")
$TargetName
ffmpeg -i ./audio/$TargetName.m4a ./audio/$TargetName.wav
echo 'Start to convert wav to text with whisper'
Get-Date -Format "yyyy/MM/dd HH:mm:ss"
whisper ./audio/$TargetName.wav --language Japanese --model medium --output_dir ./_text/
echo 'Delete wav file'
Get-Date -Format "yyyy/MM/dd HH:mm:ss"
Remove-Item -Path ./audio/$TargetName.wav -Force
echo 'Complete'
Get-Date -Format "yyyy/MM/dd HH:mm:ss"
