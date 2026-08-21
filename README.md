# 工具箱

Windows 桌面小工具集合，基于 PySide6。首页为固定尺寸的原生窗口，按按钮进入各工具。作者：玖渚東（KunagisaAzuma）。

当前版本：`26.08.21`

## 功能

### 音视频分离

从视频中分离音轨或画面。内置 FFmpeg，支持单文件与批量处理。

### 深度图生成

根据导入的图片生成深度图，可导出彩色或黑白结果。推理使用 ONNX Runtime，有 GPU 执行提供程序时自动走 GPU，否则使用 CPU。

内置多种深度估计模型（MiDaS、Depth Anything V2 等）。首次使用需联网下载模型，下载由内置 aria2 多线程完成。

## 运行

```text
pip install -r requirements.txt
python main.py
```

GPU 推理需另行安装带 GPU 的 ONNX Runtime（如 `onnxruntime-gpu` 或 `onnxruntime-directml`）。深度模型文件会保存到项目下的 `models/depth/`。

## 致谢

感谢 Cursor、ChatGPT、Qwen、DeepSeek 的大力支持。
