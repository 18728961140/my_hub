"""
日志工具模块

作用:
    为项目提供统一的日志记录器(Logger),把带时间、级别、来源模块的
    日志输出到控制台,替代零散的 print 调试,方便排查问题。

使用方式:
    from utils.logger import setup_logger

    logger = setup_logger("chat_router")   # 每个模块建一个自己的日志器
    logger.info("收到请求")                 # 普通信息
    logger.warning("xxx 失败")             # 警告
    logger.error("xxx 异常")               # 错误

设计要点:
    - 基于 Python 标准库 logging,无需安装第三方依赖;
    - 同一个 name 只会有一个 logger 实例,重复调用不会重复添加 handler,
      避免日志重复打印;
    - 日志级别从低到高:DEBUG < INFO < WARNING < ERROR < CRITICAL,
      低于 logger 设定级别的日志会被过滤掉。
"""

import logging


def setup_logger(name: str = "leave_system") -> logging.Logger:
    """
    创建(或获取)一个配置好的日志记录器。

    参数:
        name: 日志记录器名称。
              - 同一个 name 在任何地方获取到的都是同一个 logger 实例;
              - 建议按模块名传入(如 "graph.nodes"、"api.chat_router"),
                这样日志里能看出是哪段代码输出的;
              - 默认值 "leave_system" 是历史遗留命名,可按需改成项目名。

    返回:
        logging.Logger 对象,可直接调用 .debug / .info / .warning / .error 等方法。
    """

    # ----------------------------------------------------------
    # 1. 获取(或创建)Logger 实例
    # ----------------------------------------------------------
    # logging.getLogger(name):
    #   - name 相同 → 返回同一个 logger 实例(全局复用,不会重复创建);
    #   - name 不同 → 各自独立,互不影响;
    #   - 不传 name 则返回根 logger(root),一般不建议直接使用。
    # 这里把"获取"和"配置"放在同一个函数里,保证任何地方调用
    # 都能拿到一个配置好的实例。
    logger = logging.getLogger(name)

    # ----------------------------------------------------------
    # 2. 设置日志器的最低输出级别
    # ----------------------------------------------------------
    # logger.setLevel(DEBUG):
    #   - 表示"这个 logger 只处理 DEBUG 及以上级别"的日志;
    #   - 级别从低到高:DEBUG < INFO < WARNING < ERROR < CRITICAL;
    #   - 低于该级别的日志会被直接丢弃(例如设为 INFO 后,debug 不输出);
    #   - 生产环境通常改成 INFO,减少无意义的调试输出。
    logger.setLevel(logging.DEBUG)

    # ----------------------------------------------------------
    # 3. 防止重复添加 Handler(关键)
    # ----------------------------------------------------------
    # logger.handlers:该 logger 已绑定的输出处理器列表。
    # 由于同一个 logger 实例是全局复用的,如果每次调用 setup_logger
    # 都无条件 addHandler,第二次调用时就会多出一个 handler,
    # 导致同一条日志被打印两遍甚至更多。
    # 因此先检查"是否已有 handler",有就直接复用,不再重复添加。
    if not logger.handlers:
        # ------------------------------------------------------
        # 3.1 创建 StreamHandler:把日志输出到控制台
        # ------------------------------------------------------
        # StreamHandler 默认输出到 stderr(标准错误流),
        # 也可以写成 StreamHandler(sys.stdout) 指定输出到标准输出。
        handler = logging.StreamHandler()

        # ------------------------------------------------------
        # 3.2 设置 handler 自身的最低输出级别
        # ------------------------------------------------------
        # handler 还有一级独立过滤:即使 logger 允许 DEBUG,
        # 若这里设为 INFO,DEBUG 日志依旧不会输出。
        # 两级配合:logger 控制"产生哪些级别",handler 控制"输出哪些级别"。
        handler.setLevel(logging.DEBUG)

        # ------------------------------------------------------
        # 3.3 设置日志格式 Formatter
        # ------------------------------------------------------
        # 格式化模板中的占位符含义:
        #   %(asctime)s    → 日志产生的时间(配合 datefmt 自定义格式)
        #   %(levelname)s  → 日志级别(DEBUG/INFO/WARNING/ERROR/CRITICAL)
        #   %(name)s       → logger 名称(即传入的 name,方便定位来源)
        #   %(message)s    → 实际要打印的日志内容
        # 输出效果示例:
        #   [2026-09-01 10:30:00] [INFO] [graph.nodes] 节点执行完成
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"  # 时间显示为 年-月-日 时:分:秒
        )

        # ------------------------------------------------------
        # 3.4 把格式器挂到 handler 上
        # ------------------------------------------------------
        # 一个 handler 只能绑定一个 formatter,
        # 它负责把日志记录(LogRecord)格式化成最终输出的字符串。
        handler.setFormatter(formatter)

        # ------------------------------------------------------
        # 3.5 把 handler 挂到 logger 上
        # ------------------------------------------------------
        # 一个 logger 可以挂多个 handler(例如同时输出到控制台和文件),
        # 日志会广播给所有已绑定的 handler。
        logger.addHandler(handler)

    # ----------------------------------------------------------
    # 4. 返回配置好的 logger 给调用方使用
    # ----------------------------------------------------------
    return logger


if __name__ == "__main__":
    # 直接运行本文件可测试日志效果:python -m utils.logger
    demo_logger = setup_logger("demo")
    demo_logger.debug("这是 DEBUG 级别日志")
    demo_logger.info("这是 INFO 级别日志")
    demo_logger.warning("这是 WARNING 级别日志")
    demo_logger.error("这是 ERROR 级别日志")
