# Memory‑MCP‑Server
课程作业项目，选题：Memory MCP Server（Model Context Protocol）

> 调研参考 MCP 官方示例仓库 [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) 中 Memory 参考实现。
> 借鉴**外置持久记忆、MCP工具读写、按需召回**核心设计思想，未直接复用参考项目源码；基于 Python FastMCP 独立实现，采用扁平化记忆条目模型，扩展大模型语义分类、中文日期解析能力。

## 项目简介
本项目是一个 MCP 记忆服务端，使用 stdio 作为传输层，底层基于 JSON‑RPC 2.0。
实现记忆的新增、查询、检索、删除；接入 DeepSeek 大模型对记忆文本自动分类、提取标签；内置规则解析中文相对日期，记忆持久化保存在本地 JSON 文件。
MCP 基于 Python 异步 IO（asyncio）开发。MCP 客户端与服务端之间通过管道或网络通信，这类操作存在大量 IO 等待。使用async/await异步机制，程序在等待 IO 返回时不会阻塞，可以并发处理多条消息，提升通信效率。MCP SDK 提供的接口均为异步函数，调用时必须使用awai

## 工具列表
1. **add_memory**：新增记忆。接收自然语言记忆文本，自动完成分类、标签提取、日期解析，生成唯一记忆ID并持久化保存；大模型异常时自动降级保证服务可用。
2. **list_memories**：列出全部记忆，支持按标签过滤。
3. **search_memories**：关键词检索记忆，匹配记忆内容、分类、标签。
4. **delete_memory**：根据 memory_id 删除指定记忆。

## 目录结构

```text
├── main.py      # MCP记忆服务端主程序：核心功能实现
├── mcp_client.py         # MCP测试客户端：独立测试程序
├── memory_store.json     # 本地记忆数据文件，运行后自动生成
├── .gitignore            # Git 忽略文件配置
├── .env                  # 环境变量，存放DeepSeek API_KEY
├── .env.example          # 环境变量配置示例，不含真实密钥
├── requirements.txt      # 项目依赖
├── README.md             # 项目说明文档
└── opencode.json         # OpenCode的MCP服务配置
```

## 核心设计说明
1. 通信机制 <br>
使用 stdio（标准输入输出）作为传输通道。<br>
（1）stdin：接收客户端 JSON‑RPC 请求  <br>
（2）stdout：返回 JSON‑RPC 响应报文   <br>
（3）stderr：打印日志与异常信息，日志不会污染 MCP 协议报文  <br>
2. 存储方案 <br>
（1）存储介质：本地 JSON 文件 ```memory_store.json ```<br>
（2）数据模型：扁平化记忆条目，每条记忆拥有唯一  ```memory_id```，包含记忆原文、分类、事件日期、标签、创建时间；<br>
（3）写入策略：采用临时文件原子写入，防止程序异常中断导致 JSON 文件损坏；<br>
（4）加载容错：读取文件出现损坏 / 格式错误时，捕获异常并重置为空记忆列表，服务不会崩溃。<br>

## 演示场景
MCP 客户端与服务端完成 initialize 握手，执行工具发现，获取全部可用工具；
1. 调用 ```add_memory```，输入自然语言记忆文本；服务自动解析分类、标签、日期，写入本地 JSON；
2. 调用 ```list_memories``` 查看已保存记忆；
3. 调用 ```search_memories``` 使用关键词检索相关记忆；
4. 调用 ```delete_memory``` 根据记忆 ID 删除指定记忆；
所有记忆持久化保存在 ```memory_store.json```，重启程序记忆不会丢失。


## 调用本地mcp_client.py实现

### 环境准备
1. 创建虚拟环境（Windows PowerShell）
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```
2. 安装依赖
```powershell
pip install -r requirements.txt
```
3. 配置环境变量
在项目根目录新建 .env 文件，填入 DeepSeek API Key
```
env
API_KEY=你的deepseek_api_key
```
### 运行方式
客户端会自动拉起 MCP 服务端子进程，自动执行测试流程。
```powershell
python client.py
```

### 项目运行流程：

客户端和服务端是通过STDIO传输方式进行通信的。
1. 首先，客户端程序 ```mcp_client.py ```运行后，会创建一个 MCPClient 实例，并调用``` connect_to_server() ```方法建立与服务端的连接。
2. 同时，客户端会通过 ```stdio_client ```启动 main.py，使服务端作为一个独立的子进程运行。
3. 在```main.py ```中会创建一个 FastMCP 实例，并注册 ```add_memory()、list_memories()、search_memories() 、delete_memory()``` 四个工具，
4. 通过 ```mcp.run(transport="stdio") ```启动服务端，等待客户端发送请求。
5. 当服务端启动后，客户端会创建 ```ClientSession ```对象，并通过 ```initialize() ```完成 MCP 会话初始化。
6. 随后，客户端调用 ```list_tools()``` 获取服务端注册的工具列表，从而发现服务端提供了哪些功能。
7. 当用户需要执行某项操作时，例如添加一条记忆，客户端就会调用 ```call_tool("add_memory", ...)```，将工具名称和相应参数发送给服务端。
8. 服务端接收到请求后，根据工具名称找到对应的 Python 函数并执行，完成记忆添加、数据保存等操作，最后将执行结果返回给客户端，由客户端接收并展示给用户。

## 调用可视化OpenCode实现

### 环境准备
1. 准备Python环境，配置API Key，安装 OpenCode 客户端。
2. 完成``` opencode.jsonc ```的配置编写：使用本地 MCP Server + Python 启动服务端 + 指定项目所在目录

### 运行方式：
  以 OpenCode 作为 MCP Client，连接自己编写的 Memory MCP Server，OpenCode 会根据配置启动本地的 main.py，并通过 STDIO 传输方式与 MCP Server 建立通信。

### 项目运行流程：

1. 当 OpenCode 启动并读取配置文件后，会根据配置中的 command 执行：```python main.py```，启动 MCP Server。
2. OpenCode 作为 MCP Client，通过 STDIO 传输方式与``` main.py ```建立通信并完成初始化。
3. 连接成功后，OpenCode 可以发现服务端注册的四个工具，用户输入指令，调用相关工具。
4. 服务端执行完对应的工具函数后，会将执行结果通过 MCP 协议返回给 OpenCode，OpenCode 再将工具执行结果交给模型，由模型组织语言，最终向用户展示结果。