import json
import time
import urllib.request
import urllib.error

# =====================================================
# Minnow or Monster - 网页 + 120 颗 LED 同步自动测试
# 每种情况持续 5 秒
# =====================================================

SERVER = "http://127.0.0.1:8080"
PLAY_SECONDS = 5.0
UPDATE_INTERVAL = 0.5

# 每个重量持续 5 秒。
# 请根据你当前 app.js 的重量区间调整这些示例值。
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
    payload = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(
        SERVER + path,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def main():
    started = False
    try:
        print("=" * 55)
        print("Minnow or Monster：网页 + LED 自动模拟测试")
        print(f"每个情况 {PLAY_SECONDS:.0f} 秒，共 {len(TEST_CASES)} 个情况")
        print("请保持展台网页打开。按 Ctrl+C 可以中断。")
        print("=" * 55)

        result = post_json("/api/simulate/start")
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "无法启动模拟模式"))
        started = True
        print("模拟模式已启动。")

        for number, (name, kg) in enumerate(TEST_CASES, start=1):
            print(f"\n[{number}/{len(TEST_CASES)}] {name} — {kg} kg")

            # 每 0.5 秒更新一次模拟读数，让前端继续收到新的采样序号。
            # 该重量总共保持 5 秒；灯带使用 app.py 现有平滑动画。
            deadline = time.monotonic() + PLAY_SECONDS
            while time.monotonic() < deadline:
                result = post_json("/api/simulate/weight", {"kg": kg})
                remaining = deadline - time.monotonic()
                time.sleep(min(UPDATE_INTERVAL, max(0, remaining)))

        print("\n所有情况测试完毕。")

    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，正在停止测试……")
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"\n连接 Flask 失败：{exc}")
        print("请确认 app.py 已运行，地址和端口正确。")
    except Exception as exc:
        print(f"\n测试未能完成：{exc}")
    finally:
        if started:
            try:
                result = post_json("/api/simulate/stop")
                print(result.get("message", "模拟测试已停止。"))
            except Exception as exc:
                print(f"停止模拟接口失败：{exc}")
                print("如有需要，请在浏览器或终端手动 POST /api/stop。")


if __name__ == "__main__":
    main()
