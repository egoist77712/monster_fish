"""接口测试:不需要 pytest,直接 `python tests/test_api.py`。

覆盖:

  1. 采样逻辑 —— 中位数平滑、超量程剔除、稳定判定、按键计数;
  2. 连续抓取 —— 按下按钮后每 0.5 秒抓一次、连续 5 秒没人就结束会话;
  3. HTTP 接口 —— 前端 / Postman 会调的每个接口都走一遍,包括 400 / 409。

任何一项失败都会打印 FAIL 并以非 0 退出,方便挂到 CI 或 VS Code 的测试任务上。
"""

import os
import sys
import time

# 让 `python tests/test_api.py` 能 import 到项目根目录的模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 必须在 import app / config 之前设置:强制走模拟硬件,测试不依赖树莓派
os.environ["SCALE_SIMULATE"] = "1"

import hardware                                                    # noqa: E402
import config                                                      # noqa: E402
from app import create_app                                         # noqa: E402
from hardware.button import SimulatedButton                         # noqa: E402
from monitor import Monitor                                         # noqa: E402

FAILED = []


def check(label, got, want):
    """断言并打印;失败只记录不中断,最后统一汇报。"""
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got!r}"
          + ("" if ok else f"  (期望 {want!r})"))
    if not ok:
        FAILED.append(label)


class FakeScale:
    """测试用的假秤:给一个固定读数,中途也可以改。

    不启动后台线程,而是手动调用 Monitor._tick(),采样逻辑不依赖真实硬件。
    """

    name = "fake"

    def __init__(self, kg):
        self._kg = float(kg)

    def set(self, kg):
        self._kg = float(kg)

    def read_kg(self):
        return self._kg

    def close(self):
        pass


def drive(mon, seconds, step=0.1):
    """按 10 Hz 手动推进采样循环,模拟真实运行。"""
    for _ in range(int(seconds / step) + 1):
        mon._tick()
        time.sleep(step)


# ===========================================================================
# 一、采样逻辑(不起线程,手动 tick)
# ===========================================================================
print("\n-- 采样:中位数平滑 / 稳定判定 --")

mon = Monitor(FakeScale(60.0), SimulatedButton())
for _ in range(config.SMOOTH_SAMPLES):
    mon._tick()
snap = mon.weight()
check("稳定后 kg", snap["kg"], 60.0)
check("稳定后 stable", snap["stable"], True)

mon_partial = Monitor(FakeScale(60.0), SimulatedButton())
mon_partial._tick()
check("只采了 1 次时不报稳定", mon_partial.weight()["stable"], False)

mon_over = Monitor(FakeScale(999.0), SimulatedButton())
for _ in range(config.SMOOTH_SAMPLES):
    mon_over._tick()
check("超量程读数被丢弃", mon_over.weight()["kg"], 0.0)

print("\n-- 按钮:计数 / 电平 --")
mon_btn = Monitor(FakeScale(0.0), SimulatedButton())
check("初始计数为 0", mon_btn.button()["count"], 0)
mon_btn.simulate_press()
check("按一次后计数 +1", mon_btn.button()["count"], 1)
check("按下瞬间 pressed=True", mon_btn.button()["pressed"], True)
time.sleep(config.BUTTON_HOLD_MS / 1000 + 0.2)
check("松开后 pressed=False", mon_btn.button()["pressed"], False)
check("计数不会因为松开而减少", mon_btn.button()["count"], 1)

# ===========================================================================
# 二、连续抓取:按一下按钮 -> 每 0.5 秒抓一次 -> 连续 5 秒没人就结束
# ===========================================================================
print("\n-- 连续抓取(每 0.5 秒一次,连续 5 秒没人结束)--")

mon_cap = Monitor(FakeScale(60.0), SimulatedButton())
initial = mon_cap.capture()
check("还没按按钮时 active=False", initial["active"], False)
check("还没按按钮时 seq=0", initial["seq"], 0)
check("还没按按钮时 kg=None", initial["kg"], None)

mon_cap.simulate_press()
check("按下按钮后立刻 active=True", mon_cap.capture()["active"], True)

drive(mon_cap, 0.7)
first = mon_cap.capture()
check("0.7 秒内已经抓到第一笔", first["seq"] >= 1, True)
check("抓到的体重", first["kg"], 60.0)
check("抓取时间戳已记录", first["at"] > 0, True)

seq_before = first["seq"]
drive(mon_cap, 1.0)          # 再跑 1 秒,按 0.5 秒的节奏应该又抓了 1~2 笔
check("每 0.5 秒抓一次(1 秒内 seq 增加 1~3)",
      seq_before < mon_cap.capture()["seq"] <= seq_before + 3, True)

# 人走下来:体重掉到 0,连续 5 秒后会话结束
mon_cap._scale.set(0.0)
drive(mon_cap, 3.0)
check("离开 3 秒还没结束(未满 5 秒)", mon_cap.capture()["active"], True)
drive(mon_cap, 2.8)
check("连续 5 秒没人 -> 会话结束", mon_cap.capture()["active"], False)

# ===========================================================================
# 三、HTTP 接口(和 Postman 里调的完全一样)
# ===========================================================================
print("\n-- HTTP 接口 --")
app = create_app()
app.testing = True
client = app.test_client()

check("GET / 展台界面", client.get("/").status_code, 200)
check("GET /favicon.ico", client.get("/favicon.ico").status_code, 204)

r = client.get("/api/weight")
body = r.get_json()
check("GET /api/weight 状态码", r.status_code, 200)
check("weight 响应字段", sorted(body), ["at", "kg", "stable"])
check("接口禁止缓存", r.headers.get("Cache-Control"), "no-store")

r = client.post("/api/weight", json={"kg": 62.4})
check("POST /api/weight 状态码", r.status_code, 200)
check("POST /api/weight 回显", r.get_json()["kg"], 62.4)
time.sleep(1.2)
check("设置的重量能读到(±0.7 kg)",
      abs(client.get("/api/weight").get_json()["kg"] - 62.4) <= 0.7, True)

check("kg 传字符串 -> 400",
      client.post("/api/weight", json={"kg": "abc"}).status_code, 400)
check("kg 超量程 -> 400",
      client.post("/api/weight", json={"kg": 9999}).status_code, 400)
check("body 不是 JSON -> 400",
      client.post("/api/weight", data="not json").status_code, 400)
check("缺 kg 字段 -> 400",
      client.post("/api/weight", json={"weight": 50}).status_code, 400)
check("设置失败后重量没被改坏",
      abs(client.get("/api/weight").get_json()["kg"] - 62.4) <= 0.7, True)

print("\n-- 按下按钮后的连续抓取(HTTP)--")
cap = client.get("/api/capture").get_json()
check("capture 字段", sorted(cap), ["active", "at", "kg", "seq"])
check("按之前 active=False", cap["active"], False)

r = client.post("/api/button")
check("POST /api/button 状态码", r.status_code, 200)
check("按下后 count +1", r.get_json()["count"], 1)
check("按下后 pressed=True", r.get_json()["pressed"], True)
check("按下后 active=True", client.get("/api/capture").get_json()["active"], True)

time.sleep(0.8)
cap = client.get("/api/capture").get_json()
check("0.8 秒内抓到数据(seq>=1)", cap["seq"] >= 1, True)
check("抓到的重量接近 62.4(±0.7 kg)",
      cap["kg"] is not None and abs(cap["kg"] - 62.4) <= 0.7, True)

# 人走下来 -> 连续 5 秒没人 -> 会话结束
client.post("/api/weight", json={"kg": 0})
time.sleep(config.EMPTY_RESET_MS / 1000 + 0.8)
check("连续 5 秒没人后 active=False",
      client.get("/api/capture").get_json()["active"], False)

time.sleep(config.BUTTON_HOLD_MS / 1000 + 0.2)
check("按钮 150 ms 后自动松开", client.get("/api/button").get_json()["pressed"], False)

health = client.get("/api/health").get_json()
check("health.ok", health["ok"], True)
check("health.simulated", health["simulated"], True)
check("health.hardware(只有秤和按钮)", health["hardware"],
      {"scale": "simulated", "button": "simulated"})
check("health.uptimeSec 是数字", isinstance(health["uptimeSec"], (int, float)), True)

app.extensions["monitor"].stop()

# ---------------------------------------------------------------------------
# 真硬件模式下 POST /api/weight 必须被拒绝(重量不能由 HTTP 决定)
# ---------------------------------------------------------------------------
print("\n-- 真硬件模式:不允许用接口设置重量 --")


class DummyRealScale(FakeScale):
    """冒充真 HX711:只为让 create_app() 认为当前不是模拟模式。"""

    name = "hx711"


real_build = hardware.build
hardware.build = lambda: (DummyRealScale(0.0), SimulatedButton())
app_real = create_app()
app_real.testing = True
client_real = app_real.test_client()

check("真硬件模式 POST /api/weight -> 409",
      client_real.post("/api/weight", json={"kg": 50}).status_code, 409)
check("真硬件模式 health.simulated=False",
      client_real.get("/api/health").get_json()["simulated"], False)
check("真硬件模式 GET /api/weight 仍可用",
      client_real.get("/api/weight").status_code, 200)
app_real.extensions["monitor"].stop()
hardware.build = real_build

# ===========================================================================
print("\n" + "=" * 52)
if FAILED:
    print(f"{len(FAILED)} 项失败:{FAILED}")
    sys.exit(1)
print("全部通过")
