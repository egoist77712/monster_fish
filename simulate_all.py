
import json
import time
import urllib.request
import urllib.error

# =====================================================
# Minnow or Monster - 自动测试所有称重情况
# 每种情况播放 5 秒
# =====================================================

SERVER = "http://127.0.0.1:8080"
PLAY_SECONDS = 5

# 每个重量对应一个测试情况
# 重量只是用于测试页面切换，不代表真实称重结果
TEST_CASES = [
    ("Goonch - Almost", 10),
    ("Goonch - Same", 50),
    ("American Paddlefish - Almost", 80),
    ("American Paddlefish - Same", 90),
    ("Arapaima - Almost", 120),
    ("Arapaima - Same", 175),
    ("Giant Barb - Almost", 225),
    ("Giant Barb - Same", 275),
    ("Beyond 300 kg", 310),
]


def post_json(path, data=None):
    """向 Flask 发送 POST 请求。"""
    body = json.dumps(data or {}).encode("utf-8")

    request = urllib.request.Request(
        SERVER + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=5) as response:
        result = response.read().decode("utf-8")
        return result


def set_weight(kg):
    """设置模拟重量，需要 Flask 模拟模式支持此接口。"""
    post_json("/api/weight", {"kg": kg})


def main():
    print("=" * 45)
    print("Minnow or Monster - 自动动画测试")
    print(f"每种情况播放 {PLAY_SECONDS} 秒")
    print("=" * 45)

    try:
        # 先设置第一种模拟重量
        first_name, first_kg = TEST_CASES[0]
        set_weight(first_kg)

        # 启动一次称重会话
        post_json("/api/button")

        for index, (name, kg) in enumerate(TEST_CASES, start=1):
            # 第一种情况已设置；其余情况更新模拟重量
            if index != 1:
                set_weight(kg)

            print(
                f"[{index}/{len(TEST_CASES)}] "
                f"{name} | {kg} kg | 播放 {PLAY_SECONDS} 秒"
            )

            time.sleep(PLAY_SECONDS)

        print("\n所有测试情况已播放完毕。")

    except urllib.error.HTTPError as e:
        print(f"\nHTTP 错误：{e.code}")
        print(e.read().decode("utf-8", errors="replace"))
        print("请确认 Flask 已启用模拟模式。")

    except urllib.error.URLError as e:
        print(f"\n无法连接 Flask：{e}")
        print("请确认 app.py 正在运行，端口是 8080。")

    except KeyboardInterrupt:
        print("\n测试已被手动中断。")

    finally:
        try:
            post_json("/api/stop")
            print("称重测试会话已停止。")
        except Exception:
            pass


if __name__ == "__main__":
    main()
