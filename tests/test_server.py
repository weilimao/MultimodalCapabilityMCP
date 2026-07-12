import unittest
import os
import sys
from unittest.mock import patch, MagicMock
import requests

# 确保项目 src 目录在 Python 模块搜索路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mcp_relay_image_analyzer.config import Config
from src.mcp_relay_image_analyzer import server

class TestServerMultimodal(unittest.TestCase):
    
    def setUp(self):
        # 每次测试前，将 config 中的配置恢复默认状态
        server.config.relay_url = "http://127.0.0.1:18444/v1internal:generateContent"
        server.config.api_key = "test_api_key"
        server.config.relay_format = "google"
        server.config.default_model = "gemini-2.5-flash"
        server.config.timeout = 30

    def test_build_final_url(self):
        # 1. google 格式：直接原样返回，完全向后兼容
        url_google = server._build_final_url("http://127.0.0.1:18444/v1internal:generateContent", "google")
        self.assertEqual(url_google, "http://127.0.0.1:18444/v1internal:generateContent")
        url_google_base = server._build_final_url("http://127.0.0.1:18444", "google")
        self.assertEqual(url_google_base, "http://127.0.0.1:18444")
        
        # 2. openai 格式：
        # 已有全路径
        url_openai_full = server._build_final_url("https://ark.cn-beijing.volces.com/api/v3/chat/completions", "openai")
        self.assertEqual(url_openai_full, "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
        # 普通域名 Base URL，追加 /v1/chat/completions
        url_openai_base = server._build_final_url("https://api.openai.com", "openai")
        self.assertEqual(url_openai_base, "https://api.openai.com/v1/chat/completions")
        # 火山引擎 Base URL，追加 /api/v3/chat/completions
        url_volc_base = server._build_final_url("https://ark.cn-beijing.volces.com", "openai")
        self.assertEqual(url_volc_base, "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
        # 火山引擎输入包含 api/v3，追加 /chat/completions
        url_volc_v3 = server._build_final_url("https://ark.cn-beijing.volces.com/api/v3", "openai")
        self.assertEqual(url_volc_v3, "https://ark.cn-beijing.volces.com/api/v3/chat/completions")

        # 3. anthropic 格式：
        # 已有全路径
        url_anthropic_full = server._build_final_url("https://api.anthropic.com/v1/messages", "anthropic")
        self.assertEqual(url_anthropic_full, "https://api.anthropic.com/v1/messages")
        # 官方 Base URL，追加 /v1/messages
        url_anthropic_base = server._build_final_url("https://api.anthropic.com", "anthropic")
        self.assertEqual(url_anthropic_base, "https://api.anthropic.com/v1/messages")
        # 火山 coding 接口 Base URL，追加 /messages
        url_volc_coding = server._build_final_url("https://ark.cn-beijing.volces.com/api/coding/v3", "anthropic")
        self.assertEqual(url_volc_coding, "https://ark.cn-beijing.volces.com/api/coding/v3/messages")

    @patch("requests.post")
    def test_send_multimodal_request_google_success(self, mock_post):
        # 1. 模拟 Google v1internal 接口的成功响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": "这是由 Google 格式返回的图像分析结果。"
                                }
                            ]
                        }
                    }
                ]
            }
        }
        mock_post.return_value = mock_response

        # 执行请求
        result = server._send_multimodal_request(
            img_base64="fake_base64_data",
            mime_type="image/png",
            prompt="分析此图",
            target_model="gemini-2.5-flash"
        )

        self.assertEqual(result, "这是由 Google 格式返回的图像分析结果。")
        mock_post.assert_called_once()
        
        # 验证 Payload 和 Headers
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "http://127.0.0.1:18444/v1internal:generateContent")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test_api_key")
        payload = kwargs["json"]
        self.assertEqual(payload["model"], "gemini-2.5-flash")
        # 验证符合 Google 协议结构
        self.assertIn("request", payload)
        self.assertEqual(payload["request"]["contents"][0]["parts"][0]["text"], "分析此图")
        self.assertEqual(payload["request"]["contents"][0]["parts"][1]["inlineData"]["data"], "fake_base64_data")

    @patch("requests.post")
    def test_send_multimodal_request_openai_success(self, mock_post):
        # 2. 模拟 OpenAI/火山引擎 接口的成功响应，输入仅使用 Base URL，验证自适应补全功能
        server.config.relay_format = "openai"
        server.config.relay_url = "https://ark.cn-beijing.volces.com"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "这是由 火山/OpenAI 格式返回的图像分析结果。"
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        # 执行请求
        result = server._send_multimodal_request(
            img_base64="fake_base64_data",
            mime_type="image/jpeg",
            prompt="分析此图",
            target_model="ep-test-model"
        )

        self.assertEqual(result, "这是由 火山/OpenAI 格式返回的图像分析结果。")
        mock_post.assert_called_once()

        # 验证 Payload 和 Headers
        args, kwargs = mock_post.call_args
        # 验证自适应补全后的火山 Endpoint 地址
        self.assertEqual(args[0], "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test_api_key")
        payload = kwargs["json"]
        self.assertEqual(payload["model"], "ep-test-model")
        # 验证符合 OpenAI 协议结构
        self.assertIn("messages", payload)
        messages = payload["messages"]
        self.assertEqual(messages[0]["content"][0]["text"], "分析此图")
        self.assertEqual(messages[0]["content"][1]["image_url"]["url"], "data:image/jpeg;base64,fake_base64_data")

    @patch("requests.post")
    def test_send_multimodal_request_anthropic_success(self, mock_post):
        # 3. 模拟 Anthropic 接口的成功响应，输入使用 Base URL，验证自适应补全功能
        server.config.relay_format = "anthropic"
        server.config.relay_url = "https://api.anthropic.com"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [
                {
                    "type": "text",
                    "text": "这是由 Anthropic 格式返回的图像分析结果。"
                }
            ]
        }
        mock_post.return_value = mock_response

        # 执行请求
        result = server._send_multimodal_request(
            img_base64="fake_base64_data",
            mime_type="image/png",
            prompt="分析此图",
            target_model="claude-3-5-sonnet"
        )

        self.assertEqual(result, "这是由 Anthropic 格式返回的图像分析结果。")
        mock_post.assert_called_once()

        # 验证 Payload 和 Headers
        args, kwargs = mock_post.call_args
        # 验证自适应补全后的 Anthropic API 地址
        self.assertEqual(args[0], "https://api.anthropic.com/v1/messages")
        # Anthropic 特定 Headers 校验
        self.assertEqual(kwargs["headers"]["x-api-key"], "test_api_key")
        self.assertEqual(kwargs["headers"]["anthropic-version"], "2023-06-01")
        
        payload = kwargs["json"]
        self.assertEqual(payload["model"], "claude-3-5-sonnet")
        self.assertEqual(payload["max_tokens"], 1024)
        # 验证符合 Anthropic 协议结构
        self.assertIn("messages", payload)
        messages = payload["messages"]
        self.assertEqual(messages[0]["content"][0]["source"]["data"], "fake_base64_data")
        self.assertEqual(messages[0]["content"][1]["text"], "分析此图")

    @patch("requests.post")
    def test_send_multimodal_request_http_error(self, mock_post):
        # 4. 模拟网络异常/非 200 HTTP 响应
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with self.assertRaises(RuntimeError) as context:
            server._send_multimodal_request(
                img_base64="fake",
                mime_type="image/png",
                prompt="test",
                target_model="test-model"
            )
        self.assertIn("HTTP 错误码 500", str(context.exception))

    @patch("requests.post")
    def test_send_multimodal_request_invalid_json(self, mock_post):
        # 5. 模拟返回非 JSON 响应的异常
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("No JSON")
        mock_response.text = "Not a json string"
        mock_post.return_value = mock_response

        with self.assertRaises(RuntimeError) as context:
            server._send_multimodal_request(
                img_base64="fake",
                mime_type="image/png",
                prompt="test",
                target_model="test-model"
            )
        self.assertIn("非 JSON 格式内容", str(context.exception))

if __name__ == "__main__":
    unittest.main()
