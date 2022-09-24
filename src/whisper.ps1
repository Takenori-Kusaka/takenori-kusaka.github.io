echo 'Start to convert to wav from m4a'
Get-Date -Format "yyyy/MM/dd HH:mm:ss"
ffmpeg -i ./audio/$Args[0].m4a ./audio/$Args[0].wav
echo 'Start to convert wav to text with whisper'
Get-Date -Format "yyyy/MM/dd HH:mm:ss"
whisper ./audio/$Args[0].wav --language Japanese --model medium --output_dir ./_text/
echo 'Delete wav file'
Get-Date -Format "yyyy/MM/dd HH:mm:ss"
Remove-Item -Path ./audio/$Args[0].wav -Force
echo 'Complete'
Get-Date -Format "yyyy/MM/dd HH:mm:ss"
