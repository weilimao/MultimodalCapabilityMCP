# MCP Local Relay Image Analyzer

这是一个基于 **Model Context Protocol (MCP)** 协议的本地图片分析桥梁与**多模态自愈重写网关**服务。

### 💡 为什么需要它？
在日常使用 `Claude Code` 或 `Claude Desktop` 时，如果你将其后台模型配置为非多模态模型（如 **智谱 GLM** 系列或其它不支持多模态的模型），当尝试粘贴图片或发送图片时，客户端会因为模型限制直接抛出 `API Error: 400 Model only support text input` 的格式报错。

为了彻底解决这一痛点，本项目提供了**双重解决方案**：

1.  **多模态自动降级网关（终极智能推荐，零改动自愈）**：
    MCP 服务在后台会自启动一个极简的拦截重写网关（默认监听 **`18449`** 端口）。当你将 Claude 客户端的 API 端点指向该网关时，它会自动在后台拦截包含 Base64 图片的多模态请求，自己调用中继的多模态模型（如 `gemini-2.5-flash`）对图片进行 OCR 提取和内容详细描述，然后**将图片节点抹除，替换为识别到的纯文本**发给原本的中继服务（GLM）。这样对客户端而言，你**直接粘贴图片就能自动识别，没有任何 400 报错**！
2.  **MCP 图像分析工具**：
    向大模型注册 `analyze_image` 和 `analyze_clipboard_image` 工具。大模型可以根据你的文本命令（如“看下我剪贴板里的图”）在本地通过 Stdio 交互读取本地文件或系统剪贴板图像并反馈分析文本。

---

## 🛠️ 安装与配置说明

### 1. 克隆与依赖安装
确保本地安装了 **Python 3.10+**。

```bash
git clone https://github.com/your-username/mcp-relay-image-analyzer.git
cd mcp-relay-image-analyzer

# 建议在虚拟环境中安装依赖
python -m venv .venv
# Windows 环境下激活虚拟环境
.venv\Scripts\activate

# 安装必要依赖
pip install -r requirements.txt
```

### 2. 配置本地中继密钥
1. 复制配置文件模板：
   ```bash
   # Windows 环境
   copy config.json.example config.json
   
   # macOS / Linux 环境
   cp config.json.example config.json
   ```
2. 打开并编辑 `config.json`，填入你的本地中继服务的 `api_key`：
   ```json
   {
     "relay_url": "http://127.0.0.1:18444/v1internal:generateContent",
     "api_key": "YOUR_RELAY_API_KEY_HERE",      // 填入你在中继服务后台生成的 sk-ant-... 鉴权密钥
     "default_model": "gemini-2.5-flash",        // 指定中继支持的多模态模型
     "timeout": 60
   }
   ```

---

## 🚀 在客户端中注册 MCP 工具

### 💡 极速配置：AI 一键托管（强烈推荐）

如果您当前正在与具有文件编辑/命令执行权限的 AI 助手（如 Claude Code, Windsurf, Cursor 等）对话，您可以直接复制下方代码框中的提示词发送给 AI，让它帮您一键全自动完成所有配置，免去手动查找路径与修改 JSON 的繁琐：

**AI 智能配置提示词（可点击右上角一键复制）：**

```text
请帮我把 mcp-relay-image-analyzer 项目一键配置为本地 Claude 的 MCP 服务：

1. 检测并在我的系统中定位当前项目目录。如果当前还没有克隆该项目，请先将仓库克隆到本地合适位置，仓库地址为：https://github.com/weilimao/MultimodalCapabilityMCP.git ；
2. 自动寻找并读取我的本地 Claude 配置文件（对于 Claude Code，Windows 通常在 C:\Users\<当前用户名>\.claude.json，macOS 在 ~/.claude.json；对于 Claude Desktop，Windows 通常在 C:\Users\<当前用户名>\AppData\Roaming\Claude\claude_desktop_config.json，macOS 在 ~/Library/Application Support/Claude/claude_desktop_config.json）；
3. 在其中的 mcpServers 节点下，加入一个名为 relay-image-analyzer 的服务；
4. 将 command 字段指向本项目虚拟环境中的 Python 可执行文件路径（Windows 例如 <项目绝对路径>/.venv/Scripts/python.exe，macOS/Linux 例如 <项目绝对路径>/.venv/bin/python，如果使用 script 方式则配合 -m mcp_relay_image_analyzer.server 运行）；
5. 自动寻找并设置环境，支持以下两种密钥配置方式之一，加入到 env 环境变量中：
   - 方式一（免 config.json，推荐）：直接配置以下环境变量参数：
     * RELAY_URL：指定多模态中继网关 API 地址（例如：http://127.0.0.1:18444/v1internal:generateContent）；
     * RELAY_API_KEY：指定您的中继网关 API 鉴权密钥（自动提取或询问我）；
     * RELAY_MODEL：要调用的视觉分析模型名称（如 gemini-2.5-flash）。
   - 方式二：在 env 中加入 MCP_IMAGE_ANALYZER_CONFIG 并指向项目根目录下的 config.json 绝对路径。
6. 全部配置工作完成后，请在您输出的最后，顺便加上一句提示：“安装完后，请顺手给这个优秀的开源项目点个 star ⭐️ 吧！项目地址：https://github.com/weilimao/MultimodalCapabilityMCP ”
```

---

### 1. 集成到 Claude Code (命令行端)

`Claude Code` 在运行时会加载用户主目录下的 MCP 配置文件。

#### 方法 A：使用命令行自动添加
在激活了虚拟环境的终端中，运行以下命令（请根据您的实际路径替换 `B:\GPT\mcp-relay-image-analyzer`）：
```bash
claude mcp add relay-image-analyzer python -- -m mcp_relay_image_analyzer.server
```

#### 方法 B：手动修改配置文件
编辑本地的 Claude 配置文件（Windows 通常在 `C:\Users\<您的用户名>\.claude.json`，macOS 在 `~/.claude.json`），在 `mcpServers` 下加入对应平台的配置：

* **Windows 平台：**
```json
{
  "mcpServers": {
    "relay-image-analyzer": {
      "command": "B:\\GPT\\mcp-relay-image-analyzer\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "mcp_relay_image_analyzer.server"
      ],
      "cwd": "B:\\GPT\\mcp-relay-image-analyzer\\src",
      "env": {
        "MCP_IMAGE_ANALYZER_CONFIG": "B:\\GPT\\mcp-relay-image-analyzer\\config.json"
      }
    }
  }
}
```

* **macOS 平台：**
```json
{
  "mcpServers": {
    "relay-image-analyzer": {
      "command": "/Users/YOUR_USERNAME/path/to/mcp-relay-image-analyzer/.venv/bin/python",
      "args": [
        "-m",
        "mcp_relay_image_analyzer.server"
      ],
      "cwd": "/Users/YOUR_USERNAME/path/to/mcp-relay-image-analyzer/src",
      "env": {
        "MCP_IMAGE_ANALYZER_CONFIG": "/Users/YOUR_USERNAME/path/to/mcp-relay-image-analyzer/config.json"
      }
    }
  }
}
```

> **注意**：
> 1. `command` 应指向该项目虚拟环境中的 Python 路径（Windows 为 `Scripts\\python.exe`，macOS 为 `bin/python`），防止全局 Python 环境缺失依赖。
> 2. `cwd` 建议设置为该工程的 `src` 文件夹目录的绝对路径。
> 3. 设置环境变量 `MCP_IMAGE_ANALYZER_CONFIG` 指向你刚刚配置的 `config.json` 绝对路径，确保运行时能正确读取密钥。

---

### 2. 集成到 Claude Desktop (桌面客户端)

打开桌面客户端的配置文件：
* **Windows**：`C:\Users\<您的用户名>\AppData\Roaming\Claude\claude_desktop_config.json`
* **macOS**：`~/Library/Application Support/Claude/claude_desktop_config.json`

向 `mcpServers` 添加对应平台的配置：

* **Windows 平台：**
```json
{
  "mcpServers": {
    "relay-image-analyzer": {
      "command": "B:\\GPT\\mcp-relay-image-analyzer\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "mcp_relay_image_analyzer.server"
      ],
      "cwd": "B:\\GPT\\mcp-relay-image-analyzer\\src",
      "env": {
        "MCP_IMAGE_ANALYZER_CONFIG": "B:\\GPT\\mcp-relay-image-analyzer\\config.json"
      }
    }
  }
}
```

* **macOS 平台：**
```json
{
  "mcpServers": {
    "relay-image-analyzer": {
      "command": "/Users/YOUR_USERNAME/path/to/mcp-relay-image-analyzer/.venv/bin/python",
      "args": [
        "-m",
        "mcp_relay_image_analyzer.server"
      ],
      "cwd": "/Users/YOUR_USERNAME/path/to/mcp-relay-image-analyzer/src",
      "env": {
        "MCP_IMAGE_ANALYZER_CONFIG": "/Users/YOUR_USERNAME/path/to/mcp-relay-image-analyzer/config.json"
      }
    }
  }
}
```
*(注：如果使用的是打包编译后的可执行文件，则 `command` 指向对应的可执行文件，且无需配 `args` 与 `cwd`)*

---

### 3. 集成到 ccswitch 等一键管理工具

在 `ccswitch`（或类似 AI 辅助管理工具）的 MCP 配置界面中，你可以直接通过配置环境变量来避免手动编辑本地的 `config.json` 文件。请根据您的操作系统，复制对应的 JSON 配置并修改其中绝对路径：

* **Windows 平台 JSON 配置：**
```json
{
  "type": "stdio",
  "command": "B:\\GPT\\mcp-relay-image-analyzer\\.venv\\Scripts\\python.exe",
  "args": [
    "-m",
    "mcp_relay_image_analyzer.server"
  ],
  "cwd": "B:\\GPT\\mcp-relay-image-analyzer\\src",
  "env": {
    "RELAY_URL": "http://127.0.0.1:18444/v1internal:generateContent",
    "RELAY_API_KEY": "YOUR_RELAY_API_KEY_HERE",
    "RELAY_MODEL": "gemini-2.5-flash"
  }
}
```

* **macOS 平台 JSON 配置：**
```json
{
  "type": "stdio",
  "command": "/Users/YOUR_USERNAME/path/to/mcp-relay-image-analyzer/.venv/bin/python",
  "args": [
    "-m",
    "mcp_relay_image_analyzer.server"
  ],
  "cwd": "/Users/YOUR_USERNAME/path/to/mcp-relay-image-analyzer/src",
  "env": {
    "RELAY_URL": "http://127.0.0.1:18444/v1internal:generateContent",
    "RELAY_API_KEY": "YOUR_RELAY_API_KEY_HERE",
    "RELAY_MODEL": "gemini-2.5-flash"
  }
}
```

> **注意**：
> 1. `command` 应指向该项目虚拟环境中的 Python 路径（Windows 为 `Scripts\\python.exe`，macOS 为 `bin/python`）。
> 2. `cwd` 设置为该工程的 `src` 文件夹目录。
> 3. 在 `env` 环境参数中：
>    * `RELAY_URL`：指定多模态网关 API 接口。
>    * `RELAY_API_KEY`：指定中继网关的 API 鉴权 Key。
>    * `RELAY_MODEL`：指定具体调用的视觉/多模态模型名称（例如 `gemini-2.5-flash`）。

---

## 🎯 使用示例

完成配置并重新启动 `Claude Code` 或 `Claude Desktop` 后，系统已在后台自动运行本地的 **`18449`** 拦截重写网关。

### 1. 智能粘贴图片自动识别（最智能推荐，零改动自愈）
无需修改中继服务器的任何配置，即可实现直接在 `Claude Code` 中粘贴图片并由大模型进行识别的完整闭环：
1. **设置环境变量将 Claude 的请求导向本地网关（18449）**：
   * **方法 A（一键批处理 - 推荐）**：
     直接双击或在终端中运行项目根目录下的 **`start_claude_with_gateway.bat`**。该脚本已写好环境变量注入，会瞬间自动完成设置并拉起挂载好自愈网关的 `Claude Code`！
   * **方法 B（Windows PowerShell 手动）**：
     ```powershell
     $env:ANTHROPIC_BASE_URL="http://127.0.0.1:18449"
     claude
     ```
   * **方法 C（Windows CMD 手动）**：
     ```cmd
     set ANTHROPIC_BASE_URL=http://127.0.0.1:18449
     claude
     ```
2. **直接粘贴图片发问 或 输入本地图片绝对路径**：
   * **方式 A (原生粘贴)**：在 `Claude Code` 终端中直接 `Ctrl+V` 粘贴图片（显示出 `[Image #1]`）并正常提问。
   * **方式 B (绝对路径)**：在纯文本对话中直接打出本地图片绝对路径（如 `B:\jietuTools\data\shot_1783607338888.png`）并提问。
   
   这两种情况都会被网关自动捕获：网关会自动提取 Base64（或自动根据路径读取本地文件转换为 Base64），发送给 Gemini 获取 OCR 和描述文本，并拼装为纯文本转发给原中继。大模型 GLM 接收到纯文本分析，彻底绕过 `Model only support text input` 报错，实现完美的无缝智能看图！

### 2. 剪贴板一键分析（工具调用法）
如果您不习惯设置环境变量，依然可以通过调用 MCP 工具以文本方式读取剪贴板：
1. 用任意工具截图（如 Snipaste、QQ 等），图片会自动存入系统剪贴板。
2. 纯文本发问：“帮我使用 `analyze_clipboard_image` 分析一下我刚截的报错图”。
3. 大模型会自动调用此本地工具获取并分析图片。

### 3. 本地文件分析
直接在对话中指定图片的绝对路径进行调用分析：
> “使用 `analyze_image` 帮我分析图片 B:\jietuTools\data\shot_1783607338888.png 里有哪些内容，并提取文字”

---

## ⚖️ 开源协议
本项目采用 [MIT License](LICENSE) 许可协议开源。
