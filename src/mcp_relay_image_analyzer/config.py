import os
import json
import sys
from pathlib import Path

DEFAULT_RELAY_URL = "http://127.0.0.1:18444/v1internal:generateContent"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_FORMAT = "google"

class Config:
    def __init__(self):
        # ── Step 1: 硬编码默认值 ──────────────────────────────────────────
        self.relay_url = DEFAULT_RELAY_URL
        self.api_key = ""
        self.default_model = DEFAULT_MODEL
        self.timeout = 180
        self.upstream_base_url = "http://127.0.0.1:18444"
        self.relay_format = DEFAULT_FORMAT
        self.gateway_port = 18449

        # ── Step 2: 读取 config.json（覆盖默认值）────────────────────────
        self._load_from_file()

        # ── Step 3: 环境变量最高优先级（覆盖文件值）──────────────────────
        if os.getenv("RELAY_URL"):
            self.relay_url = os.getenv("RELAY_URL")
        if os.getenv("RELAY_API_KEY"):
            self.api_key = os.getenv("RELAY_API_KEY")
        if os.getenv("RELAY_MODEL"):
            self.default_model = os.getenv("RELAY_MODEL")
        if os.getenv("RELAY_TIMEOUT"):
            self.timeout = int(os.getenv("RELAY_TIMEOUT"))
        if os.getenv("UPSTREAM_BASE_URL"):
            self.upstream_base_url = os.getenv("UPSTREAM_BASE_URL")
        if os.getenv("RELAY_FORMAT"):
            self.relay_format = os.getenv("RELAY_FORMAT").strip().lower()
        if os.getenv("GATEWAY_PORT"):
            self.gateway_port = int(os.getenv("GATEWAY_PORT"))

    def _load_from_file(self):
        # 寻找 config.json 的候选路径
        # 1. 环境变量指定的路径
        # 2. 当前工作目录下的 config.json
        # 3. 脚本所在目录的上一级（项目根目录）下的 config.json
        # 4. 用户主目录下的 .mcp-relay-image-analyzer/config.json
        
        candidates = []
        
        env_config_path = os.getenv("MCP_IMAGE_ANALYZER_CONFIG")
        if env_config_path:
            candidates.append(Path(env_config_path))
            
        candidates.append(Path.cwd() / "config.json")
        
        script_dir = Path(__file__).resolve().parent
        candidates.append(script_dir.parent.parent / "config.json")
        candidates.append(script_dir.parent.parent.parent / "config.json") # 兼容各种部署目录
        
        candidates.append(Path.home() / ".mcp-relay-image-analyzer" / "config.json")

        for path in candidates:
            if path.is_file():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.relay_url = data.get("relay_url", self.relay_url)
                        self.api_key = data.get("api_key", self.api_key)
                        self.default_model = data.get("default_model", self.default_model)
                        self.timeout = data.get("timeout", self.timeout)
                        self.upstream_base_url = data.get("upstream_base_url", self.upstream_base_url)
                        self.relay_format = data.get("relay_format", self.relay_format).strip().lower()
                        self.gateway_port = data.get("gateway_port", self.gateway_port)
                        
                        # 只要成功加载了一个存在的 config.json，就打印日志到 stderr 并返回
                        print(f"Loaded config from: {path}", file=sys.stderr)
                        return
                except Exception as e:
                    print(f"Error reading config file {path}: {e}", file=sys.stderr)

    def validate(self):
        if not self.api_key:
            print(
                "Warning: RELAY_API_KEY is not set. Please set the RELAY_API_KEY environment variable "
                "or configure it in config.json.",
                file=sys.stderr
            )
            return False
        return True
