"""
状态定义模块

LangGraph 最核心的概念：State（状态）。
状态可以理解为整个对话工作流的"共享工作台"：
  - 所有节点（Node）都能读取它
  - 节点处理完把结果写回它
  - 写回的结果自动传给下一个节点

本项目状态 = 对话消息列表(messages) + 聊天状态判断结果(intent)
"""

from langgraph.graph import MessagesState


class ChatState(MessagesState):
    """
    自定义聊天状态。

    继承 MessagesState，自带 messages 字段：
      messages: 对话消息列表（HumanMessage 用户消息 /
               AIMessage AI消息 / ToolMessage 工具结果）

    MessagesState 内部给 messages 配了 add_messages 合并规则（reducer）：
    普通字段更新是"覆盖"，messages 是"追加"——
    新消息永远加在列表末尾，旧消息不丢，这样对话历史才能累积。
    这就是多轮对话"短期记忆"的数据基础。

    额外增加的字段：
      intent:           聊天状态判断结果（闲聊/倾诉/危机/求助），由 classify 写入
      tool_rounds:      深度倾诉的工具调用轮次计数（防止死循环）
      risk_level:       危机检测结果（high=高危 / normal=正常）
      reflect_retries:  反思节点已重答次数（限制最多重答几次）
      reflect_pending:  反思判定"需要重答"的标记（True 则回到 deep_talk）
      reflect_feedback: 反思给出的改进建议（传给 deep_talk 参考）
    """

    intent: str = "闲聊"
    tool_rounds: int = 0
    risk_level: str = "normal"
    reflect_retries: int = 0
    reflect_pending: bool = False
    reflect_feedback: str = ""
