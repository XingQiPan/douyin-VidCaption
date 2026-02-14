# 视频文案提取器

基于 Whisper 的本地视频文案提取工具，支持批量处理和 LLM 智能清理。

## 功能特点

- 🎤 **语音识别** - 使用 OpenAI Whisper 本地识别，完全免费
- 📦 **批量处理** - 支持多个视频链接同时处理
- 🤖 **LLM清理** - 可接入大语言模型优化文案
- 📁 **自动保存** - 文案自动保存到 output 目录
- 🧹 **自动清理** - 临时视频文件自动删除

## 项目结构

```
XYYW/
├── venv/                    # Python虚拟环境
├── videos/                  # 临时视频存放（自动清理）
├── output/                  # 文案输出目录
├── video_caption_app.py     # 主应用
└── README.md                # 使用说明
```

## 安装

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\activate

# 安装依赖
pip install streamlit openai-whisper imageio-ffmpeg requests openai
```

## 启动

```bash
# 激活虚拟环境
.\venv\Scripts\activate

# 启动应用
streamlit run video_caption_app.py
```

访问 http://localhost:8501 使用

## Whisper 模型说明

| 模型 | 参数 | 速度 | 准确率 | 内存 | 说明 |
|------|------|------|--------|------|------|
| tiny | 39M | 最快 | 一般 | ~1GB | 快速识别，适合对准确率要求不高 |
| **base** | **74M** | **较快** | **良好** | **~1GB** | **平衡选择，推荐日常使用** |
| small | 244M | 中等 | 较好 | ~2GB | 准确率更高，适合重要内容 |
| medium | 769M | 较慢 | 很好 | ~5GB | 高准确率，需要更多内存 |
| large | 1550M | 最慢 | 最佳 | ~10GB | 最高准确率，适合专业场景 |

## LLM 配置

支持 OpenAI 兼容 API，可接入：
- OpenAI GPT
- DeepSeek
- 通义千问
- 智谱 GLM
- 其他兼容 API

配置方式：
1. 勾选"启用LLM清理"
2. 输入 API Key
3. 输入 API Base URL（如：`https://api.deepseek.com/v1`）
4. 输入模型名称（如：`deepseek-chat`）

## 使用说明

1. 在输入框粘贴视频链接（每行一个）
2. 选择 Whisper 模型（推荐 base）
3. 可选：启用 LLM 清理
4. 点击"开始提取"
5. 文案自动保存到 `output/` 目录

## 支持平台

- 抖音
- 小红书
- B站
- 微博
- 或直接提供视频 URL
