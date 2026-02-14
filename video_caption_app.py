# -*- coding: utf-8 -*-
"""
视频文案提取器 - Web应用
支持批量提取视频文案，可接入大语言模型进行文案清理

项目结构:
├── venv/                   # 虚拟环境
├── videos/                 # 临时视频存放（自动清理）
├── output/                 # 文案输出目录
├── config.json             # API配置（自动保存）
├── video_caption_app.py    # 主应用
└── README.md               # 使用说明

启动方式:
    streamlit run video_caption_app.py
"""

import streamlit as st
import os
import re
import json
import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# ==================== 配置 ====================
BASE_DIR = Path(__file__).parent
VIDEOS_DIR = BASE_DIR / "videos"
OUTPUT_DIR = BASE_DIR / "output"
CONFIG_FILE = BASE_DIR / "config.json"

# 确保目录存在
VIDEOS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Whisper模型说明
WHISPER_MODELS = {
    "tiny": {"params": "39M", "speed": "最快", "accuracy": "一般", "memory": "~1GB", "desc": "快速识别，适合对准确率要求不高的场景"},
    "base": {"params": "74M", "speed": "较快", "accuracy": "良好", "memory": "~1GB", "desc": "平衡选择，推荐日常使用"},
    "small": {"params": "244M", "speed": "中等", "accuracy": "较好", "memory": "~2GB", "desc": "准确率更高，适合重要内容"},
    "medium": {"params": "769M", "speed": "较慢", "accuracy": "很好", "memory": "~5GB", "desc": "高准确率，需要更多内存"},
    "large": {"params": "1550M", "speed": "最慢", "accuracy": "最佳", "memory": "~10GB", "desc": "最高准确率，适合专业场景"},
}

# 页面配置
st.set_page_config(
    page_title="视频文案提取器",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS
st.markdown("""
<style>
    .main-header {font-size: 2.5rem; color: #FF4B4B; text-align: center; margin-bottom: 2rem;}
    .success-box {padding: 1rem; border-radius: 0.5rem; background-color: #d4edda; border: 1px solid #c3e6cb; margin: 1rem 0;}
    .error-box {padding: 1rem; border-radius: 0.5rem; background-color: #f8d7da; border: 1px solid #f5c6cb; margin: 1rem 0;}
    .caption-box {padding: 1rem; border-radius: 0.5rem; background-color: #f8f9fa; border: 1px solid #dee2e6; margin: 1rem 0; max-height: 400px; overflow-y: auto;}
    .model-card {padding: 1rem; border-radius: 0.5rem; background-color: #fff; border: 1px solid #dee2e6; margin: 0.5rem 0;}
    .stProgress > div > div > div > div {background-color: #FF4B4B;}
</style>
""", unsafe_allow_html=True)


# ==================== 配置管理 ====================
def load_config() -> Dict[str, Any]:
    """加载配置文件"""
    default_config = {
        "api_key": "",
        "api_base": "https://api.openai.com/v1",
        "llm_model": "gpt-3.5-turbo",
        "model_size": "base",
        "use_llm": False,
        "auto_save": True,
        "clean_prompt": """请帮我清理和优化以下语音转文字内容：

{text}

要求：
1. 修正错别字和语法错误
2. 添加适当的标点符号
3. 分段整理，提高可读性
4. 保持原意，不要添加新内容
5. 提取一个简洁的标题放在最前面

格式：
【标题】xxx

正文内容...

请按此格式输出："""
    }

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                default_config.update(saved)
        except:
            pass
    return default_config


def save_config(config: Dict[str, Any]):
    """保存配置文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.warning(f"保存配置失败: {e}")
        return False


def check_dependencies():
    """检查依赖是否安装"""
    missing = []
    try:
        import whisper
    except ImportError:
        missing.append("openai-whisper")
    try:
        import imageio_ffmpeg
    except ImportError:
        missing.append("imageio-ffmpeg")
    try:
        import requests
    except ImportError:
        missing.append("requests")
    return missing


def setup_ffmpeg():
    """设置ffmpeg环境"""
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_dir = os.path.dirname(ffmpeg_path)
        ffmpeg_exe = os.path.join(ffmpeg_dir, 'ffmpeg.exe')
        if not os.path.exists(ffmpeg_exe):
            shutil.copy(ffmpeg_path, ffmpeg_exe)
        os.environ['PATH'] = ffmpeg_dir + os.pathsep + os.environ.get('PATH', '')
        return True
    except Exception as e:
        st.error(f"ffmpeg设置失败: {e}")
        return False


@st.cache_resource
def load_whisper_model(model_size="base"):
    """加载Whisper模型（缓存）"""
    import whisper
    return whisper.load_model(model_size)


def extract_video_url(video_input: str) -> Optional[str]:
    """从链接提取视频下载URL"""
    import requests

    # 模拟手机浏览器
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.douyin.com/'
    }

    def decode_url(url):
        """解码URL中的转义字符"""
        if not url:
            return url
        # 处理Unicode转义序列
        import codecs
        try:
            # 尝试解码Unicode转义
            url = codecs.decode(url, 'unicode_escape')
        except:
            pass
        # 处理反斜杠转义
        url = url.replace('\\/', '/')
        if url.startswith('//'):
            url = 'https:' + url
        return url

    try:
        # 直接是视频URL
        if video_input.endswith(('.mp4', '.webm', '.mkv', '.m3u8')):
            return video_input

        # 抖音短链接处理
        if 'v.douyin.com' in video_input or 'douyin.com' in video_input or 'iesdouyin.com' in video_input:
            st.info("正在解析抖音链接...")

            # 第一步：获取重定向后的真实URL
            try:
                resp = requests.get(video_input, headers=headers, allow_redirects=True, timeout=15)
                final_url = resp.url
                page_content = resp.text
            except Exception as e:
                st.warning(f"获取页面失败: {e}")
                return None

            # 提取aweme_id
            aweme_id_match = re.search(r'/video/(\d+)', final_url)
            if not aweme_id_match:
                aweme_id_match = re.search(r'aweme_id[=:]["\']?(\d+)', page_content)

            # 获取share页面内容（包含更多数据）
            if aweme_id_match:
                aweme_id = aweme_id_match.group(1)
                share_url = f'https://www.iesdouyin.com/share/video/{aweme_id}/'
                try:
                    share_resp = requests.get(share_url, headers=headers, timeout=15)
                    page_content = share_resp.text
                except:
                    pass

            # 从页面内容中提取视频URL - 多种模式尝试
            patterns = [
                r'"play_addr"[^}]*"url_list"\s*:\s*\["([^"]+)"',
                r'"video"[^}]*"play_addr"[^}]*"url_list"\s*:\s*\["([^"]+)"',
                r'"playApi"\s*:\s*"([^"]+)"',
                r'playAddr.*?src["\']?\s*:\s*["\']([^"\']+)["\']',
            ]

            for pattern in patterns:
                matches = re.findall(pattern, page_content, re.IGNORECASE | re.DOTALL)
                if matches:
                    url = decode_url(matches[0])
                    if 'http' in url:
                        # 替换playwm为play获取无水印版本
                        url = url.replace('/playwm/', '/play/')
                        st.success(f"✅ 成功提取视频URL")
                        return url

            # 备用：尝试找aweme.snssdk.com链接
            aweme_pattern = r'(https?://aweme\.snssdk\.com/[^"\'>\s]+)'
            matches = re.findall(aweme_pattern, page_content)
            if matches:
                url = decode_url(matches[0])
                url = url.replace('/playwm/', '/play/')
                st.success(f"✅ 成功提取视频URL (备用模式)")
                return url

            st.warning("无法从页面提取视频URL，抖音可能更新了页面结构")
            return None

        return None

    except Exception as e:
        st.warning(f"提取视频URL失败: {e}")
        return None


def download_video_with_ytdlp(url: str, output_path: str) -> bool:
    """使用yt-dlp下载视频"""
    try:
        import yt_dlp
        import glob

        output_dir = os.path.dirname(output_path)
        base_name = os.path.basename(output_path).replace('.mp4', '')

        ydl_opts = {
            'outtmpl': os.path.join(output_dir, base_name),
            'format': 'best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
            'extract_audio': False,
            'noplaylist': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # 查找下载的文件并重命名为.mp4
        pattern = os.path.join(output_dir, base_name + '*')
        files = glob.glob(pattern)
        for f in files:
            if not f.endswith('.mp4') and not f.endswith('.part'):
                os.rename(f, f + '.mp4')
                return True
            elif f.endswith('.mp4'):
                return True

        return False
    except ImportError:
        return False
    except Exception as e:
        st.warning(f"yt-dlp下载失败: {e}")
        return False


def download_douyin_with_selenium(url: str, output_dir: Path) -> Optional[str]:
    """使用Selenium下载抖音视频，返回下载的文件路径"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        import time

        st.info("正在启动浏览器...")

        # 使用webdriver_manager自动管理ChromeDriver版本
        options = Options()
        options.add_argument('--headless')  # 无头模式
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)

        # 设置下载目录
        prefs = {
            "download.default_directory": str(output_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        options.add_experimental_option("prefs", prefs)

        # 自动下载匹配的ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        try:
            st.info("正在访问抖音页面...")
            driver.get(url)
            time.sleep(5)  # 等待页面加载

            # 获取页面标题
            title = driver.title.split(' - ')[0]
            st.info(f"视频标题: {title}")

            # 执行JavaScript获取音频URL
            audio_url = driver.execute_script("""
            var resources = performance.getEntriesByType('resource');
            for (var i = 0; i < resources.length; i++) {
                if (resources[i].name.includes('media-audio')) {
                    return resources[i].name;
                }
            }
            return null;
            """)

            if not audio_url:
                # 刷新页面重试
                driver.refresh()
                time.sleep(5)
                audio_url = driver.execute_script("""
                var resources = performance.getEntriesByType('resource');
                for (var i = 0; i < resources.length; i++) {
                    if (resources[i].name.includes('media-audio')) {
                        return resources[i].name;
                    }
                }
                return null;
                """)

            if audio_url:
                st.info("正在下载音频...")

                # 使用fetch下载音频
                result = driver.execute_async_script(f"""
                var callback = arguments[arguments.length - 1];
                (async function() {{
                    try {{
                        var response = await fetch('{audio_url}');
                        var blob = await response.blob();
                        var url = URL.createObjectURL(blob);
                        var a = document.createElement('a');
                        a.href = url;
                        a.download = 'audio.m4a';
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        callback({{success: true, size: blob.size}});
                    }} catch(e) {{
                        callback({{success: false, error: e.message}});
                    }}
                }})();
                """)

                if result and result.get('success'):
                    st.info(f"音频下载中... ({result.get('size', 0)} bytes)")
                    time.sleep(5)  # 等待下载完成

                    # 查找下载的文件
                    downloaded_files = list(output_dir.glob("*.m4a")) + list(output_dir.glob("*.mp4"))
                    if downloaded_files:
                        # 找最新的文件
                        latest = max(downloaded_files, key=lambda f: f.stat().st_mtime)
                        # 重命名文件
                        safe_title = re.sub(r'[<>:"/\\\\|?*]', '', title)[:50]
                        new_path = output_dir / f"{safe_title}.m4a"
                        if latest != new_path:
                            latest.rename(new_path)
                        driver.quit()
                        return str(new_path)

            driver.quit()
            return None

        except Exception as e:
            driver.quit()
            st.error(f"下载过程出错: {e}")
            return None

    except ImportError as e:
        st.warning(f"未安装必要依赖: {e}")
        return None
    except Exception as e:
        st.error(f"浏览器启动失败: {e}")
        return None


def download_video(url: str, output_path: str) -> bool:
    """下载视频 - 优先使用yt-dlp，失败则用requests"""
    import requests

    # 先尝试yt-dlp
    if download_video_with_ytdlp(url, output_path):
        return True

    # 完整的浏览器headers模拟
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148',
        'Accept': '*/*',
        'Accept-Encoding': 'identity',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.douyin.com/',
        'Connection': 'keep-alive',
    }

    try:
        # 第一次请求获取真实下载地址
        resp = requests.get(url, headers=headers, stream=True, timeout=30, allow_redirects=True)

        # 检查是否需要跟随重定向
        if resp.status_code in (301, 302, 303, 307, 308):
            redirect_url = resp.headers.get('Location')
            if redirect_url:
                resp = requests.get(redirect_url, headers=headers, stream=True, timeout=120)

        resp.raise_for_status()

        with open(output_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        st.error(f"下载失败: {e}")
        return False


def transcribe_video(video_path: str, model_size: str = "base") -> Dict[str, Any]:
    """使用Whisper进行语音识别"""
    import whisper
    import warnings
    warnings.filterwarnings('ignore')

    if not setup_ffmpeg():
        return {"success": False, "error": "ffmpeg设置失败"}

    try:
        model = load_whisper_model(model_size)
        result = model.transcribe(video_path, language='zh')
        return {
            "success": True,
            "text": result.get('text', ''),
            "segments": result.get('segments', [])
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def clean_with_llm(text: str, api_key: str, api_base: str, model: str, prompt_template: str) -> Dict[str, Any]:
    """使用大语言模型清理文案，返回清理后的文本和标题"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=api_base)
        prompt = prompt_template.format(text=text)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个专业的文案编辑助手，擅长整理和优化文字内容。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        cleaned_text = response.choices[0].message.content

        # 尝试提取标题
        title = None
        title_match = re.search(r'【标题】(.+?)(?:\n|$)', cleaned_text)
        if title_match:
            title = title_match.group(1).strip()
        else:
            # 用第一行作为标题
            first_line = cleaned_text.strip().split('\n')[0]
            if len(first_line) < 50:
                title = first_line

        return {"success": True, "text": cleaned_text, "title": title}
    except Exception as e:
        return {"success": False, "text": f"LLM清理失败: {e}", "title": None}


def extract_title_from_text(text: str, max_length: int = 30) -> str:
    """从文本中提取标题（取第一句有意义的话）"""
    # 移除空白
    text = text.strip()

    # 尝试取第一句
    sentences = re.split(r'[。！？\n]', text)
    for s in sentences:
        s = s.strip()
        if len(s) >= 5 and len(s) <= max_length:
            return s

    # 取前max_length个字符
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text if text else "未命名"


def sanitize_filename(name: str) -> str:
    """清理文件名，移除非法字符"""
    # 移除Windows非法字符
    illegal_chars = r'[<>:"/\\|?*]'
    name = re.sub(illegal_chars, '', name)
    # 移除首尾空格和点
    name = name.strip('. ')
    # 限制长度
    if len(name) > 50:
        name = name[:50]
    return name if name else "未命名"


def save_caption(result: Dict[str, Any], output_dir: Path, index: int, use_llm: bool) -> Path:
    """保存文案到文件"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 确定文件名
    if use_llm and result.get("cleaned_title"):
        title = result["cleaned_title"]
    elif result.get("transcript"):
        title = extract_title_from_text(result["transcript"])
    else:
        title = f"video{index}"

    safe_title = sanitize_filename(title)
    filename = f"{timestamp}_{safe_title}.txt"
    filepath = output_dir / filename

    content = f"视频文案提取结果\n"
    content += f"{'='*60}\n"
    content += f"时间: {result.get('timestamp', '')}\n"
    content += f"来源: {result.get('input', '')}\n"
    content += f"{'='*60}\n\n"

    # if result.get("transcript"):
    #     content += f"【语音转文字】\n{result['transcript']}\n\n"

    if result.get("cleaned"):
        content += f"{'='*60}\n"
        content += f"【LLM清理后】\n{result['cleaned']}\n\n"

    # if result.get("segments"):
    #     content += f"{'='*60}\n"
    #     content += f"【分段字幕】\n"
    #     for seg in result["segments"]:
    #         start = f"{int(seg['start']//60):02d}:{int(seg['start']%60):02d}"
    #         end = f"{int(seg['end']//60):02d}:{int(seg['end']%60):02d}"
    #         content += f"[{start} - {end}] {seg['text'].strip()}\n"

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    return filepath


def cleanup_video_files():
    """清理临时视频文件"""
    try:
        for file in VIDEOS_DIR.glob("*"):
            if file.is_file():
                file.unlink()
        return True
    except Exception as e:
        st.warning(f"清理临时文件失败: {e}")
        return False


def process_video(video_input: str, model_size: str, use_llm: bool,
                  api_key: str, api_base: str, llm_model: str,
                  clean_prompt: str, progress_callback=None) -> Dict[str, Any]:
    """处理单个视频"""
    result = {
        "input": video_input,
        "timestamp": datetime.now().isoformat(),
        "success": False
    }

    video_path = None
    is_temp_video = False

    try:
        # 判断是URL还是本地文件
        is_url = video_input.startswith('http://') or video_input.startswith('https://')

        if is_url:
            # 检查是否是抖音链接，使用Selenium下载
            if 'douyin.com' in video_input or 'v.douyin.com' in video_input:
                if progress_callback:
                    progress_callback(0.1, "正在使用浏览器下载...")

                downloaded_file = download_douyin_with_selenium(video_input, VIDEOS_DIR)
                if downloaded_file:
                    video_path = Path(downloaded_file)
                    is_temp_video = True
                    if progress_callback:
                        progress_callback(0.5, "下载完成，正在进行语音识别...")
                else:
                    # Selenium失败，尝试常规方式
                    if progress_callback:
                        progress_callback(0.2, "尝试常规下载...")

                    video_url = extract_video_url(video_input)
                    if video_url:
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        video_path = VIDEOS_DIR / f"{timestamp}.mp4"
                        is_temp_video = True
                        if not download_video(video_url, str(video_path)):
                            result["error"] = "视频下载失败"
                            return result
                    else:
                        result["error"] = "无法提取视频URL"
                        return result
            else:
                # 非抖音链接，使用常规方式
                if progress_callback:
                    progress_callback(0.1, "正在解析链接...")

                video_url = extract_video_url(video_input)
                if not video_url:
                    result["error"] = "无法提取视频URL，请检查链接或直接提供视频下载地址"
                    return result

                if progress_callback:
                    progress_callback(0.2, "正在下载视频...")

                # 下载到videos目录
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                video_path = VIDEOS_DIR / f"{timestamp}.mp4"
                is_temp_video = True

                if not download_video(video_url, str(video_path)):
                    result["error"] = "视频下载失败"
                    return result
        else:
            video_path = Path(video_input)
            if not video_path.exists():
                result["error"] = f"文件不存在: {video_input}"
                return result

        if progress_callback:
            progress_callback(0.5, "正在进行语音识别...")

        # 语音识别
        transcript_result = transcribe_video(str(video_path), model_size)

        if not transcript_result["success"]:
            result["error"] = transcript_result.get("error", "语音识别失败")
            return result

        result["transcript"] = transcript_result["text"]
        result["segments"] = transcript_result["segments"]
        result["success"] = True

        # LLM清理
        if use_llm and api_key:
            if progress_callback:
                progress_callback(0.8, "正在进行LLM清理...")
            llm_result = clean_with_llm(
                transcript_result["text"], api_key, api_base, llm_model, clean_prompt
            )
            result["cleaned"] = llm_result["text"]
            if llm_result.get("title"):
                result["cleaned_title"] = llm_result["title"]

        if progress_callback:
            progress_callback(1.0, "完成!")

    except Exception as e:
        result["error"] = str(e)

    finally:
        # 清理临时视频
        if is_temp_video and video_path and video_path.exists():
            try:
                video_path.unlink()
            except:
                pass

    return result


def main():
    # 标题
    st.markdown('<h1 class="main-header">🎬 视频文案提取器</h1>', unsafe_allow_html=True)

    # 检查依赖
    missing_deps = check_dependencies()
    if missing_deps:
        st.error(f"缺少依赖: {', '.join(missing_deps)}")
        st.code(f"pip install {' '.join(missing_deps)}")
        return

    # 加载保存的配置
    saved_config = load_config()

    # 侧边栏配置
    with st.sidebar:
        st.header("⚙️ 设置")

        # Whisper模型选择
        st.subheader("🎤 语音识别模型")
        model_size = st.selectbox(
            "Whisper模型",
            list(WHISPER_MODELS.keys()),
            index=list(WHISPER_MODELS.keys()).index(saved_config.get("model_size", "base")),
            help="模型越大越准确，但速度越慢"
        )

        # 显示模型说明
        with st.expander("📖 模型说明"):
            for name, info in WHISPER_MODELS.items():
                icon = "✅" if name == model_size else "⚪"
                st.markdown(f"**{icon} {name}** ({info['params']})")
                st.caption(f"速度: {info['speed']} | 准确率: {info['accuracy']} | {info['desc']}")

        st.markdown("---")

        # 输出设置
        st.subheader("📁 输出设置")
        auto_save = st.checkbox("自动保存文案", value=saved_config.get("auto_save", True), help="提取完成后自动保存到output目录")
        if auto_save:
            st.caption(f"保存路径: `{OUTPUT_DIR}`")

        st.markdown("---")

        # LLM配置
        st.subheader("🤖 LLM清理")
        use_llm = st.checkbox("启用LLM清理", value=saved_config.get("use_llm", False))

        if use_llm:
            api_key = st.text_input("API Key", value=saved_config.get("api_key", ""), type="password")
            api_base = st.text_input(
                "API Base URL",
                value=saved_config.get("api_base", "https://api.openai.com/v1"),
                help="支持OpenAI兼容API：DeepSeek、通义千问、智谱等"
            )
            llm_model = st.text_input("模型名称", value=saved_config.get("llm_model", "gpt-3.5-turbo"))
            clean_prompt = st.text_area("清理提示词", value=saved_config.get("clean_prompt", ""), height=150)

            # 保存配置按钮
            if st.button("💾 保存配置", use_container_width=True):
                new_config = {
                    "api_key": api_key,
                    "api_base": api_base,
                    "llm_model": llm_model,
                    "model_size": model_size,
                    "use_llm": use_llm,
                    "auto_save": auto_save,
                    "clean_prompt": clean_prompt
                }
                if save_config(new_config):
                    st.success("✅ 配置已保存！")
        else:
            api_key, api_base, llm_model, clean_prompt = "", "", "", ""

    # 主区域 - 输入
    col_input, col_info = st.columns([2, 1])

    with col_input:
        # 输入方式选择
        input_mode = st.radio("输入方式", ["🔗 链接/路径", "📁 上传文件"], horizontal=True)

        video_inputs = ""

        if input_mode == "🔗 链接/路径":
            st.markdown("支持抖音、小红书、B站等平台链接，每行一个，或直接输入视频URL")

            video_inputs = st.text_area(
                "视频链接/路径",
                height=120,
                placeholder="https://v.douyin.com/xxx/\nC:\\path\\to\\video.mp4"
            )

            # 浏览器辅助下载说明
            with st.expander("💡 抖音视频下载帮助（遇到403错误时使用）"):
                st.markdown("""
                **方法1：一键下载视频+音频（推荐）**
                1. 在浏览器中打开抖音视频链接
                2. 按 F12 打开开发者工具 → 控制台(Console)
                3. 粘贴以下代码并回车，视频和音频会自动下载：

                ```javascript
                (async()=>{const r=performance.getEntriesByType('resource').filter(x=>x.name.includes('zjcdn'));const video=r.find(x=>x.name.includes('media-video'));const audio=r.find(x=>x.name.includes('media-audio'));const dl=async(u,n)=>{const res=await fetch(u);const b=await res.blob();const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=n;document.body.appendChild(a);a.click();};if(video)await dl(video.name,'video.mp4');if(audio)await dl(audio.name,'audio.m4a');alert('下载完成！使用音频文件(audio.m4a)进行识别即可');})();
                ```

                4. 下载完成后，选择"上传文件"，上传 **audio.m4a** 进行识别

                **方法2：书签脚本（更方便）**
                1. 创建新书签，URL填写：
                ```
                javascript:(async()=>{const r=performance.getEntriesByType('resource').filter(x=>x.name.includes('zjcdn'));const v=r.find(x=>x.name.includes('media-audio'))||r.find(x=>x.name.includes('media-video'));if(v){const res=await fetch(v.name);const b=await res.blob();const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=(document.title||'video').split(' ')[0]+'.mp4';a.click();}})();
                ```
                2. 在抖音页面点击书签即可下载
                """)
        else:
            uploaded_files = st.file_uploader(
                "上传视频文件",
                type=['mp4', 'webm', 'mkv', 'avi', 'mov'],
                accept_multiple_files=True
            )

            if uploaded_files:
                # 保存上传的文件到videos目录
                saved_paths = []
                for uploaded_file in uploaded_files:
                    save_path = VIDEOS_DIR / uploaded_file.name
                    with open(save_path, 'wb') as f:
                        f.write(uploaded_file.getbuffer())
                    saved_paths.append(str(save_path))
                video_inputs = '\n'.join(saved_paths)
                st.success(f"已上传 {len(uploaded_files)} 个文件")

    with col_info:
        st.subheader("📊 处理状态")
        status_placeholder = st.empty()
        progress_bar = st.progress(0)

        st.markdown("---")
        st.subheader("📂 文件管理")
        if st.button("🗑️ 清理临时文件", use_container_width=True):
            cleaned = cleanup_video_files()
            if cleaned:
                st.success("临时文件已清理")

        # 显示输出目录内容
        output_files = list(OUTPUT_DIR.glob("*.txt"))
        st.caption(f"已保存文案: {len(output_files)} 个")
        if output_files:
            with st.expander("查看文件列表"):
                for f in sorted(output_files, reverse=True)[:10]:
                    st.text(f.name)

    # 按钮
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
    with col_btn1:
        start_btn = st.button("🚀 开始提取", type="primary", use_container_width=True)
    with col_btn2:
        clear_btn = st.button("🗑️ 清空", use_container_width=True)

    # 结果区域
    results_container = st.container()

    # 处理逻辑
    if start_btn:
        inputs = [line.strip() for line in video_inputs.strip().split('\n') if line.strip()]

        if not inputs:
            st.warning("请输入至少一个视频链接")
        else:
            all_results = []

            for i, video_input in enumerate(inputs):
                status_placeholder.info(f"正在处理 [{i+1}/{len(inputs)}]: {video_input[:40]}...")

                def update_progress(p, msg):
                    progress_bar.progress(int(p * 100))
                    status_placeholder.info(msg)

                result = process_video(
                    video_input, model_size, use_llm,
                    api_key, api_base, llm_model, clean_prompt,
                    update_progress
                )
                result["index"] = i + 1
                all_results.append(result)

                # 自动保存
                if auto_save and result["success"]:
                    filepath = save_caption(result, OUTPUT_DIR, i + 1, use_llm)
                    result["saved_file"] = str(filepath)

            st.session_state["results"] = all_results
            status_placeholder.success(f"✅ 处理完成！共 {len(all_results)} 个视频")

    if clear_btn:
        if "results" in st.session_state:
            del st.session_state["results"]
        progress_bar.progress(0)
        status_placeholder.empty()

    # 显示结果
    if "results" in st.session_state:
        results = st.session_state["results"]

        with results_container:
            st.markdown("---")
            st.subheader("📝 提取结果")

            # 批量下载
            if len(results) > 1:
                all_text = ""
                for r in results:
                    if r.get("success"):
                        all_text += f"=== 视频 {r['index']} ===\n"
                        all_text += f"链接: {r['input']}\n\n"
                        text = r.get("cleaned") or r.get("transcript", "")
                        all_text += f"{text}\n\n{'-'*50}\n\n"

                st.download_button(
                    "📥 下载全部文案",
                    all_text,
                    file_name=f"全部文案_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain"
                )

            # 单个结果
            for result in results:
                status = "✅" if result["success"] else "❌"
                with st.expander(f"{status} 视频 {result['index']}: {result['input'][:50]}...", expanded=True):

                    if result["success"]:
                        # 原文
                        st.markdown("**🎤 语音转文字:**")
                        st.markdown(f'<div class="caption-box">{result.get("transcript", "")}</div>', unsafe_allow_html=True)
                        st.code(result.get("transcript", ""), language=None)

                        # LLM清理结果
                        if result.get("cleaned"):
                            st.markdown("**✨ LLM清理后:**")
                            st.markdown(f'<div class="caption-box" style="background-color:#e8f5e9;">{result["cleaned"]}</div>', unsafe_allow_html=True)
                            st.code(result["cleaned"], language=None)

                        # 保存信息
                        if result.get("saved_file"):
                            st.success(f"📄 已保存: {result['saved_file']}")

                        # 分段字幕
                        if result.get("segments"):
                            with st.expander("📋 分段字幕"):
                                for seg in result["segments"]:
                                    s = f"{int(seg['start']//60):02d}:{int(seg['start']%60):02d}"
                                    e = f"{int(seg['end']//60):02d}:{int(seg['end']%60):02d}"
                                    st.text(f"[{s} - {e}] {seg['text'].strip()}")

                        # 下载按钮
                        st.download_button(
                            "📥 下载此文案",
                            result.get("cleaned") or result.get("transcript", ""),
                            file_name=f"文案_{result['index']}.txt",
                            mime="text/plain",
                            key=f"dl_{result['index']}"
                        )
                    else:
                        st.error(f"处理失败: {result.get('error', '未知错误')}")

    # 页脚
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #888; font-size: 0.9rem;">
        <p>💡 首次使用会下载Whisper模型 | 支持平台：抖音、小红书、B站等 | 语音识别：OpenAI Whisper</p>
        <p>📂 视频临时存放: <code>videos/</code> | 📄 文案输出: <code>output/</code> | ⚙️ 配置: <code>config.json</code></p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
