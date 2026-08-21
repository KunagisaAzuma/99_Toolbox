# 单文件打包（内置 FFmpeg）
# 输出: dist\工具箱.exe
# 注意: 体积约 250MB+，首次启动需解压到临时目录，会稍慢

.\.venv\Scripts\python.exe -m pip install pyinstaller -q
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean flm.spec

$out = Join-Path $PSScriptRoot "dist\工具箱.exe"
if (Test-Path $out) {
    $sizeMB = [math]::Round((Get-Item $out).Length / 1MB, 1)
    Write-Host ""
    Write-Host "单文件打包完成: $out"
    Write-Host "大小: ${sizeMB} MB"
} else {
    Write-Host "打包失败，未找到输出文件"
    exit 1
}
