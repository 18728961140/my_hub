"""
节点模块（LangGraph 的"办事人员"）

LangGraph 把工作流拆成一个个 Node（节点），每个节点就是一个普通 Python 函数：
  输入：当前 State（整个对话的共享状态）
  处理：调用大模型、检索知识库、读写记忆等
  输出：一个字典，表示要更新到 State 上的字段

本文件有 8 个节点：
  1. classify_node      —— 聊天状态判断（闲聊 / 倾诉 / 危机 / 求助）
  2. crisis_check_node  —— 危机二次检测（关键词快检 + LLM 复核）
  3. crisis_respond_node—— 危机干预：安抚 + 提供危机热线
  4. consult_talk_node  —— 知识问答：求助类问题直接检索回答
  5. small_talk_node    —— 闲聊：直接回答，不检索
  6. deep_talk_node     —— 深度倾诉：检索知识 + 结合记忆回答（可循环调用工具）
  7. reflect_node       —— 反思：回答质量自评，不合格重答一次
  8. remember_node      —— 记忆提取：倾诉结束后自动把重要信息存进长期记忆
"""

import json
import logging
import re
from typing import Literal, get_origin

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore
from pydantic import BaseModel, Field

from graph.state import ChatState
from models.llm import qwen_llm
from retriever.bm25_retriever import retrieve
from tools.memory_tools import save_memory
from tools.rag_tools import retrieve_knowledge

logger = logging.getLogger(__name__)


# ============================================================
# 1. 聊天状态判断节点
# ============================================================

class Intent(BaseModel):
    """用 Pydantic 定义"结构化的判断结果"。

    with_structured_output 会强制大模型按这个格式输出，
    我们拿到的就是可靠的结构化数据，而不是自由文本。
    Literal["闲聊","倾诉","危机","求助"] 表示只能取这四个值之一。
    """

    intent: Literal["闲聊", "倾诉", "危机", "求助"] = Field(
        description="判断用户发言属于闲聊、倾诉、危机还是求助"
    )


def _candidate_shapes(data, model_class) -> list:
    """按目标 schema 生成"可能正确的载荷形态"，供逐个尝试校验。

    模型输出的文本形态不稳定，常见三种：
      1. 直接是对象            -> {"intent": "倾诉"}（原样可用）
      2. 对象被包成数组         -> [{"intent": "倾诉"}]（取其中一个元素）
      3. MemoryExtract 的 items 内容直接成了顶层数组
         -> [{"category": ...}, ...]（需包回 {"items": [...]}）

    # 目标：Intent，期望输出 {"intent": "倾诉"}
    data = [{"intent": "倾诉"}]     # 形态 2：外层数组 = 多余包装
    # 拆开取元素 -> {"intent": "倾诉"} 校验通过

    # 目标：MemoryExtract，期望输出 {"items": [{...}, ...]}
    data = [{"category": "情绪", "content": "焦虑"}, {"category": "背景", "content": "程序员"}]
    # 形态 3：这个数组本来就是 items 的内容，缺的是 {"items":} 外壳
    # 包回去 -> {"items": [...]} 校验通过
    """
    if isinstance(data, dict):
        return [data]                # 形态 1：直接当对象校验
    if not isinstance(data, list):
        return []                    # 非对象非数组：没有可尝试的形态
    shapes = []
    # 形态 3：目标 schema 含 list 字段（如 MemoryExtract.items）时，
    # 顶层数组可能是该字段的内容，包一层再校验
    for field_name, field_info in model_class.model_fields.items():
        if get_origin(field_info.annotation) is list:
            shapes.append({field_name: data})
    # 形态 2：逐个元素试，直到找到能通过校验的那一个
    shapes.extend(item for item in data if isinstance(item, dict))
    return shapes


def _parse_model_json(text: str, model_class):
    """把模型文本解析成指定的 Pydantic 模型（schema 感知 + 多形态容错）。

    运行中发现：大模型偶尔把结构化结果包成数组（[{"intent": "倾诉"}]），
    或把 MemoryExtract 的 items 内容直接输出成顶层数组，或带 ```json
    代码块和前后缀文字。统一走"文本提取 + 多形态候选校验"兜底，
    而不是见到数组就盲取第一个元素（那会让 MemoryExtract 丢记忆）。
    """
    data = _extract_json(text)
    if data is None:                   # 提取失败（空/乱码）
        return None
    for candidate in _candidate_shapes(data, model_class):
        try:
            return model_class.model_validate(candidate)  # 这个形态校验成功
        except Exception:              # 校验失败，试下一个形态
            continue
    return None                        # 所有形态都失败


# 原生通道 + 文本兜底都失败时的重试提示（顶层必须是对象，不能是数组/代码块）
_STRUCTURED_RETRY_HINT = (
    "上次输出不是合法的 JSON 对象（可能包成了数组、带了 ```json 代码块"
    "或解释文字）。请只输出一个符合要求的 JSON 对象，"
    "顶层不要用数组包裹，不要代码块，不要任何解释。"
)


def _invoke_structured(
    messages: list,
    model_class,
    *,
    retries: int = 0,
) -> object:
    """优先走原生 json_mode 通道，失败退回文本容错解析，可选带提示重试。

    冒烟测试结论（qwen3.8-27b）：
      - json_mode 通道 6/6 成功，function_calling 只有 5/6——
        空结果时模型可能直接输出文本 {"items": []} 而不发起工具调用，
        所以这里默认 json_mode，function_calling 留作备选。
      - include_raw 能拿到 parsing_error，解析失败时再对 raw.content
        走一次 _parse_model_json 文本兜底（兼容数组/代码块等历史脏输出）。

    返回值：model_class 实例；所有尝试都失败返回 None，由调用方按节点降级。
    """
    chain = qwen_llm.with_structured_output(
        model_class, method="json_mode", include_raw=True
    )
    current_messages = messages
    for attempt in range(retries + 1):
        raw_result = chain.invoke(current_messages)
        parsed = raw_result.get("parsed")
        if parsed is not None:
            return parsed
        # 原生通道解析失败：退化到"文本提取 + 多形态校验"再救一次
        raw = raw_result.get("raw")
        content = getattr(raw, "content", "") if raw is not None else ""
        parsed = _parse_model_json(content or "", model_class)
        if parsed is not None:
            return parsed
        # 观测层：记录失败样本（截断内容，便于统计格式失败率）
        logger.warning(
            "结构化输出解析失败（第 %d 次）：schema=%s, content=%r",
            attempt + 1,
            model_class.__name__,
            (content or "")[:120],
        )
        if attempt < retries:
            # 把格式错误反馈回模型，给它一次纠错机会
            current_messages = current_messages + [
                SystemMessage(content=_STRUCTURED_RETRY_HINT)
            ]
    return None


def _last_user_message(state: ChatState) -> str:
    """从消息历史里取最后一条用户消息的纯文本（供"单句任务"使用）。

    注意：回答/分类类节点已改用 _recent_context 注入多轮上下文，
    本函数只服务"只需要最新一句"的子任务：
      - crisis_check 的关键词快检（不能拿旧历史去扫危机词，避免误判）；
      - consult_talk 的 BM25 检索 query；
      - reflect 的质量评估配对（最新提问 vs 本次回答）；
      - remember 的寒暄短路与记忆提取。
    messages 是完整对话历史（包含之前的 AI 回复），这里从后往前
    找到最新一条用户消息返回。
    """
    for message in reversed(state["messages"]):  # 从后往前遍历
        if isinstance(message, HumanMessage):    # 遇到用户消息就返回
            return message.content
    return ""


# ============================================================
# 1.1 历史上下文工具（短期记忆优化：本轮新增）
# ============================================================

def _context_chars(messages: list) -> int:
    """统计消息列表的总字符数（用于超长截断判断）"""
    total = 0
    for message in messages:
        content = message.content
        total += len(content) if isinstance(content, str) else len(str(content))
    return total


def _recent_context(
    state: ChatState,
    rounds: int = 10,
    max_chars: int = 6000,
) -> list:
    """从完整历史里截取"最近 rounds 轮"对话（含当前提问，结尾即最新发言）。

    短期记忆优化的核心工具：
      1. 以 HumanMessage 为一轮的分界，整轮截断，不拆散
         AI 的工具调用（AIMessage.tool_calls）与其结果（ToolMessage）的配对；
      2. 先按轮数截断，再按字符预算从最早的整轮开始丢，
         保证最后至少还剩一轮（当前提问不会被丢掉）；
      3. 返回列表的结尾就是用户最新提问，节点把它拼在 SystemMessage 之后
         直接调用模型，不再单独重复注入。
    """
    # 复制消息历史，避免影响原列表
    msgs = list(state["messages"])

    # ---------- 第一步：按"轮数"截断，只留最近的 rounds 轮 ----------
    # 起点默认 0：用户消息不足 rounds 条时就保留全部
    start = 0
    # 从末尾往回数，已经遇到了几条用户消息
    human_seen = 0
    # range(len-1, -1, -1) = 从最后一个下标倒序走到 0
    for i in range(len(msgs) - 1, -1, -1):
        # 每条 HumanMessage 是一轮对话的开头
        if isinstance(msgs[i], HumanMessage):
            # 倒着数到一条，就多算一轮
            human_seen += 1
            # 数满 rounds 条，就锁定了"最近第 rounds 轮"的起点
            if human_seen >= rounds:
                start = i
                break  # 起点已确定，不必继续往前扫
    # 从该轮起点截到末尾：含当前提问及其后的全部 AI 回复
    kept = msgs[start:]

    # ---------- 第二步：按"字符数"截断，仍超长就丢最旧的一整轮 ----------
    # 字符数超预算，且还有可丢的轮次时，循环继续
    while kept and _context_chars(kept) > max_chars:
        # 先找当前最旧一轮的开头（kept 里的第一条 HumanMessage）
        first_human = None
        # 从头往后遍历 kept
        for i, message in enumerate(kept):
            # 遇到用户消息就是最旧一轮的起点
            if isinstance(message, HumanMessage):
                first_human = i
                break
        # 没有用户消息（异常数据），无从按轮丢弃
        if first_human is None:
            break
        # 再找第二条 HumanMessage，用它划出"最旧一整轮"的结束边界
        next_human = None
        # 从最旧一轮开头的下一条开始继续找
        for i in range(first_human + 1, len(kept)):
            # 遇到的 HumanMessage 就是下一轮的开头
            if isinstance(kept[i], HumanMessage):
                next_human = i
                break
        # 找不到下一轮，说明只剩最后一轮，不能再丢（宁可超长）
        if next_human is None:
            break
        # 从下一轮开头切片，等于丢掉最旧的那一整轮（用户提问 + 对应回复）
        kept = kept[next_human:]
    return kept


def classify_node(state: ChatState) -> dict:
    """聊天状态判断：把用户的话分成"闲聊/倾诉/危机/求助"四类。

    短期记忆优化：注入最近 3 轮对话（含当前提问），
    让"后来呢？""我该怎么办"这类追问能结合前文判断，
    而不是只看孤立的最新一句话。
    返回 {"intent": ...} 会更新 State 的 intent 字段，
    图里的条件边（conditional edge）根据它决定走闲聊还是深度倾诉。
    """
    # 历史上下文（最近 3 轮，超长限制 2000 字）
    context = _recent_context(state, rounds=3, max_chars=2000)

    messages = [
        SystemMessage(content="""你是一个心理咨询陪伴系统的状态判断器。
你会看到用户最近几轮的对话记录，最后一条是用户的最新发言。
请根据最新发言、并结合上下文，判断属于哪一类：
- 闲聊：日常问候、普通话题、与心理困扰无关的轻松聊天。
- 倾诉：涉及情绪困扰、心理压力、情感问题、焦虑、抑郁、人际冲突等，需要心理支持或陪伴。
- 危机：涉及自伤、自杀、轻生等严重心理危机，需要紧急干预。
- 求助：明确询问心理知识、应对方法、专业帮助渠道等知识性问题。
只输出一个 JSON 对象，例如 {"intent": "倾诉"}；
不要数组、不要代码块、不要任何解释。"""),
    ] + context

    # 原生 json_mode 通道 + 文本容错解析（见 _invoke_structured 说明）
    result = _invoke_structured(messages, Intent)

    # 解析失败的兜底：按"倾诉"处理，走深度倾诉路径而不是让请求崩溃
    if result is None:
        result = Intent(intent="倾诉")
    return {"intent": result.intent}


# ============================================================
# 2. 危机检测与危机回应节点
# ============================================================

# 高危关键词快检表：命中任一关键词直接判定为危机（不依赖模型，最快最稳）
CRISIS_KEYWORDS = [
    "自杀", "想死", "不想活", "活不下去", "结束生命", "轻生",
    "自残", "割腕", "跳楼", "伤害自己", "遗书", "死了算了", "安眠药",
]

# 危机热线（写进提示词，让模型在回应中给出）
CRISIS_HOTLINES = "全国统一心理援助热线：12356；希望24热线：400-161-9995"


class CrisisRisk(BaseModel):
    """危机风险评估结果（结构化输出）"""

    risk: Literal["high", "normal"] = Field(
        description="是否存在自伤/自杀等严重危机风险，high=存在，normal=不存在"
    )


def _has_crisis_keywords(text: str) -> bool:
    """关键词快检：命中高危词直接返回 True（响应最快，不依赖模型）"""
    return any(keyword in text for keyword in CRISIS_KEYWORDS)


def crisis_check_node(state: ChatState) -> dict:
    """危机检测节点：关键词快检 + LLM 复核 双通道。

    先做零成本的关键词快检；没命中再由大模型做语义判断，
    兼顾"响应速度"和"召回率"。
    """
    last_input = _last_user_message(state)

    # 通道一：关键词快检
    if _has_crisis_keywords(last_input):
        return {"risk_level": "high"}

    # 通道二：LLM 语义复核（注入最近 2 轮对话作参考）
    context = _recent_context(state, rounds=2, max_chars=1500)
    messages = [
        SystemMessage(content="""你是一个心理危机风险评估器。
你会看到用户最近几轮对话记录，最后一条是用户的最新发言。
请根据最新发言、并结合上下文，判断是否存在自伤、自杀等严重心理危机风险：
- high：明确或强烈暗示想伤害自己、结束生命，或处于极度绝望中
- normal：没有明显危机信号
只输出一个 JSON 对象，例如 {"risk": "high"}；
不要数组、不要代码块、不要任何解释。"""),
    ] + context

    # 原生 json_mode 通道 + 文本容错解析；危机复核允许带提示重试一次
    result = _invoke_structured(messages, CrisisRisk, retries=1)
    # 解析失败按 high 兜底（fail-closed）：宁可误报进危机通道，
    # 也不能让真实危机因为格式问题漏进普通倾诉
    if result is None:
        result = CrisisRisk(risk="high")
    return {"risk_level": result.risk}


def crisis_respond_node(state: ChatState) -> dict:
    """危机回应节点：安抚 + 提供危机热线（高危时走这里，不进入普通对话）

    短期记忆优化：注入最近 10 轮对话，回应时可温和呼应前文；
    但最新一句的危机信号始终是最高优先级。
    """
    context = _recent_context(state, rounds=10, max_chars=6000)

    messages = [
        SystemMessage(content=f"""你是一位专业的心理危机干预助手。用户正处于严重心理危机中。
以下是用户最近几轮对话记录，最后一条是用户的最新发言；
请优先处理最新发言中的危机信号，必要时可温和呼应前文。
请以温暖、坚定、不评判的方式回应，务必做到：
1. 表达关心与陪伴，让用户感到被听见、被重视；
2. 明确建议立即联系专业帮助，并给出以下热线：
   {CRISIS_HOTLINES}
3. 不要空洞安慰，不要评判用户的感受。
请直接输出给用户的回应。"""),
    ] + context

    answer = qwen_llm.invoke(messages)
    return {"messages": [AIMessage(content=answer.content)]}


# ============================================================
# 3. 闲聊节点
# ============================================================

def small_talk_node(state: ChatState) -> dict:
    """闲聊：直接用大模型轻松回应。

    不检索知识库、不读长期记忆（长期记忆模块后续再扩展）。
    短期记忆优化：注入最近 10 轮对话，闲聊也能接住上文——
    例如用户前面说过"我叫小周"，再问"我是谁"时可以结合前文回答。
    """
    context = _recent_context(state, rounds=10, max_chars=6000)

    messages = [
        SystemMessage(content="""你是一个温暖、友好的心理陪伴助手。用户在和你闲聊。
你会看到最近几轮对话记录，请自然承接上文、保持语气亲切、口径一致，
并适当关心对方。不要提及"对话历史""记忆"这类系统概念。"""),
    ] + context

    answer = qwen_llm.invoke(messages)

    # 把 AI 的回答包成 AIMessage 放进 messages，
    # add_messages 规则会自动把它追加到对话历史末尾（供下一轮参考）
    return {"messages": [AIMessage(content=answer.content)]}


# ============================================================
# 4. 知识问答节点（求助类）
# ============================================================

def consult_talk_node(state: ChatState) -> dict:
    """知识问答：用户明确问心理知识/应对方法时，直接检索知识库回答。

    与 deep_talk 的区别：
      - 不注入长期记忆、不绑定工具循环（更轻、更快）；
      - 检索是"确定性"的：直接用 BM25 查，再让模型基于结果回答。
    短期记忆优化：注入最近 10 轮对话，支持"我刚刚说的方法……"这类追问。
    """
    query = _last_user_message(state)
    docs = retrieve(query, k=5)
    knowledge = "\n\n".join(doc.page_content for doc in docs) or "暂无相关资料"
    context = _recent_context(state, rounds=10, max_chars=6000)

    messages = [
        SystemMessage(content=f"""你是一个心理咨询知识问答助手。
请仅依据以下知识库内容回答用户问题，回答要准确、温和；
知识库没有的内容就如实说明，不要编造。
你会看到用户最近几轮对话记录，用户可能引用之前提到的信息，
请结合上下文理解提问，但回答依据仍以知识库内容为主。

知识库：
{knowledge}"""),
    ] + context

    answer = qwen_llm.invoke(messages)
    return {"messages": [AIMessage(content=answer.content)]}


# ============================================================
# 5. 深度倾诉节点（核心节点）
# ============================================================

# 深度倾诉可用的工具列表：
#   retrieve_knowledge —— BM25 检索本地心理咨询知识文档
#   save_memory        —— 把用户的重要信息写入长期记忆
# 注意：长期记忆的"读取"不做成工具，而是在 deep_talk_node 里直接注入提示词，
# 这样更可靠（不会出现模型忘了调用工具而导致"失忆"）。
deep_talk_tools = [retrieve_knowledge, save_memory]

# bind_tools：把工具"注册"给大模型。
# 之后大模型回答时会"看到"这些工具，并自己决定：直接回答？还是调用哪个工具？
deep_talk_llm = qwen_llm.bind_tools(deep_talk_tools)


def _format_memories(items) -> str:
    """把长期记忆条目格式化成一串文字，方便塞进系统提示词。"""
    if not items:
        return "暂无"
    lines = []
    for item in items:
        # item.value 可能是对象或字典，两种都兼容
        value = item.value if hasattr(item, "value") else item.get("value", {})
        lines.append(f"- [{item.key}] {value.get('content', '')}")
    return "\n".join(lines)


def deep_talk_node(state: ChatState, config: RunnableConfig, store: BaseStore) -> dict:
    """深度倾诉节点。

    LangGraph 会自动向节点注入额外参数（不用自己传）：
      config：运行配置，包含 thread_id（会话ID）和 user_id（用户ID）
      store ：长期记忆仓库（SqliteStore 实例）

    执行逻辑：
      1. 从 store 读取该用户的长期记忆，拼进系统提示词（确定性注入）
      2. 把"系统提示词 + 完整对话历史"交给绑定了工具的模型
      3. 模型可能返回普通回答（流程结束），也可能返回工具调用请求（进 tools 节点）
    """
    # 从 config 取用户 ID，用于隔离不同用户的长期记忆
    # limit:最多读取20条
    user_id = config["configurable"].get("user_id", "anonymous")
    memories = store.search((user_id, "memory"), limit=20)

    system_prompt = SystemMessage(
        content=f"""你是一个专业、温暖的心理陪伴助手。用户正在向你深度倾诉。
以下是该用户的长期记忆（来自之前的对话，请参考，不要提及"长期记忆"这类系统概念）：
{_format_memories(memories)}

请遵循以下步骤：
1. 调用 retrieve_knowledge 检索本地心理咨询知识库中的相关知识点；
2. 结合检索到的知识、用户记忆和你的专业判断，以温暖、专业、不评判的方式回应。
涉及严重心理危机（自伤、自杀等）时，请明确建议寻求专业帮助或拨打危机干预热线。"""
    )

    # 系统提示词 + 全部对话历史（包括之前几轮，这就是短期记忆发挥作用的地方）
    messages = [system_prompt] + list(state["messages"])

    # 如果反思节点判定上一版回答不合格，把改进建议也传给模型
    if state.get("reflect_feedback"):
        messages.append(
            SystemMessage(
                content=(
                    "你上一版回答未通过质量检查，请根据以下建议重新回答，"
                    f"给出更温暖、更专业的版本：\n{state['reflect_feedback']}"
                )
            )
        )

    result = deep_talk_llm.invoke(messages)

    update = {"messages": [result]}
    # 统计工具调用轮次：超过上限时由条件边强制结束，防止死循环
    if getattr(result, "tool_calls", None):
        update["tool_rounds"] = state.get("tool_rounds", 0) + 1
    return update


# ============================================================
# 6. 反思节点（回答质量自评）
# ============================================================

MAX_REFLECT_RETRIES = 1  # 最多允许重答次数


class Reflection(BaseModel):
    """回答质量评估结果（结构化输出）"""

    score: int = Field(ge=0, le=10, description="回答质量评分（0-10）")
    passed: bool = Field(description="是否通过质量检查")
    feedback: str = Field(description="未通过时的具体改进建议")


def _extract_json(text: str):
    """从模型输出里提取 JSON 数据，兼容代码块、前后缀文字等情况"""
    text = text.strip()
    # 去掉 ```json ... ``` 代码块标记
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    # 1) 整段就是 JSON
    try:
        return json.loads(text)
    except Exception:
        pass
    # 2) 从第一个 { 到最后一个 } 截取（对象）
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    # 3) 从第一个 [ 到最后一个 ] 截取（数组）
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    return None


def reflect_node(state: ChatState) -> dict:
    """反思节点：对 deep_talk 的回答做质量自评，不合格则带着建议重答一次。

    流程：
      1. 取最后一条 AI 回答；
      2. 让模型按（温暖度/专业性/安全性）打分并判断是否通过；
      3. 未通过且未超过重试上限 -> 删掉旧回答，置 reflect_pending=True，
         带着 feedback 回到 deep_talk 重新生成；
      4. 通过或重试次数用尽 -> 清空反馈，继续走 remember。
    """
    # 取最后一条 AI 回答
    last_ai = None
    for message in reversed(state["messages"]):
        if isinstance(message, AIMessage):
            last_ai = message
            break
    if last_ai is None or not getattr(last_ai, "content", ""):
        return {"reflect_pending": False}

    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个心理咨询回答质量评估器。
请评估助手对用户问题的回答，从三个方面打分：
- 温暖度：语气是否温暖、共情、不评判
- 专业性：是否专业、有依据、给出可操作建议
- 安全性：是否避免医学诊断、是否在危机场景给出求助渠道
输出 0-10 分，并判断是否通过（passed）。未通过时给出具体改进建议（feedback）。
只输出一个 JSON 对象，格式如 {"score": 8, "passed": true, "feedback": "建议"}；
不要数组、不要代码块、不要任何解释。"""),
        ("human", "用户问题：{question}\n\n助手回答：{answer}"),
    ])
    # 原生 json_mode 通道 + 文本容错解析；
    # 自评失败按"通过"兜底，避免格式问题导致无限重答
    result = _invoke_structured(
        prompt.format_messages(
            question=_last_user_message(state),
            answer=last_ai.content,
        ),
        Reflection,
    )
    if result is None:
        result = Reflection(score=10, passed=True, feedback="")

    retries = state.get("reflect_retries", 0)
    if not result.passed and retries < MAX_REFLECT_RETRIES and last_ai.id:
        # 不合格且未超过上限：删掉旧回答，带上建议回 deep_talk 重答
        return {
            "reflect_retries": retries + 1,
            "reflect_pending": True,
            "reflect_feedback": result.feedback,
            "messages": [RemoveMessage(id=last_ai.id)],
        }

    # 通过或重试次数用尽：清空反馈，继续收尾
    return {"reflect_pending": False, "reflect_feedback": ""}


# ============================================================
# 7. 记忆提取节点（深度倾诉回答完之后的收尾）
# ============================================================

class MemoryItem(BaseModel):
    """一条记忆：类别 + 内容"""

    category: str = Field(description="信息类别，如：背景、情绪、经历、偏好")
    content: str = Field(description="信息内容")


class MemoryExtract(BaseModel):
    """
    一次提取的结果：可能有多条记忆
    items"一次提取出的记忆条目列表"
    Field()是 Pydantic 的字段函数,平时用来加描述(Field(description="..."))、加约束;放在 = 后面表示"同时把默认值也交给 Pydantic 管"。
    default_factory=list 意思是:每次创建实例时,调用 list() 现场生成一个新的空列表,而不是共用一个写死的列表。
    """

    items: list[MemoryItem] = Field(default_factory=list)


# 无需记忆的寒暄/超短回应（用于 remember 短路，省一次无效的 LLM 提取）
_TRIVIAL_REPLIES = {
    "嗯", "好", "哦", "嗯嗯", "好的", "好的谢谢", "谢谢", "感谢",
    "哈哈", "知道了", "再见", "拜拜", "没事了",
}


def _is_trivial_message(text: str) -> bool:
    """判断用户发言是否属于无需记忆的寒暄/超短回应"""
    t = text.strip()
    return (not t) or (len(t) <= 1) or (t in _TRIVIAL_REPLIES)


def remember_node(state: ChatState, config: RunnableConfig, store: BaseStore) -> dict:
    """记忆提取节点。

    作用：深度倾诉回答完成后，让大模型把用户这次提到的重要信息
    提炼成结构化记忆，写入长期记忆（SqliteStore）。
    这样下次用户再来（哪怕换了会话），助手依然记得他的情况。

    这是"确定性兜底"：不依赖大模型在对话中主动调用 save_memory，
    只要走了深度倾诉，就一定会尝试存记忆。
    """
    from datetime import datetime

    user_id = config["configurable"].get("user_id", "anonymous")
    last_input = _last_user_message(state)

    # 短路：纯寒暄/超短回应没有可提取的信息，直接跳过 LLM 提取
    if _is_trivial_message(last_input):
        return {}

    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个心理咨询系统的记忆提取器。
从用户的发言中，提取值得长期记住的用户信息，例如：
- 背景：姓名、身份、职业、家庭情况等
- 情绪：长期或反复出现的情绪状态
- 经历：重要的人生经历或事件
- 偏好：喜好、习惯等
只提取明确、有价值的信息；没有则返回空列表。
只输出一个 JSON 对象，格式如 {"items": [{"category": "背景", "content": "..."}]}；
不要数组、不要代码块、不要任何解释。"""),
        ("human", "{input}"),
    ])

    # 原生 json_mode 通道 + 文本容错解析；记忆提取允许重试一次
    result = _invoke_structured(
        prompt.format_messages(input=last_input), MemoryExtract, retries=1
    )
    if result is None:
        result = MemoryExtract(items=[])

    # 空结果短路：没有提取到任何记忆，直接结束
    if not result.items:
        return {}

    # 把每条记忆写入 store：
    #   namespace = (user_id, "memory") -> 按用户隔离
    #   key       = category            -> 同类信息存同一个 key（新值覆盖旧值）
    for item in result.items:
        store.put(
            (user_id, "memory"),
            key=item.category,
            value={
                "content": item.content,
                "timestamp": datetime.now().isoformat(),
            },
        )

    # 本节点不需要更新 State，返回空字典即可
    return {}
