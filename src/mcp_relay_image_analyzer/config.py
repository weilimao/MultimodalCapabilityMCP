import os
import json
import sys
from pathlib import Path

DEFAULT_RELAY_URL = "http://127.0.0.1:18444/v1internal:generateContent"
DEFAULT_MODEL = "gemini-2.5-flash"

class Config:
    def __init__(self):
        self.relay_url = os.getenv("RELAY_URL", DEFAULT_RELAY_URL)
        self.api_key = os.getenv("RELAY_API_KEY", "")
        self.default_model = os.getenv("RELAY_MODEL", DEFAULT_MODEL)
        self.timeout = int(os.getenv("RELAY_TIMEOUT", "60"))
        self.upstream_base_url = os.getenv("UPSTREAM_BASE_URL", "http://127.0.0.1:18444")

        # 如果没有通过环境变量设置 API_KEY，则尝试从 config.json 中读取
        if not self.api_key:
            self._load_from_file()

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
