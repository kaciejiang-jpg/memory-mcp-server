import asyncio    #python异步IO库->管理异步任务的调度器（异步函数内等待一个io任务完成，过程中可以处理其他任务）
from typing import Optional  #类型注解，表示变量可以是指定类型或者none
from contextlib import AsyncExitStack  #异步管理资源器，统一自动关闭异步打开的连接、会话
from pathlib import Path   #查找、生成、管理文件（定位main.py）
from mcp import ClientSession, StdioServerParameters  #配置stdio启动服务端的参数（命令、脚本路径、工作目录）
from mcp.client.stdio import stdio_client  #FastMCP提供的stdio传输工具，创建stdio管道连接

# 项目路径与服务端文件名配置  
PROJECT_DIR = Path(__file__).resolve().parent  #当前脚本所在文件夹的绝对路径D:\memory-mcp-server
SERVER_FILE = PROJECT_DIR / "main.py"  #main.py的绝对路径D:\memory-mcp-server\main.py

# 定义需要的服务端工具集合
EXPECTED_TOOLS = {
    "add_memory",
    "list_memories",
    "search_memories",
    "delete_memory",
}

# 定义MCP客户端类，参考官方骨架实现
class MCPClient:
    def __init__(self):  #创建对象的时候规定自动调用这个函数，使对象具有下面属性
        self.session: Optional[ClientSession] = None  #给对象创造一个属性，类型要么是clientsession对象（连接会话->连接上下文的容器（保持异步网络连接状态）），要么是none
        self.exit_stack = AsyncExitStack()  #异步资源栈，统一管理所有异步打开的资源（stdio通道、session会话）

# 确立是.py文件
    async def connect_to_server(self, server_script_path: str): 
        is_python = server_script_path.endswith('.py') 
        if not is_python:
            raise ValueError("Server script must be a .py file")
        
        #配置启动服务进程        
        command = "python"  
        server_params = StdioServerParameters(   
            command=command,    #启动命令python
            args=[server_script_path],  #运行main.py的脚本路径
            cwd=str(PROJECT_DIR),  #工作目录（确保json文件路径正常）
            env=None
        )

        # #①异步方法启动main.py，建立stdio管道  ②初始化mcp会话（保持服务端与客户端之间的通信会话，负责收发mcp工具调用消息）
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))  #用刚刚配置好的参数启动main.py子程序，创建stdio管道的读（接受mcp服务端发送的消息）写（向mcp服务端发送消息）通道
        self.stdio, self.write = stdio_transport   #保存读写流到实例变量中
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))  #创建mcp协议会话（封装协议、两端自动握手、封装接口）

        # 初始化会话，获取可用工具列表
        await self.session.initialize()  #执行握手协议，完成两端初始化
        response = await self.session.list_tools()  #请求拿到服务端注册的全部工具名称
        available_tools = {tool.name for tool in response.tools}  
        print("已连接。服务端工具：" + ", ".join(sorted(available_tools)))
        missing_tools = EXPECTED_TOOLS - available_tools  #对比所得工具差异，确保完全获取
        if missing_tools:
            print("服务端缺少预期工具：" + ", ".join(sorted(missing_tools)))

    # 封装输入函数，异步读取控制台输入
    async def prompt(self, message: str) -> str:  #接受message作为提示文字（提示用户输入问题），最后返回用户输入的字符串
        return await asyncio.to_thread(input, message)   #借助thread新开独立子线程执行input，防止同步input卡住mcp主异步循环

    # 解析逗号分隔的标签字符串为列表
    def parse_tags(self, value: str) -> list[str]:
        return [tag.strip() for tag in value.split(",") if tag.strip()]

    # 打印工具调用返回结果
    def print_result(self, result) -> None:
        if result.isError:  #标记工具调用是否报错（例如删除不存在id、api调用失败）
            print("工具调用返回错误：")
        text_parts = [item.text for item in result.content if hasattr(item, "text")]  #遍历工具调用返回结果result里面的每个item，如果item是文本类型，具备.text属性，提取文本放到列表里
        if text_parts:
            print("\n".join(text_parts))  #将文本连接起来
        elif not result.isError:   #工具调用成功（布尔类型==false）
            print(result)  #直接返回原始信息

    # 打印命令操作提示信息，告诉用户支持的交互命令
    def print_help(self) -> None:
        print(
            "\n命令：\n"
            "  add     新增记忆\n"
            "  list    列出记忆，可按标签筛选\n"
            "  search  按关键词搜索\n"
            "  delete  按记忆 ID 删除\n"
            "  help    显示命令帮助\n"
            "  exit    退出客户端\n"
        )

    # 交互式命令行主循环
    async def chat_loop(self):   #对话主循环入口
        self.print_help()  #启动时先打印提示信息
        while True:   #持续等待用户输入命令
            try:
                command = (await self.prompt("mcp> ")).strip().lower()  #不区分大小写、空格
            except EOFError:
                print("\n输入结束，客户端退出。")   #按ctrl+d退出循环
                break
            if command in {"exit", "quit", "q"}:
                print("客户端已退出。")
                break
            if command in {"help", "h", "?"}:
                self.print_help()
                continue
        #判断退出命令、帮助命令，匹配则执行对应逻辑。break跳出 while 循环，continue回到循环开头继续等待输入

            try:
                if command == "add":  
                    content = (await self.prompt("记忆内容：")).strip()
                    if not content:
                        print("记忆内容不能为空。")
                        continue
                    result = await self.session.call_tool("add_memory", {"content": content})   #向服务端发送调用 add_memory 工具请求，传入 content 参数

                elif command == "list":
                    tags = self.parse_tags(await self.prompt("筛选标签（逗号分隔）："))
                    arguments = {"filter_tags": tags} if tags else {}
                    result = await self.session.call_tool("list_memories", arguments)  #list 列出记忆分支，直接回车返回全部记忆，输入标签做匹配筛选，调用 list_memories

                elif command == "search":
                    keyword = (await self.prompt("搜索关键词：")).strip()
                    if not keyword:
                        print("搜索关键词不能为空。")
                        continue
                    result = await self.session.call_tool("search_memories", {"keyword": keyword})  #输入关键词，调用 search_memories 工具检索记忆文本

                elif command == "delete":
                    memory_id = (await self.prompt("要删除的 memory_id：")).strip()  #用户输入要删除的 UUID 记忆 ID
                    if not memory_id:
                        print("memory_id 不能为空。")
                        continue
                    confirmation = (await self.prompt("确认永久删除？输入 y 确认：")).strip().lower()  #增加二次确认，输入 y 才执行删除，其他输入直接取消
                    if confirmation != "y":
                        print("已取消删除。")
                        continue
                    result = await self.session.call_tool("delete_memory", {"memory_id": memory_id})  #调用 delete_memory，传入 memory_id 精准删除对应记忆

                else:
                    print("未知命令，输入 help 查看可用命令。")
                    continue

                self.print_result(result)  #与前面程序相同，接收 MCP 工具调用返回的result对象，自动提取文本并打印

            except Exception as error:  #捕获单次工具调用异常，不会让整个客户端程序崩溃
                print(f"工具调用失败：{error}")

    # 资源清理，关闭连接
    async def cleanup(self):
        await self.exit_stack.aclose()

# 程序入口
async def main():
    client = MCPClient()  #创建 MCPClient 实例
    try:  #连接服务端，启动交互式命令循环
        print(f"正在启动 MCP Server：{SERVER_FILE}")  
        await client.connect_to_server(str(SERVER_FILE))
        await client.chat_loop()
    finally:   #无论成败，最终一定执行资源清除释放资源
        await client.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:   #用户强行停止，打印提示词
        print("\n客户端已中断。")
    except Exception as error:  #外部捕获连接失败异常（服务端启动失败，main.py不存在）
        print(f"无法连接 MCP Server：{error}")
