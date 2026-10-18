# Memory‑MCP‑Server
课程作业项目，选题：Memory MCP Server（Model Context Protocol）

> 调研参考 MCP 官方示例仓库 [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) 中 Memory 参考实现。
> 借鉴**外置持久记忆、MCP工具读写、按需召回**核心设计思想，未直接复用参考项目源码；基于 Python FastMCP 独立实现，采用扁平化记忆条目模型，扩展大模型语义分类、中文日期解析能力。

## 项目简介
本项目是一个 MCP 记忆服务端，使用 stdio 作为传输层，底层基于 JSON‑RPC 2.0。
实现记忆的新增、查询、检索、删除；接入 DeepSeek 大模型对记忆文本自动分类、提取标签；内置规则解析中文相对日期，记忆持久化保存在本地 JSON 文件。

### 工具列表
1. **add_memory**：新增记忆。接收自然语言记忆文本，自动完成分类、标签提取、日期解析，生成唯一记忆ID并持久化保存；大模型异常时自动降级保证服务可用。
2. **list_memories**：列出全部记忆，支持按标签过滤。
3. **search_memories**：关键词检索记忆，匹配记忆内容、分类、标签。
4. **delete_memory**：根据 memory_id 删除指定记忆。

## 目录结构

```text
├── main.py      # MCP记忆服务端主程序
├── mcp_client.py         # MCP测试客户端（参考官方SDK示例）
├── .env                  # 环境变量，存放DeepSeek API_KEY
├── memory_store.json     # 自动生成，记忆持久化存储文件
├── memory_store.tmp      # 临时写入文件（程序运行产生，可忽略）
├── requirements.txt      # 项目依赖
└── README.md             # 项目说明文档
```

## 环境准备
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
## 运行方式
客户端会自动拉起 MCP 服务端子进程，自动执行测试流程。
```powershell
python client.py
```
## 演示场景
MCP 客户端与服务端完成 initialize 握手，执行工具发现，获取全部可用工具；
1. 调用 ```add_memory```，输入自然语言记忆文本；服务自动解析分类、标签、日期，写入本地 JSON；
2. 调用 ```list_memories``` 查看已保存记忆；
3. 调用 ```search_memories``` 使用关键词检索相关记忆；
4. 调用 ```delete_memory``` 根据记忆 ID 删除指定记忆；
所有记忆持久化保存在 ```memory_store.json```，重启程序记忆不会丢失。

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