import json  #读写本地记忆存储文件
import logging  #日志模块，记录程序异常
import os  #读取环境变量
import re  #正则表达式模块，用于解析日期（提取关键信息）
import uuid  #生成全局唯一记忆 ID（每一条记忆对应一个独特id）
from datetime import date, datetime, timedelta  #日期时间处理，计算相对时间（明天、后天）
from pathlib import Path #查找、生成、管理文件
from dotenv import load_dotenv  #读取api key
from mcp.server.fastmcp import FastMCP #mcp服务端sdk，快速注册工具（包括通信方式、解析json消息、异常处理、收到工具调用请求并调用相应函数：@mcp.tool()）
from openai import OpenAI  #兼容openai接口格式，调用deepseek


logger = logging.getLogger(__name__) #创造相应的日志模块，用于记录异常信息（可单独建立文件/终端显示）（当代码无语法错误时，内部出现问题则需要日志显示）
load_dotenv()  #加载环境变量文件

client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url="https://api.deepseek.com",
)   #创建openai客户端，读取环境变量中的api key，连接deepseek服务器

STORE_FILE = Path(__file__).resolve().parent / "memory_store.json"  #__file__表示当前文件路径，resolve()返回绝对路径(完善成一个完整的路径)，parent / "memory_store.json" 
CATEGORIES = {"工作待办", "日程安排", "事件提醒", "普通记忆"} #规定输入记忆内容的分类，方便后续分析和检索
mcp = FastMCP("Memory-MCP-Server")  #创建mcp服务端实例（容器），后面采用@mcp.tool()装饰器往里注册工具函数
memories = []  #暂时存放记忆的列表，结束后存储到json文件中


def analyze_memory(text: str) -> tuple[str, list[str]]:  
    """Use DeepSeek to classify a memory and extract concise keyword tags."""  #大模型语言分析函数，把语句发给deepseek分析，返回分类和标签

    prompt = f"""
分析下面的中文记忆，只返回 JSON 对象，不要解释：
{{"category":"工作待办|日程安排|事件提醒|普通记忆中的一个","tags":["关键词"]}}
分类规则：
- 工作待办：需要完成的工作或任务。
- 日程安排：计划中的活动、会议或约会。
- 事件提醒：用户明确要求提醒，或记录需要在未来提醒的事情。
- 普通记忆：不属于以上三类。
关键词提取 2 到 6 个，不要把相对日期词（如“明天”）作为标签，具体日期由程序添加。   
记忆：{text}  
"""    #写给大模型的指令，规定输出只能是 JSON，只能选 4 类中的一种，提取 2~6 个关键词
    response = client.chat.completions.create(  #client前面创建的api客户端，chat对话类接口，completions处理多轮对话消息，create网络请求函数（模型名称、用户消息、系统提示词）
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,  #稳定性
    )   #调用大模型api，向大模型发送对话请求，将模型返回的结果存到response中

    content = response.choices[0].message.content  #读取大模型返回内容
    if not content:
        raise ValueError("DeepSeek 未返回分析结果")  #异常处理（空内容）
    
    content = content.strip().removeprefix("```json").removesuffix("```").strip()   #保留大模型返回json内容的纯文本（有时候大模型会用 markdown 代码块包裹 JSON）
    result = json.loads(content)  #转成python字典

    category = result.get("category") #在结果中取出类别
    tags = result.get("tags")  #取标签
    if category not in CATEGORIES:  
        raise ValueError(f"DeepSeek 返回了无效分类：{category!r}")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):  #isinstance(变量，类型)判断变量是否是某种类型，all()判断列表中所有元素是否满足条件
        raise ValueError("DeepSeek 返回的标签不是字符串数组")
    
    return category, [tag.strip() for tag in tags if tag.strip()]  #清理标签空格，删除空标签，返回记忆分类和标签


def extract_date(text: str, today: date | None = None) -> date | None:  #日期提取函数（原始文本，基准日期（可以是具体时间也可以是None->默认是今天的日期））——>返回的两种类型（日期或者是None）
    """Resolve common Chinese relative and explicit date expressions.""" #解释函数作用，算是注释
    today = today or date.today()
    if "大后天" in text:
        return today + timedelta(days=3)
    if "后天" in text:
        return today + timedelta(days=2)
    if "明天" in text:
        return today + timedelta(days=1)
    if "今天" in text or "今日" in text:
        return today

    iso_match = re.search(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)", text)
    if iso_match:
        try:
            return date(*(int(part) for part in iso_match.groups()))
        except ValueError:
            return None  #匹配2026-10-18这种标准日期形式

    month_day = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})[日号]?", text)
    if not month_day:
        month_day = re.search(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?!\d)", text)
    if month_day:
        month, day_number = map(int, month_day.groups())   #匹配日期
        try:
            resolved = date(today.year, month, day_number) 
            if resolved < today:
                resolved = date(today.year + 1, month, day_number) #解析日期小于目前日期，则自动推到下一年
            return resolved
        except ValueError:
            return None   

    weekday_match = re.search(
        r"(下下周|下周|本周|这周|周|星期|礼拜)([一二三四五六日天])",
        text,
    )
    if weekday_match:
        period, weekday_name = weekday_match.groups()
        target_weekday = "一二三四五六日".find(
            "日" if weekday_name == "天" else weekday_name
        )
        monday = today - timedelta(days=today.weekday())
        week_offset = 14 if period == "下下周" else 7 if period == "下周" else 0
        resolved = monday + timedelta(days=week_offset + target_weekday)
        if period in {"周", "星期", "礼拜"} and resolved <= today:
            resolved += timedelta(days=7)
        return resolved   #匹配中文星期描述，以周一为一周起点

    return None    #文字里没有日期，则返回空

def load_memories():  #在json文件里加载之前存储的全部记忆，并加载到memories列表中，方便后续操作
    """Load saved memories from the project JSON file."""
    global memories  #声明全局变量memories（add、list、search、delete都用这个列表）
    if not STORE_FILE.exists():  #首次使用还未创建json文件，自动创建
        memories = []
        return
    
    with STORE_FILE.open("r", encoding="utf-8") as file:   #安全打开文件，读取完成后自动关闭  r->只读模式，encoding="utf-8"->读取中文不乱码
        data = json.load(file)
    if not isinstance(data, list):  #确保data为列表类型
        raise ValueError(f"{STORE_FILE} 必须包含 JSON 数组")   #异常处理
    memories = data   


def save_memories():
    """Write memories to the project JSON file."""
    with STORE_FILE.open("w", encoding="utf-8") as file:  #写入json文件中
        json.dump(memories, file, ensure_ascii=False, indent=2)  #支持中文+格式化


load_memories()  #直接调用加载函数，载入历史记忆


@mcp.tool()  #装饰器，注册为mcp可调用工具
def add_memory(content: str, tags: list[str] | None = None) -> str:  
    """Save a memory with automatically inferred category, tags, and date."""

    if not content or not content.strip():
        return "错误：记忆内容 content 不能为空！"
    content = content.strip()
    event_date = extract_date(content)
    analysis_failed = False  #初始化一个异常标记，创建布尔变量，false表示大模型分析成功，True表示大模型分析失败
    try:
        category, inferred_tags = analyze_memory(content)
    except Exception:    #保底措施，如果api报错，做降级处理，保证程序正常运行
        logger.exception("DeepSeek 记忆分析失败")
        category, inferred_tags = "普通记忆", ["记忆"]
        analysis_failed = True

    memory_tags = [tag.strip() for tag in (tags or inferred_tags) if tag.strip()]
    if event_date:
        date_tag = event_date.isoformat()
        if date_tag not in memory_tags:
            memory_tags.append(date_tag)  #如果识别除日期，自动添加到标签中，方便后续检索

#构造记忆字典，uuid生成唯一id，content是记忆内容，category是分类，event_date是日期，tags是标签，create_time是创建时间
    memory = {
        "memory_id": str(uuid.uuid4()),
        "content": content,
        "category": category,
        "event_date": event_date.isoformat() if event_date else None,
        "tags": memory_tags,
        "create_time": datetime.now().isoformat(),
    }
    memories.append(memory)
    save_memories()    #调用存储函数写入json

    result = (
        f"记忆保存成功！memory_id={memory['memory_id']}\n"
        f"分类：{category}\n"
        f"日期：{memory['event_date'] or '未识别'}\n"
        f"标签：{', '.join(memory_tags) or '无'}"
    )
    if analysis_failed:
        result += "\n注意：大模型分析失败，分类和关键词使用默认值；错误已记录到服务端日志。" 
    return result   #返回提示文字

#有标签按照标签筛选记忆（任意标签对应即可），没有标签返回全部记忆，标签不对返回提示词
@mcp.tool()
def list_memories(filter_tags: list[str] | None = None) -> str:
    """List memories, optionally matching any provided tag."""
    result = memories
    if filter_tags:
        result = [item for item in memories if any(tag in item.get("tags", []) for tag in filter_tags)]
    if not result:
        return "暂无匹配的记忆"
    
    return "\n---------\n".join(
        f"id:{item['memory_id']}\n内容:{item['content']}\n"
        f"分类:{item.get('category', '普通记忆')}\n日期:{item.get('event_date') or '未识别'}\n"
        f"标签:{item.get('tags', [])}\n时间:{item['create_time']}"
        for item in result   #把多条记忆拼接成文本返回
    )

#关键词模糊搜索
@mcp.tool()
def search_memories(keyword: str) -> str:
    """Search memories by content, category, or tag."""
    if not keyword.strip():
        return "错误：关键词不能为空"
    keyword = keyword.strip().lower()  #不区分大小写
    hits = [  #只要关键词在内容、分类、标签中出现即可匹配
        item for item in memories
        if keyword in item.get("content", "").lower()
        or keyword in item.get("category", "").lower()
        or any(keyword in tag.lower() for tag in item.get("tags", []))
    ]
    if not hits:
        return "没有搜索到匹配记忆"
    
    return "\n---------\n".join(
        f"id:{item['memory_id']}\n内容:{item['content']}\n"
        f"分类:{item.get('category', '普通记忆')}\n日期:{item.get('event_date') or '未识别'}\n"
        f"标签:{item.get('tags', [])}"
        for item in hits
    )

#凭唯一id删除记忆
@mcp.tool()
def delete_memory(memory_id: str) -> str:
    """Delete a memory by its ID."""
    global memories
    remaining = [item for item in memories if item["memory_id"] != memory_id]  #遍历全部记忆，筛选出没被删除的记忆组成新列表
    if len(remaining) == len(memories):
        return f"未找到 id={memory_id} 的记忆，删除失败"
    memories = remaining   
    save_memories()
    return f"成功删除记忆 {memory_id}"


if __name__ == "__main__":    #运行main.py时，启动mcp服务端
    logging.getLogger("mcp.server").setLevel(logging.CRITICAL)  #设置日志级别为CRITICAL（只显示严重错误）logger按级别（debug、info、warning、error、critical）
    mcp.run(transport="stdio")   #使用stdio通信方式，客户端和服务端通过终端收发json消息，不需要网络端口啥的，在本机运行
#sse走网络通信


#本记忆 MCP 服务端基于FastMCP与STDIO通信构建，将记忆数据持久化存储在本地JSON文件。
# 提供新增、列表查询、关键词检索、按 ID 删除四类工具；
# 利用 DeepSeek 大模型自动完成记忆分类与标签提取，正则解析中文自然语言日期，
# 并设计 API 异常降级机制，保证服务稳定运行，供 MCP 客户端调用。