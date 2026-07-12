import sys
import os
import time
import base64
from pathlib import Path

# 将项目 src 目录加入 Python 搜索路径中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    from mcp_relay_image_analyzer.server import call_gemini_ocr, config
except ImportError as e:
    print(f"Error importing server modules: {e}")
    sys.exit(1)

def main():
    # 验证并读取 config.json 配置
    if not config.validate():
        print("Warning: Configuration is invalid or incomplete. Trying to run anyway...")
        
    print(f"Relay URL: {config.relay_url}")
    print(f"Default Model: {config.default_model}")
    print(f"Timeout: {config.timeout}s")
    print(f"Format: {config.relay_format}")
    print("-" * 50)
    
    if len(sys.argv) < 2:
        print("Usage: python tests/test_ocr_performance.py <path_to_image>")
        sys.exit(1)
        
    image_path = Path(sys.argv[1])
    if not image_path.is_file():
        print(f"Error: File not found at {image_path}")
        sys.exit(1)
        
    try:
        with open(image_path, "rb") as f:
            img_bytes = f.read()
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    except Exception as e:
        print(f"Error reading image: {e}")
        sys.exit(1)
        
    print(f"Starting OCR analysis on: {image_path.name} (Original Size: {len(img_bytes)/1024:.1f} KB)")
    start_time = time.time()
    
    # 检测 MIME 类型
    import mimetypes
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/png"
        
    try:
        result = call_gemini_ocr(img_b64, mime_type)
        elapsed = time.time() - start_time
        print(f"Finished in {elapsed:.2f} seconds!")
        print("-" * 50)
        print("Result:")
        print(result)
    except Exception as e:
        print(f"Error executing OCR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
