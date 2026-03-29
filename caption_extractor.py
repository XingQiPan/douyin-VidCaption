# -*- coding: utf-8 -*-
"""
视频文案提取器 - 命令行版本
用于 Claude Code Skill 调用

用法:
    python caption_extractor.py <视频链接或文件路径> [--model base] [--no-llm] [--output output.txt]

示例:
    python caption_extractor.py "https://v.douyin.com/xxx/"
    python caption_extractor.py "C:/path/to/video.mp4" --model small
    python caption_extractor.py "https://v.douyin.com/xxx/" --no-llm --output result.txt
"""

import os
import re
import sys
import json
import shutil
import argparse
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# 警告过滤
warnings.filterwarnings('ignore')

# ==================== 配置 ====================
BASE_DIR = Path(__file__).parent
VIDEOS_DIR = BASE_DIR / "videos"
OUTPUT_DIR = BASE_DIR / "output"
CONFIG_FILE = BASE_DIR / "config.json"

# 确保目录存在
VIDEOS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


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
        print(f"ERROR: ffmpeg设置失败: {e}", file=sys.stderr)
        return False


# ==================== B站字幕提取 ====================
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52
]


def get_mixin_key(orig: str) -> str:
    """生成WBI签名用的mixin key"""
    return ''.join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def sign_wbi(params: dict, img_key: str, sub_key: str) -> dict:
    """对请求参数进行WBI签名"""
    import time
    import urllib.parse
    import hashlib

    mixin_key = get_mixin_key(img_key + sub_key)
    params['wts'] = round(time.time())
    params = {
        k: ''.join(c for c in str(v) if c not in "!'()*")
        for k, v in sorted(params.items())
    }
    query = urllib.parse.urlencode(params)
    params['w_rid'] = hashlib.md5(f'{query}{mixin_key}'.encode()).hexdigest()
    return params


def get_wbi_keys() -> tuple:
    """获取WBI签名密钥 (img_key, sub_key)"""
    import requests

    resp = requests.get('https://api.bilibili.com/x/web-interface/nav', timeout=10)
    data = resp.json().get('data', {}).get('wbi_img', {})
    img_url = data.get('img_url', '')
    sub_url = data.get('sub_url', '')
    img_key = img_url.split('/')[-1].split('.')[0]
    sub_key = sub_url.split('/')[-1].split('.')[0]
    return img_key, sub_key


def extract_bilibili_subtitle(url: str, sessdata: str = "") -> Optional[Dict[str, Any]]:
    """从B站视频提取字幕文本"""
    import requests

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com',
    }
    if sessdata:
        headers['Cookie'] = f'SESSDATA={sessdata}'

    # 解析BV号
    bv_match = re.search(r'(BV[\w]+)', url)
    if not bv_match:
        return None
    bvid = bv_match.group(1)

    # 解析多P参数
    page = 1
    p_match = re.search(r'[?&]p=(\d+)', url)
    if p_match:
        page = int(p_match.group(1))

    print(f"INFO: B站视频 BV号={bvid}, P={page}")

    # 获取视频信息（标题、CID等）
    try:
        info_resp = requests.get(
            'https://api.bilibili.com/x/web-interface/view',
            params={'bvid': bvid}, headers=headers, timeout=10
        )
        info_data = info_resp.json()
        if info_data.get('code') != 0:
            print(f"ERROR: 获取视频信息失败: {info_data.get('message', '')}", file=sys.stderr)
            return None

        video_info = info_data['data']
        title = video_info.get('title', '')
        print(f"INFO: 视频标题: {title}")

        # 获取对应P的cid
        pages = video_info.get('pages', [])
        if pages:
            cid = None
            for p in pages:
                if p.get('page') == page:
                    cid = p.get('cid')
                    break
            if cid is None:
                cid = pages[0].get('cid')
        else:
            cid = video_info.get('cid')
    except Exception as e:
        print(f"ERROR: 获取视频信息失败: {e}", file=sys.stderr)
        return None

    if not cid:
        print("ERROR: 无法获取CID", file=sys.stderr)
        return None

    # 获取WBI密钥并签名
    try:
        img_key, sub_key = get_wbi_keys()
        params = sign_wbi({'bvid': bvid, 'cid': cid}, img_key, sub_key)

        subtitle_resp = requests.get(
            'https://api.bilibili.com/x/player/wbi/v2',
            params=params, headers=headers, timeout=10
        )
        subtitle_data = subtitle_resp.json()
    except Exception as e:
        print(f"ERROR: 获取字幕信息失败: {e}", file=sys.stderr)
        return None

    subtitles = subtitle_data.get('data', {}).get('subtitle', {}).get('subtitles', [])

    if not subtitles:
        print("INFO: 该视频无CC/AI字幕，将使用语音识别")
        return None

    # 优先选择中文字幕
    target = None
    for sub in subtitles:
        if sub.get('lan', '').startswith('zh'):
            target = sub
            break
    if not target:
        target = subtitles[0]

    subtitle_url = target.get('subtitle_url', '')
    if subtitle_url.startswith('//'):
        subtitle_url = 'https:' + subtitle_url

    # 下载字幕内容
    try:
        sub_resp = requests.get(subtitle_url, headers=headers, timeout=10)
        sub_json = sub_resp.json()
    except Exception as e:
        print(f"ERROR: 下载字幕失败: {e}", file=sys.stderr)
        return None

    body = sub_json.get('body', [])
    if not body:
        return None

    # 拼接字幕文本
    full_text = '\n'.join(item.get('content', '') for item in body)
    # 生成带时间戳的分段信息（兼容Whisper的segments格式）
    segments = []
    for item in body:
        segments.append({
            'start': item.get('from', 0),
            'end': item.get('to', 0),
            'text': item.get('content', '')
        })

    print(f"INFO: 成功提取B站字幕，共 {len(body)} 条")
    return {
        "success": True,
        "text": full_text,
        "segments": segments,
        "title": title,
        "source": "bilibili_subtitle"
    }


def extract_video_url(video_input: str) -> Optional[str]:
    """从链接提取视频下载URL"""
    import requests

    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.douyin.com/'
    }

    def decode_url(url):
        if not url:
            return url
        import codecs
        try:
            url = codecs.decode(url, 'unicode_escape')
        except:
            pass
        url = url.replace('\\/', '/')
        if url.startswith('//'):
            url = 'https:' + url
        return url

    try:
        if video_input.endswith(('.mp4', '.webm', '.mkv', '.m3u8')):
            return video_input

        if 'v.douyin.com' in video_input or 'douyin.com' in video_input or 'iesdouyin.com' in video_input:
            print("INFO: 正在解析抖音链接...")

            try:
                resp = requests.get(video_input, headers=headers, allow_redirects=True, timeout=15)
                final_url = resp.url
                page_content = resp.text
            except Exception as e:
                print(f"ERROR: 获取页面失败: {e}", file=sys.stderr)
                return None

            aweme_id_match = re.search(r'/video/(\d+)', final_url)
            if not aweme_id_match:
                aweme_id_match = re.search(r'aweme_id[=:]["\']?(\d+)', page_content)

            if aweme_id_match:
                aweme_id = aweme_id_match.group(1)
                share_url = f'https://www.iesdouyin.com/share/video/{aweme_id}/'
                try:
                    share_resp = requests.get(share_url, headers=headers, timeout=15)
                    page_content = share_resp.text
                except:
                    pass

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
                        url = url.replace('/playwm/', '/play/')
                        print("INFO: 成功提取视频URL")
                        return url

            aweme_pattern = r'(https?://aweme\.snssdk\.com/[^"\'>\s]+)'
            matches = re.findall(aweme_pattern, page_content)
            if matches:
                url = decode_url(matches[0])
                url = url.replace('/playwm/', '/play/')
                print("INFO: 成功提取视频URL (备用模式)")
                return url

            print("ERROR: 无法从页面提取视频URL", file=sys.stderr)
            return None

        return None

    except Exception as e:
        print(f"ERROR: 提取视频URL失败: {e}", file=sys.stderr)
        return None


def download_video_with_ytdlp(url: str, output_path: str, audio_only: bool = False) -> bool:
    """使用yt-dlp下载视频"""
    try:
        import yt_dlp
        import glob

        output_dir = os.path.dirname(output_path)
        base_name = os.path.basename(output_path).replace('.mp4', '')

        if audio_only:
            fmt = 'bestaudio/best'
        else:
            fmt = 'best[ext=mp4]/best'

        ydl_opts = {
            'outtmpl': os.path.join(output_dir, base_name),
            'format': fmt,
            'quiet': True,
            'no_warnings': True,
            'extract_audio': False,
            'noplaylist': True,
            'merge_output_format': 'mp4',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        pattern = os.path.join(output_dir, base_name + '*')
        files = glob.glob(pattern)
        for f in files:
            if f.endswith('.part'):
                continue
            if not f.endswith(('.mp4', '.m4a', '.webm', '.mkv', '.mp3', '.ogg', '.wav')):
                os.rename(f, f + '.mp4')
                return True
            else:
                return True

        return False
    except ImportError:
        return False
    except Exception as e:
        print(f"WARN: yt-dlp下载失败: {e}", file=sys.stderr)
        return False


def download_video(url: str, output_path: str) -> bool:
    """下载视频"""
    import requests

    if download_video_with_ytdlp(url, output_path):
        return True

    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148',
        'Accept': '*/*',
        'Accept-Encoding': 'identity',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.douyin.com/',
        'Connection': 'keep-alive',
    }

    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=30, allow_redirects=True)

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
        print(f"ERROR: 下载失败: {e}", file=sys.stderr)
        return False


def transcribe_video(video_path: str, model_size: str = "base") -> Dict[str, Any]:
    """使用Whisper进行语音识别"""
    import whisper

    if not setup_ffmpeg():
        return {"success": False, "error": "ffmpeg设置失败"}

    try:
        print(f"INFO: 加载Whisper模型 ({model_size})...")
        model = whisper.load_model(model_size)
        print("INFO: 正在进行语音识别...")
        result = model.transcribe(video_path, language='zh')
        return {
            "success": True,
            "text": result.get('text', ''),
            "segments": result.get('segments', [])
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def clean_with_llm(text: str, api_key: str, api_base: str, model: str, prompt_template: str) -> Dict[str, Any]:
    """使用大语言模型清理文案"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=api_base)
        prompt = prompt_template.format(text=text)

        print(f"INFO: 正在使用LLM清理文案 ({model})...")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个专业的文案编辑助手，擅长整理和优化文字内容。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        cleaned_text = response.choices[0].message.content

        title = None
        title_match = re.search(r'【标题】(.+?)(?:\n|$)', cleaned_text)
        if title_match:
            title = title_match.group(1).strip()
        else:
            first_line = cleaned_text.strip().split('\n')[0]
            if len(first_line) < 50:
                title = first_line

        return {"success": True, "text": cleaned_text, "title": title}
    except Exception as e:
        return {"success": False, "text": f"LLM清理失败: {e}", "title": None}


def sanitize_filename(name: str) -> str:
    """清理文件名"""
    illegal_chars = r'[<>:"/\\|?*]'
    name = re.sub(illegal_chars, '', name)
    name = name.strip('. ')
    if len(name) > 50:
        name = name[:50]
    return name if name else "未命名"


def process_video(video_input: str, model_size: str = "base", use_llm: bool = True,
                  output_file: str = None) -> Dict[str, Any]:
    """处理视频并提取文案"""

    config = load_config()

    if not use_llm:
        config["use_llm"] = False

    result = {
        "input": video_input,
        "timestamp": datetime.now().isoformat(),
        "success": False
    }

    video_path = None
    is_temp_video = False

    try:
        is_url = video_input.startswith('http://') or video_input.startswith('https://')
        is_bilibili = is_url and ('bilibili.com' in video_input or 'b23.tv' in video_input)

        if is_bilibili:
            print(f"INFO: 处理B站链接: {video_input}")

            # 优先尝试直接提取字幕
            sessdata = config.get("bilibili_sessdata", "")
            subtitle_result = extract_bilibili_subtitle(video_input, sessdata)

            if subtitle_result and subtitle_result.get("success"):
                result["transcript"] = subtitle_result["text"]
                result["segments"] = subtitle_result["segments"]
                result["success"] = True
                result["source"] = "bilibili_subtitle"
                if subtitle_result.get("title"):
                    result["bilibili_title"] = subtitle_result["title"]
                print("INFO: 通过B站字幕API提取成功")
            else:
                # 回退到yt-dlp下载 + Whisper
                print("INFO: 回退到下载视频+语音识别模式...")
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                video_path = VIDEOS_DIR / f"{timestamp}.mp4"
                is_temp_video = True

                if download_video_with_ytdlp(video_input, str(video_path), audio_only=True):
                    print("INFO: 视频下载完成，开始语音识别")
                    transcript_result = transcribe_video(str(video_path), model_size)
                    if transcript_result["success"]:
                        result["transcript"] = transcript_result["text"]
                        result["segments"] = transcript_result["segments"]
                        result["success"] = True
                        result["source"] = "whisper"
                    else:
                        result["error"] = transcript_result.get("error", "语音识别失败")
                        return result
                else:
                    result["error"] = "B站视频下载失败，请检查yt-dlp是否安装且为最新版本"
                    return result

        elif is_url:
            print(f"INFO: 处理URL: {video_input}")

            video_url = extract_video_url(video_input)
            if not video_url:
                result["error"] = "无法提取视频URL"
                return result

            print("INFO: 正在下载视频...")
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            video_path = VIDEOS_DIR / f"{timestamp}.mp4"
            is_temp_video = True

            if not download_video(video_url, str(video_path)):
                result["error"] = "视频下载失败"
                return result
            print("INFO: 视频下载完成")

            # 语音识别
            transcript_result = transcribe_video(str(video_path), model_size)
            if not transcript_result["success"]:
                result["error"] = transcript_result.get("error", "语音识别失败")
                return result

            result["transcript"] = transcript_result["text"]
            result["segments"] = transcript_result["segments"]
            result["success"] = True
        else:
            video_path = Path(video_input)
            if not video_path.exists():
                result["error"] = f"文件不存在: {video_input}"
                return result

            # 语音识别
            transcript_result = transcribe_video(str(video_path), model_size)
            if not transcript_result["success"]:
                result["error"] = transcript_result.get("error", "语音识别失败")
                return result

            result["transcript"] = transcript_result["text"]
            result["segments"] = transcript_result["segments"]
            result["success"] = True

        # LLM清理
        if config.get("use_llm") and config.get("api_key"):
            llm_result = clean_with_llm(
                result["transcript"],
                config["api_key"],
                config["api_base"],
                config["llm_model"],
                config["clean_prompt"]
            )
            result["cleaned"] = llm_result["text"]
            if llm_result.get("title"):
                result["cleaned_title"] = llm_result["title"]

        # 保存结果
        if output_file or config.get("auto_save"):
            if output_file:
                filepath = Path(output_file)
            else:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                title = result.get("cleaned_title") or result.get("bilibili_title") or result["transcript"][:30]
                safe_title = sanitize_filename(title)
                filepath = OUTPUT_DIR / f"{timestamp}_{safe_title}.txt"

            content = f"视频文案提取结果\n"
            content += f"{'='*60}\n"
            content += f"时间: {result['timestamp']}\n"
            content += f"来源: {result['input']}\n"
            content += f"{'='*60}\n\n"

            if result.get("cleaned"):
                content += f"{result['cleaned']}\n"
            else:
                content += f"{result['transcript']}\n"

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            result["saved_file"] = str(filepath)
            print(f"INFO: 文案已保存到: {filepath}")

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
    parser = argparse.ArgumentParser(
        description='视频文案提取器 - 从视频中提取语音文字（支持抖音、B站）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "https://v.douyin.com/xxx/"
  %(prog)s "https://www.bilibili.com/video/BV1Jsw1zDE8u/"
  %(prog)s "C:/path/to/video.mp4" --model small
  %(prog)s "https://v.douyin.com/xxx/" --no-llm --output result.txt
        """
    )

    parser.add_argument('input', help='视频链接或本地文件路径')
    parser.add_argument('--model', '-m', default='base',
                        choices=['tiny', 'base', 'small', 'medium', 'large'],
                        help='Whisper模型大小 (default: base)')
    parser.add_argument('--no-llm', action='store_true',
                        help='禁用LLM清理')
    parser.add_argument('--output', '-o', default=None,
                        help='输出文件路径')
    parser.add_argument('--json', action='store_true',
                        help='以JSON格式输出结果')

    args = parser.parse_args()

    result = process_video(
        video_input=args.input,
        model_size=args.model,
        use_llm=not args.no_llm,
        output_file=args.output
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            print("\n" + "="*60)
            print("提取结果:")
            print("="*60)
            if result.get("cleaned"):
                print(result["cleaned"])
            else:
                print(result["transcript"])
            print("="*60)
            if result.get("saved_file"):
                print(f"已保存到: {result['saved_file']}")
        else:
            print(f"ERROR: {result.get('error', '未知错误')}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
