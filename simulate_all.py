import json
import time
import urllib.request
import urllib.error


# =========================================================
# Minnow or Monster - 自动重量模拟测试
#
# 1. 不读取真实电子秤
# 2. 每 0.2 秒更新一次模拟重量
# 3. 每个目标重量先渐变，再保持显示
# 4. 每次重量变化都会更新后端状态和 LED 目标
# 5. 测试结束后停止模拟模式
# =========================================================

SERVER = "http://127.0.0.1:8080"

UPDATE_INTERVAL = 0.2

# 每个重量渐变到目标所用的时间
RAMP_SECONDS = 1.5

# 到达目标后，保持页面显示的时间
HOLD_SECONDS = 3.5

MAX_WEIGHT_KG = 324.0

TEST_CASES = [
    ("Baby fish", 50),
    ("Goonch - Almost", 70),
    ("Goonch - Same", 75),
    ("Paddlefish - Almost", 80),
    ("Paddlefish - Same", 100),
    ("Arapaima - Almost", 120),
    ("Arapaima - Same", 200),
    ("Giant Barb - Almost", 250),
    ("Giant Barb - Same", 300),
    ("Beyond 300 kg", 310),
]


def post_json(path, data=None):
    """发送 POST JSON 请求。"""

    payload = json.dumps(data or {}).encode("utf-8")

    request_obj = urllib.request.Request(
        SERVER + path,
        data=payload,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request_obj,
        timeout=5,
    ) as response:

        raw = response.read().decode("utf-8")

        if raw:
            return json.loads(raw)

        return {}


def check_server():
    """检查 Flask 服务是否启动。"""

    with urllib.request.urlopen(
        SERVER + "/api/health",
        timeout=3,
    ) as response:

        return json.loads(
            response.read().decode("utf-8")
        )


def send_weight(weight):
    """提交一个模拟重量，并打印当前状态。"""

    result = post_json(
        "/api/simulate/weight",
        {"kg": round(weight, 2)},
    )

    if not result.get("ok"):
        raise RuntimeError(
            result.get(
                "error",
                "模拟重量更新失败",
            )
        )

    print(
        "\r重量: {:6.2f} kg | seq: {:5} | LED 目标: {:6.2f}/{}".format(
            result.get("kg", weight),
            result.get("seq", 0),
            result.get("led_target", 0),
            120,
        ),
        end="",
        flush=True,
    )

    return result


def ramp_weight(start_weight, target_weight):
    """
    在 RAMP_SECONDS 时间内逐渐改变重量。
    每 UPDATE_INTERVAL 秒发送一次新重量。
    """

    steps = max(
        1,
        int(round(RAMP_SECONDS / UPDATE_INTERVAL)),
    )

    for step in range(1, steps + 1):

        ratio = step / steps

        weight = (
            start_weight
            + (target_weight - start_weight) * ratio
        )

        send_weight(weight)

        if step < steps:
            time.sleep(UPDATE_INTERVAL)

    print()


def hold_weight(weight):
    """保持目标重量，让网页显示对应结果。"""

    deadline = time.monotonic() + HOLD_SECONDS

    while True:

        remaining = deadline - time.monotonic()

        if remaining <= 0:
            break

        send_weight(weight)

        remaining = deadline - time.monotonic()

        if remaining > 0:
            time.sleep(
                min(UPDATE_INTERVAL, remaining)
            )

    print()


def main():
    simulation_started = False
    current_weight = 0.0

    print("=" * 60)
    print("Minnow or Monster - 自动模拟测试")
    print("Flask 地址：{}".format(SERVER))
    print("重量更新间隔：{} 秒".format(UPDATE_INTERVAL))
    print("重量渐变时间：{} 秒".format(RAMP_SECONDS))
    print("目标停留时间：{} 秒".format(HOLD_SECONDS))
    print("测试场景数量：{}".format(len(TEST_CASES)))
    print("=" * 60)

    try:
        health = check_server()

        print(
            "Flask 状态：{}".format(
                health.get("status", "running")
            )
        )

        result = post_json(
            "/api/simulate/start"
        )

        if not result.get("ok"):
            raise RuntimeError(
                result.get(
                    "error",
                    "模拟模式启动失败",
                )
            )

        simulation_started = True

        print("\n模拟模式已启动。")
        print("真实电子秤不会被读取。")

        for index, (name, target) in enumerate(
            TEST_CASES,
            start=1,
        ):

            if not 0 <= target <= MAX_WEIGHT_KG:
                raise ValueError(
                    "测试重量超出范围：{}".format(target)
                )

            print(
                "\n[{}/{}] {}".format(
                    index,
                    len(TEST_CASES),
                    name,
                )
            )

            print(
                "重量从 {:.2f} kg 变化到 {:.2f} kg".format(
                    current_weight,
                    target,
                )
            )

            # 第一阶段：渐变到测试重量
            ramp_weight(
                current_weight,
                target,
            )

            # 第二阶段：保持目标重量，显示结果页面
            hold_weight(target)

            current_weight = target

            print(
                "完成：{}，目标重量 {} kg".format(
                    name,
                    target,
                )
            )

        print("\n所有模拟测试已完成。")

    except KeyboardInterrupt:
        print("\n测试被手动中断。")

    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
    ) as exc:

        print("\n连接 Flask 失败：{}".format(exc))
        print(
            "请确认 app_simulation_ready.py 正在运行，"
            "且 SERVER 地址正确。"
        )

    except Exception as exc:
        print("\n模拟测试失败：{}".format(exc))

    finally:

        if simulation_started:

            try:
                result = post_json(
                    "/api/simulate/stop"
                )

                print(
                    result.get(
                        "message",
                        "模拟模式已停止。",
                    )
                )

            except Exception as exc:

                print(
                    "\n自动停止失败：{}".format(exc)
                )

                print(
                    "请手动向 {}/api/stop 发送 POST 请求。".format(
                        SERVER
                    )
                )


if __name__ == "__main__":
    main()
