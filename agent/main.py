import os
import sys

# 随包 Python 使用 embeddable 发行版时存在 python3xx._pth，
# 该模式不会把脚本所在目录加入 sys.path，这里显式补上，保证 import registry 可用。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maa.agent.agent_server import AgentServer
from maa.tasker import Tasker

import registry


def main():
    # Agent 子进程的日志写到 ./debug（相对 interface.json 所在目录）
    Tasker.set_log_dir("./debug")
    registry.register_all()

    if len(sys.argv) < 2:
        print("Usage: python main.py <socket_id>")
        print("socket_id is provided by AgentIdentifier.")
        sys.exit(1)

    socket_id = sys.argv[-1]

    AgentServer.start_up(socket_id)
    AgentServer.join()
    AgentServer.shut_down()


if __name__ == "__main__":
    main()
