import base64
import os
import platform
import subprocess
import mimetypes
import sys
import io
import re
import json
import requests
import threading
import time
import hashlib
import traceback
from pathlib import Path
from PIL import ImageGrab
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from mcp.server.fastmcp import FastMCP

# 强制重配置标准流编码为 UTF-8，防止 Windows 管道重定向中文路径时抛出 UnicodeEncodeError 导致崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from .config import Config

# 初始化 FastMCP 服务
mcp = FastMCP("Relay Image Analyzer")
config = Config()

IS_BACKEND_PROCESS = False

def log_message(message: str):
    print(message, file=sys.stderr, flush=True)
    if globals().get('IS_BACKEND_PROCESS', False):
        port = getattr(config, 'gateway_port', 18449)
        try:
            requests.post(f"http://127.0.0.1:{port}/_log", json={"msg": message}, timeout=0.5)
        except Exception:
            pass

def write_log_with_limit(file_path: Path, new_content: str, max_lines: int = 200):
    """线程安全地写入日志文件，并滚动限制最多保留 max_lines 行数据"""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        if file_path.is_file():
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except Exception:
                pass
        
        new_lines = new_content.splitlines(keepends=True)
        lines.extend(new_lines)
        
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
            
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as e:
        print(f"Error writing to log file {file_path}: {e}", file=sys.stderr)

def _build_final_url(base_url: str, fmt: str) -> str:
    url = base_url.rstrip('/')
    if fmt == "openai":
        if url.endswith("chat/completions"):
            return url
        if "api/v3" in url:
            return f"{url}/chat/completions"
        if "ark.cn-beijing.volces.com" in url:
            return f"{url}/api/v3/chat/completions"
        return f"{url}/v1/chat/completions"
    elif fmt == "anthropic":
        if url.endswith("messages"):
            return url
        if "/api/coding/" in url:
            return f"{url}/messages"
        return f"{url}/v1/messages"
    else:
        return base_url

def _send_multimodal_request(img_base64: str, mime_type: str, prompt: str, target_model: str) -> str:
    """
    发送多模态中继请求，自适应支持 Google v1internal、OpenAI/火山引擎 及 Anthropic 协议。
    """
    fmt = config.relay_format
    headers = {}
    payload = {}
    
    if fmt == "openai":
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": target_model,
            "max_tokens": 800,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{img_base64}"
                            }
                        }
                    ]
                }
            ]
        }
    elif fmt == "anthropic":
        headers = {
            "x-api-key": config.api_key,
            "Authorization": f"Bearer {config.api_key}",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        payload = {
            "model": target_model,
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": img_base64
                            }
                        },
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
        }
    else:
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": target_model,
            "request": {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": prompt},
                            {
                                "inlineData": {
                                    "mimeType": mime_type,
                                    "data": img_base64
                                }
                            }
                        ]
                    }
                ]
            }
        }
        
    url = _build_final_url(config.relay_url, fmt)
    log_message(f"Sending request to relay: {url} using model: {target_model} (Format: {fmt})")
    
    # 记录本服务向第三方中继发送多模态 OCR 分析的请求包
    try:
        def truncate_base64_in_json(val):
            if isinstance(val, dict):
                return {k: truncate_base64_in_json(v) for k, v in val.items()}
            elif isinstance(val, list):
                return [truncate_base64_in_json(x) for x in val]
            elif isinstance(val, str) and len(val) > 200:
                if val.startswith("data:") and ";base64," in val:
                    parts = val.split(";base64,")
                    return f"{parts[0]};base64,{parts[1][:50]}... [truncated, total length: {len(val)}]"
                elif len(val) > 1000 and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in val[:100].strip()):
                    return f"{val[:50]}... [truncated base64, total length: {len(val)}]"
                return val
            return val

        relay_log_file = project_root / "scratch" / "gateway_to_relay.log"
        log_payload = truncate_base64_in_json(payload)
        pretty_relay_body = json.dumps(log_payload, indent=2, ensure_ascii=False)
        
        entry = (
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Sending Multimodal OCR Request to Relay URL: {url}\n"
            f"Request Headers: {headers}\n"
            f"Request Body:\n{pretty_relay_body}\n\n"
        )
        write_log_with_limit(relay_log_file, entry, 200)
    except Exception as e:
        log_message(f"Failed to write relay debug log: {e}")
        
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=config.timeout
        )
    except requests.exceptions.RequestException as e:
        err_msg = (
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: 请求本地中继服务（{url}）失败。异常信息: {e}\n"
            f"{traceback.format_exc()}\n"
        )
        relay_log_file = project_root / "scratch" / "gateway_to_relay.log"
        write_log_with_limit(relay_log_file, err_msg, 200)
        raise RuntimeError(f"请求本地中继服务失败。请确认中继服务（{url}）是否已启动。异常信息: {e}")
        
    if response.status_code != 200:
        err_msg = (
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: 中继服务返回 HTTP 错误码 {response.status_code}。\n"
            f"响应详情: {response.text}\n"
        )
        relay_log_file = project_root / "scratch" / "gateway_to_relay.log"
        write_log_with_limit(relay_log_file, err_msg, 200)
        raise RuntimeError(f"中继服务返回 HTTP 错误码 {response.status_code}。\n响应详情: {response.text}")
        
    try:
        result = response.json()
        if fmt == "openai":
            choices = result.get("choices", [])
            if not choices:
                raise KeyError("choices")
            text = choices[0].get("message", {}).get("content", "")
            if not text:
                raise KeyError("content")
            return text
        elif fmt == "anthropic":
            content_list = result.get("content", [])
            if not content_list:
                raise KeyError("content")
            text = content_list[0].get("text", "")
            if not text:
                raise KeyError("text")
            return text
        else:
            candidates = result.get("response", {}).get("candidates", [])
            if not candidates:
                raise KeyError("candidates")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise KeyError("parts")
            text = parts[0].get("text", "")
            if not text:
                thought = parts[0].get("thoughtSignature", "")
                if thought:
                    return f"[模型思考签名]: {thought}\n(正文未输出内容)"
                return "提示：模型未返回任何文本内容。"
            return text
    except ValueError:
        raise RuntimeError(f"中继服务返回了非 JSON 格式内容。\n原始响应: {response.text}")
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"解析响应 JSON 结构时出错（{e}）。\n原始响应: {response.text}")

@mcp.tool()
def analyze_image(
    image_path: str, 
    prompt: str = "详细分析并描述这张图片的内容，如果其中有文字或代码，请进行 OCR 识别提取并清晰排版。",
    model: str = None
) -> str:
    """
    使用本地多模态中继服务分析本地的图片（支持 PNG、JPEG、WEBP 等常见格式）。
    
    :param image_path: 本地图片文件的绝对路径或相对路径。
    :param prompt: 对图片的分析要求或提问。
    :param model: 调用的多模态模型名称（可选，如 gemini-2.5-flash，不填则使用配置的默认模型）。
    """
    # 验证配置
    if not config.validate():
        return "错误：中继服务 API Key 未配置，请查阅 README 配置 config.json 或设置 RELAY_API_KEY 环境变量。"

    # 解析图片路径
    img_path = Path(image_path)
    if not img_path.is_absolute():
        img_path = Path.cwd() / img_path

    if not img_path.exists():
        return f"错误：找不到图片文件 '{image_path}'。请确保路径正确，如果是相对路径，则其相对于 Claude 的当前运行工作目录。"

    if not img_path.is_file():
        return f"错误：指定的路径 '{image_path}' 不是一个文件。"

    # 识别 MIME 类型
    mime_type, _ = mimetypes.guess_type(img_path)
    if not mime_type:
        # 根据后缀名兜底
        ext = img_path.suffix.lower()
        if ext in ['.png']:
            mime_type = 'image/png'
        elif ext in ['.jpg', '.jpeg']:
            mime_type = 'image/jpeg'
        elif ext in ['.webp']:
            mime_type = 'image/webp'
        elif ext in ['.gif']:
            mime_type = 'image/gif'
        else:
            mime_type = 'application/octet-stream'

    log_message(f"Reading image: {img_path} (MIME: {mime_type})")

    # 读取并进行 Base64 编码与自适应压缩防御
    try:
        try:
            from PIL import Image
            import io
            with Image.open(img_path) as img:
                if img.mode in ('RGBA', 'P', 'LA'):
                    img = img.convert('RGB')
                
                max_size = 1024
                if img.width > max_size or img.height > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                    log_message(f"Image compressed to {img.width}x{img.height}")
                
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85)
                img_data = buffer.getvalue()
                mime_type = 'image/jpeg'
        except ImportError:
            log_message("Pillow not installed, skipping image pre-compression.")
            with open(img_path, "rb") as f:
                img_data = f.read()

        img_base64 = base64.b64encode(img_data).decode("utf-8")
    except Exception as e:
        return f"错误：读取或压缩图片文件失败: {e}"

    # 确定请求的模型
    target_model = model if model else config.default_model

    try:
        return _send_multimodal_request(img_base64, mime_type, prompt, target_model)
    except Exception as e:
        return f"错误：{e}"

@mcp.tool()
def analyze_clipboard_image(
    prompt: str = "详细分析并描述这张图片的内容，如果其中有文字、代码或报错提示，请进行 OCR 识别提取并清晰排版。",
    model: str = None
) -> str:
    """
    使用本地多模态中继服务，分析当前系统剪贴板中的图片（截图）。
    请确保在运行此工具前，已通过截图工具（如 QQ 截图、微信截图或 Snipaste 等）将图片复制到了剪贴板中。
    
    :param prompt: 对图片的分析要求或提问。
    :param model: 调用的多模态模型名称（可选，如 gemini-2.5-flash，不填则使用配置 of 默认模型）。
    """
    # 验证配置
    if not config.validate():
        return "错误：中继服务 API Key 未配置，请配置 config.json 或设置 RELAY_API_KEY 环境变量。"

    print("Grabbing image from clipboard...", file=sys.stderr)
    
    try:
        # 读取剪贴板图片
        img = ImageGrab.grabclipboard()
    except Exception as e:
        return f"错误：访问剪贴板失败，这可能是因为当前环境权限受限。异常信息: {e}"

    if img is None:
        return "错误：当前剪贴板中没有图片。请先使用截图工具进行截图，或将一张图片复制到剪贴板中再试。"

    # 如果复制的是文件（例如在资源管理器中复制了一个 PNG）
    if isinstance(img, list):
        if len(img) > 0:
            from PIL import Image
            try:
                img = Image.open(img[0])
            except Exception as e:
                return f"错误：读取剪贴板中复制的文件 {img[0]} 失败: {e}"
        else:
            return "错误：剪贴板中的文件列表为空。"

    # 将 PIL Image 保存为字节流，并进行 Base64 编码与自适应压缩防御
    try:
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')
            
        max_size = 1024
        if img.width > max_size or img.height > max_size:
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = getattr(Image, 'ANTIALIAS', 1)
            img.thumbnail((max_size, max_size), resample)
            log_message(f"Clipboard image compressed to {img.width}x{img.height}")
            
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        img_bytes = buffered.getvalue()
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")
        mime_type = "image/jpeg"
    except Exception as e:
        return f"错误：处理剪贴板中的图像数据失败: {e}"

    target_model = model if model else config.default_model

    try:
        return _send_multimodal_request(img_base64, mime_type, prompt, target_model)
    except Exception as e:
        return f"错误：{e}"

def call_gemini_ocr(base64_data: str, mime_type: str) -> str:
    """内部辅助函数：将图片 Base64 发往中继的多模态接口提取文本（内含大图自适应本地压缩）"""
    # 验证配置
    if not config.validate():
        return "\n\n[本地中继自动分析图片失败：API Key 未配置]\n"

    # ── 大图本地自适应缩放（防止网络传输/推理超时）────────────────
    try:
        from PIL import Image
        import io
        img_bytes = base64.b64decode(base64_data)
        with Image.open(io.BytesIO(img_bytes)) as img:
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')
            
            # 自适应限制最大尺寸为 768px
            max_size = 768
            if img.width > max_size or img.height > max_size:
                try:
                    resample = Image.Resampling.LANCZOS
                except AttributeError:
                    resample = getattr(Image, 'ANTIALIAS', 1)
                img.thumbnail((max_size, max_size), resample)
                log_message(f"Gateway image auto-compressed to {img.width}x{img.height}")
                
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=80)
                base64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
                mime_type = "image/jpeg"
    except Exception as e:
        log_message(f"Gateway image auto-compression failed: {e}")

    prompt = "请详细分析并描述这张图片的内容，如果其中有文字、代码或报错提示，请进行 OCR 识别提取并清晰排版。直接输出图片分析结果即可，不要输出任何引言 and 前言解释。"

    try:
        text = _send_multimodal_request(base64_data, mime_type, prompt, config.default_model)
        return f"\n\n[本地中继服务已自动调用 {config.default_model} 协助分析了用户发送的截图，内容提取如下：]\n{text}\n[图片分析内容结束]\n"
    except Exception as e:
        print(f"Error calling OCR inside fallback gateway: {e}", file=sys.stderr)
        return f"\n\n[本地中继服务自动分析图片出错：{e}]\n"

# 缓存机制：持久化保存图片分析结果至本地 JSON，避免多轮对话时反复调用多模态接口
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
CACHE_FILE = Path.home() / ".mcp-relay-image-analyzer" / "image_analysis_cache.json"

_cache_data = {}
_cache_lock = threading.Lock()

def load_cache():
    global _cache_data
    if CACHE_FILE.is_file():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _cache_data = json.load(f)
            print(f"Loaded {len(_cache_data)} cached image analyses.", file=sys.stderr)
        except Exception as e:
            print(f"Error loading image cache: {e}", file=sys.stderr)
            _cache_data = {}

def save_cache():
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_cache_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving image cache: {e}", file=sys.stderr)

def get_cached_analysis(key: str) -> str:
    with _cache_lock:
        return _cache_data.get(key)

def set_cached_analysis(key: str, val: str):
    with _cache_lock:
        _cache_data[key] = val
    save_cache()

def is_valid_analysis_result(desc: str) -> bool:
    """检查识别结果是否有效，若包含失败、错误或未配置等关键词则不予缓存"""
    if not desc:
        return False
    error_keywords = ["失败", "未配置", "错误", "出错", "timeout", "timed out"]
    return not any(kw in desc for kw in error_keywords)

# 匹配 Windows 绝对路径图片（支持正反斜杠以及常见格式：png, jpg, jpeg, webp, gif）
IMAGE_PATH_PATTERN = re.compile(r'([a-zA-Z]:[\\/][^:?*"<>|\r\n]+\.(?:png|jpg|jpeg|webp|gif))', re.IGNORECASE)

def process_text_paths(text_content: str) -> str:
    """辅助函数：正则匹配文本中的本地绝对路径，自动读取图片文件转 Base64 并调用多模态转换为描述文本"""
    if not isinstance(text_content, str):
        return text_content

    matches = IMAGE_PATH_PATTERN.findall(text_content)
    if not matches:
        return text_content

    new_text = text_content
    for match in matches:
        img_path = Path(match)
        if img_path.is_file():
            try:
                # 读取并进行 Base64 编码
                with open(img_path, "rb") as f:
                    img_base64 = base64.b64encode(f.read()).decode("utf-8")
                
                # 识别 MIME 类型
                mime_type, _ = mimetypes.guess_type(img_path)
                if not mime_type:
                    mime_type = "image/png"

                # 使用 MD5 作为缓存 Key
                md5_key = f"b64:{hashlib.md5(img_base64.encode('utf-8')).hexdigest()}"
                cached_desc = get_cached_analysis(md5_key)
                if cached_desc:
                    print(f"Found cached OCR for local path image: {img_path}", file=sys.stderr, flush=True)
                    ocr_desc = cached_desc
                else:
                    print(f"Intercepted local image path, executing OCR: {img_path}", file=sys.stderr, flush=True)
                    ocr_desc = call_gemini_ocr(img_base64, mime_type)
                    if is_valid_analysis_result(ocr_desc):
                        set_cached_analysis(md5_key, ocr_desc)
                
                # 替换原本的绝对路径为大模型的 OCR 描述结果
                replacement = f"\n\n[本地网关已自动读取本地路径图片 {img_path} 并分析，内容提取如下：]\n{ocr_desc}\n"
                new_text = new_text.replace(match, replacement)
            except Exception as e:
                print(f"Failed to process text image path {img_path}: {e}", file=sys.stderr)

    return new_text

def process_multimodal_request(data: dict) -> dict:
    """自动过滤并翻译请求体中多模态内容（包含原生 Base64 和绝对路径文本）为纯文本的辅助函数"""
    messages = data.get("messages", [])
    if not isinstance(messages, list):
        return data

    for m in messages:
        content = m.get("content")
        # 1. 块列表格式多模态处理
        if isinstance(content, list):
            new_content = []
            for part in content:
                if not isinstance(part, dict):
                    new_content.append(part)
                    continue

                part_type = part.get("type")

                # 如果是文本块，检测其内部是否含有图片绝对路径并重写
                if part_type == "text":
                    original_text = part.get("text", "")
                    part["text"] = process_text_paths(original_text)
                    new_content.append(part)

                # 识别并过滤 Anthropic 格式的 image
                elif part_type == "image":
                    source = part.get("source", {})
                    base64_data = source.get("data", "")
                    media_type = source.get("media_type", "image/png")

                    if base64_data:
                        # 用 MD5 作为缓存 Key
                        md5_key = f"b64:{hashlib.md5(base64_data.encode('utf-8')).hexdigest()}"
                        cached_desc = get_cached_analysis(md5_key)
                        if cached_desc:
                            print("Found cached OCR for Anthropic image", file=sys.stderr, flush=True)
                            ocr_desc = cached_desc
                        else:
                            print("Intercepted Anthropic image in gateway, executing OCR...", file=sys.stderr, flush=True)
                            ocr_desc = call_gemini_ocr(base64_data, media_type)
                            if is_valid_analysis_result(ocr_desc):
                                set_cached_analysis(md5_key, ocr_desc)

                        new_content.append({
                            "type": "text",
                            "text": ocr_desc
                        })
                    else:
                        new_content.append(part)

                # 识别并过滤 OpenAI 格式的 image_url
                elif part_type == "image_url":
                    image_url = part.get("image_url", {})
                    url = image_url.get("url", "")

                    if url.startswith("data:"):
                        try:
                            header, base64_data = url.split(";base64,")
                            media_type = header.replace("data:", "")

                            md5_key = f"b64:{hashlib.md5(base64_data.encode('utf-8')).hexdigest()}"
                            cached_desc = get_cached_analysis(md5_key)
                            if cached_desc:
                                print("Found cached OCR for OpenAI image_url", file=sys.stderr, flush=True)
                                ocr_desc = cached_desc
                            else:
                                print("Intercepted OpenAI image_url in gateway, executing OCR...", file=sys.stderr, flush=True)
                                ocr_desc = call_gemini_ocr(base64_data, media_type)
                                if is_valid_analysis_result(ocr_desc):
                                    set_cached_analysis(md5_key, ocr_desc)

                            new_content.append({
                                "type": "text",
                                "text": ocr_desc
                            })
                        except Exception as e:
                            print(f"Failed to parse data URL: {e}", file=sys.stderr)
                            new_content.append(part)
                    else:
                        new_content.append(part)
                else:
                    new_content.append(part)
            m["content"] = new_content
        # 2. 纯字符串文本多模态处理
        elif isinstance(content, str):
            m["content"] = process_text_paths(content)

    return data

def run_gateway():
    """多模态降级中继代理网关线程函数"""
    load_cache()
    class GatewayHandler(BaseHTTPRequestHandler):
        # 强制将日志输出至 stderr，切勿输出至 stdout 破坏 MCP 协议
        def log_message(self, format, *args):
            print(format % args, file=sys.stderr)

        def do_POST(self):
            if self.path == "/_log":
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                try:
                    msg = json.loads(body.decode('utf-8')).get("msg", "")
                    print(f" -> [Backend MCP Server Log] {msg}", file=sys.stderr, flush=True)
                except Exception:
                    pass
                self.send_response(200)
                self.end_headers()
                return

            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)

            # 调试：写日志记录网关是否被触发以及打印请求体
            try:
                def truncate_base64_in_json(val):
                    if isinstance(val, dict):
                        return {k: truncate_base64_in_json(v) for k, v in val.items()}
                    elif isinstance(val, list):
                        return [truncate_base64_in_json(x) for x in val]
                    elif isinstance(val, str) and len(val) > 200:
                        if val.startswith("data:") and ";base64," in val:
                            parts = val.split(";base64,")
                            return f"{parts[0]};base64,{parts[1][:50]}... [truncated, total length: {len(val)}]"
                        elif len(val) > 1000 and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in val[:100].strip()):
                            return f"{val[:50]}... [truncated base64, total length: {len(val)}]"
                        return val
                    return val

                body_str = body.decode('utf-8', errors='ignore')
                try:
                    body_json = json.loads(body_str)
                    log_json = truncate_base64_in_json(body_json)
                    pretty_body = json.dumps(log_json, indent=2, ensure_ascii=False)
                except Exception:
                    pretty_body = body_str

                # 输出至 stderr，以便在 claude code 运行终端直接看到
                print(f"\n--- [Gateway POST Request] path: {self.path} ---\n{pretty_body}\n-----------------------------------\n", file=sys.stderr, flush=True)
                print(f" -> Client x-api-key: {self.headers.get('x-api-key')}", file=sys.stderr, flush=True)
                print(f" -> Client Authorization: {self.headers.get('Authorization')}", file=sys.stderr, flush=True)

                entry = (
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Received POST request on path: {self.path}\n"
                    f"Headers: {dict(self.headers)}\n"
                    f"Request Body:\n{pretty_body}\n\n"
                )
                log_file = project_root / "scratch" / "claude_to_gateway.log"
                write_log_with_limit(log_file, entry, 200)
            except Exception as e:
                print(f"Failed to write gateway debug log: {e}", file=sys.stderr)

            # 解析并翻译多模态请求包为纯文本
            try:
                data = json.loads(body.decode('utf-8'))
                data = process_multimodal_request(data)
                modified_body = json.dumps(data).encode('utf-8')
            except Exception as e:
                print(f"Error filtering body in gateway: {e}", file=sys.stderr)
                modified_body = body

            # 准备请求头部
            headers_to_send = {k: v for k, v in self.headers.items() if k.lower() != 'host'}
            headers_to_send['Content-Length'] = str(len(modified_body))

            # 提取目标地址并转发给原生中继服务
            upstream_base = config.upstream_base_url.rstrip('/')
            target_url = f"{upstream_base}{self.path}"
            print(f"Gateway forwarding request to: {target_url}", file=sys.stderr, flush=True)

            try:
                # 采用流式（stream=True）处理转发，保留打字机式 SSE 回复体验
                resp = requests.post(
                    target_url,
                    headers=headers_to_send,
                    data=modified_body,
                    stream=True
                )

                self.send_response(resp.status_code)
                for k, v in resp.headers.items():
                    if k.lower() not in ['transfer-encoding', 'content-encoding', 'content-length']:
                        self.send_header(k, v)
                self.end_headers()

                # 处理并原样回传数据
                if resp.status_code != 200:
                    err_content = resp.content
                    print(f"--- [Upstream Error Response] status: {resp.status_code} ---\n{err_content.decode('utf-8', errors='ignore')}\n---------------------------------------\n", file=sys.stderr, flush=True)
                    self.wfile.write(err_content)
                    self.wfile.flush()
                else:
                    for chunk in resp.iter_content(chunk_size=4096):
                        if chunk:
                            self.wfile.write(chunk)
                            self.wfile.flush()
            except Exception as e:
                err_msg = (
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR in do_POST: {e}\n"
                    f"{traceback.format_exc()}\n"
                )
                print(err_msg, file=sys.stderr, flush=True)
                log_file = project_root / "scratch" / "claude_to_gateway.log"
                write_log_with_limit(log_file, err_msg, 200)
                try:
                    self.send_error(502, f"Gateway proxy error: {e}")
                except Exception:
                    pass

        # 同样需要代理 GET 请求（如 /v1/models）
        def do_GET(self):
            # 记录 GET 请求日志
            try:
                entry = (
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Received GET request on path: {self.path}\n"
                    f"Headers: {dict(self.headers)}\n\n"
                )
                log_file = project_root / "scratch" / "claude_to_gateway.log"
                write_log_with_limit(log_file, entry, 200)
            except Exception as e:
                print(f"Failed to write gateway GET debug log: {e}", file=sys.stderr)

            headers_to_send = {k: v for k, v in self.headers.items() if k.lower() != 'host'}
            upstream_base = config.upstream_base_url.rstrip('/')
            target_url = f"{upstream_base}{self.path}"
            try:
                resp = requests.get(target_url, headers=headers_to_send)
                self.send_response(resp.status_code)
                for k, v in resp.headers.items():
                    if k.lower() not in ['transfer-encoding', 'content-encoding', 'content-length']:
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.content)
                self.wfile.flush()
            except Exception as e:
                err_msg = (
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR in do_GET: {e}\n"
                    f"{traceback.format_exc()}\n"
                )
                print(err_msg, file=sys.stderr, flush=True)
                log_file = project_root / "scratch" / "claude_to_gateway.log"
                write_log_with_limit(log_file, err_msg, 200)
                try:
                    self.send_error(502, f"Gateway GET proxy error: {e}")
                except Exception:
                    pass

    # 使用配置的端口启动重写网关（ThreadingHTTPServer：每个请求独立线程，OCR 不阻塞并发请求）
    port = getattr(config, 'gateway_port', 18449)
    try:
        server = ThreadingHTTPServer(('127.0.0.1', port), GatewayHandler)
        server.daemon_threads = True  # 子线程随主进程退出，不阻止关闭
        print(f"MCP Multimodal Gateway (Threaded) running on http://127.0.0.1:{port}", file=sys.stderr)
        server.serve_forever()
    except Exception as e:
        globals()['IS_BACKEND_PROCESS'] = True
        print(f"[Port in use] Gateway port {port} is already bound, gracefully reusing external gateway process. (Error: {e})", file=sys.stderr)
        try:
            requests.post(f"http://127.0.0.1:{port}/_log", json={"msg": "MCP Server standard I/O channel established. Connected to Claude!"}, timeout=0.5)
        except Exception:
            pass

def setup_system_env():
    """检测当前平台，若是 Windows 且未配置代理基址环境变量，则自动使用 setx 写入用户环境变量"""
    if platform.system() == "Windows":
        target_url = "http://127.0.0.1:18449"
        if os.getenv("ANTHROPIC_BASE_URL") != target_url:
            try:
                # setx 会静默写入注册表 HKCU\Environment 中，对之后打开的所有新终端生效
                subprocess.run(
                    ["setx", "ANTHROPIC_BASE_URL", target_url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print("MCP gateway automatically configured ANTHROPIC_BASE_URL in Windows system env.", file=sys.stderr)
            except Exception as e:
                print(f"Failed to auto-set system env variable ANTHROPIC_BASE_URL: {e}", file=sys.stderr)

def main():
    """入口函数，供 pyproject.toml 脚本入口直接运行"""
    # 自动设置系统级环境变量 (已完成历史使命，注释掉以防 stdio 挂起)
    # setup_system_env()

    # 启动后台拦截网关
    gateway_thread = threading.Thread(target=run_gateway, daemon=True)
    gateway_thread.start()

    # 启动原本的 MCP stdio 服务
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
