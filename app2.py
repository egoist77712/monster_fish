
import time
import threading
from flask import Flask, jsonify, render_template, request

# =========================================================
# 1. Flask 设置：只运行前端和模拟 API，不连接任何硬件
# =========================================================

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)

# =========================================================
# 2. 模拟参数
# =========================================================

STEP_SECONDS = 2  # 每个模拟阶段停留 2 秒

# 依次模拟不同重量。
# app.js 会根据现有 PROMPTS / resolve 逻辑决定显示哪一屏。
DEMO_WEIGHTS = [
    50,
    70,
    75,
    80,
    100,
    120,
    200,
    250,
    300,
    310
]

# =========================================================
# 3. 模拟状态
# =========================================================

state_lock = threading.Lock()

state = {
    "active": False,
    "kg": 0.0,
    "stable": True,
    "seq": 0,
    "button_pressed": False,
    "stage": "idle",
    "stage_index": 0,
    "last_update": time.time()
}

simulation_thread = None
stop_event = threading.Event()


# =========================================================
# 4. 获取当前状态
# =========================================================

def get_state():
    with state_lock:
        return dict(state)


# =========================================================
# 5. 模拟完整称重流程
# =========================================================

def run_simulation():
    global state

    try:
        # 模拟进入称重流程
        with state_lock:
            state["active"] = True
            state["button_pressed"] = True
            state["stage"] = "weighing"
            state["stage_index"] = 0
            state["seq"] += 1
            state["last_update"] = time.time()

        print("\n========== 模拟展示开始 ==========")

        for index, kg in enumerate(DEMO_WEIGHTS, start=1):

            if stop_event.is_set():
                break

            # 更新模拟重量
            with state_lock:
                state["active"] = True
                state["kg"] = float(kg)
                state["stable"] = True
                state["seq"] += 1
                state["stage"] = "result"
                state["stage_index"] = index
                state["last_update"] = time.time()

            print(
                f"[模拟阶段 {index}/{len(DEMO_WEIGHTS)}] "
                f"重量={kg} kg，停留 {STEP_SECONDS} 秒"
            )

            # 每个重量阶段保持 2 秒
            if stop_event.wait(STEP_SECONDS):
                break

        # 模拟流程结束
        with state_lock:
            state["active"] = False
            state["button_pressed"] = False
            state["stable"] = True
            state["stage"] = "idle"
            state["stage_index"] = 0
            state["kg"] = 0.0
            state["seq"] += 1
            state["last_update"] = time.time()

        print("========== 模拟展示结束 ==========\n")

    finally:
        with state_lock:
            state["active"] = False
            state["button_pressed"] = False
            state["stage"] = "idle"


# =========================================================
# 6. 启动模拟
# =========================================================

def start_simulation():
    global simulation_thread

    # 如果已有演示正在运行，不重复启动
    with state_lock:
        if state["active"]:
            return False

        stop_event.clear()

        simulation_thread = threading.Thread(
            target=run_simulation,
            daemon=True
        )
        simulation_thread.start()

    return True


# =========================================================
# 7. 前端主页
# =========================================================

@app.route("/")
def index():
    response = render_template("index.html")

    # 使用 ?demo=1 时，打开网页自动开始演示
    if request.args.get("demo") == "1":
        start_simulation()

    return response


# =========================================================
# 8. API：读取当前重量
# =========================================================

@app.route("/api/weight", methods=["GET"])
def api_weight():
    current = get_state()

    return jsonify({
        "kg": current["kg"],
        "weight": current["kg"],
        "stable": current["stable"],
        "active": current["active"],
        "seq": current["seq"]
    })


# =========================================================
# 9. API：按钮状态 / 模拟按下按钮
# =========================================================

@app.route("/api/button", methods=["GET", "POST"])
def api_button():
    if request.method == "GET":
        current = get_state()

        return jsonify({
            "pressed": current["button_pressed"],
            "button_pressed": current["button_pressed"],
            "active": current["active"],
            "stage": current["stage"]
        })

    started = start_simulation()

    return jsonify({
        "ok": True,
        "started": started,
        "message": (
            "模拟流程已启动"
            if started
            else "模拟流程已经在运行"
        )
    })


# =========================================================
# 10. API：前端轮询流程状态
# =========================================================

@app.route("/api/capture", methods=["GET"])
def api_capture():
    current = get_state()

    return jsonify({
        "active": current["active"],
        "seq": current["seq"],
        "kg": current["kg"],
        "weight": current["kg"],
        "stable": current["stable"],
        "stage": current["stage"],
        "stage_index": current["stage_index"]
    })


# =========================================================
# 11. API：手动设置模拟重量（方便 Postman 测试）
# =========================================================

@app.route("/api/weight", methods=["POST"])
def set_simulated_weight():
    data = request.get_json(silent=True) or {}

    try:
        kg = float(data.get("kg", data.get("weight", 0)))
    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "error": "kg 必须是数字"
        }), 400

    if kg < 0:
        return jsonify({
            "ok": False,
            "error": "重量不能小于 0"
        }), 400

    with state_lock:
        state["kg"] = kg
        state["stable"] = True
        state["seq"] += 1
        state["last_update"] = time.time()

    return jsonify({
        "ok": True,
        "kg": kg,
        "stable": True,
        "seq": get_state()["seq"]
    })


# =========================================================
# 12. API：停止模拟
# =========================================================

@app.route("/api/stop", methods=["POST"])
def api_stop():
    stop_event.set()

    with state_lock:
        state["active"] = False
        state["button_pressed"] = False
        state["stage"] = "idle"
        state["kg"] = 0.0
        state["seq"] += 1

    return jsonify({
        "ok": True,
        "message": "模拟已停止"
    })


# =========================================================
# 13. API：手动启动完整演示
# =========================================================

@app.route("/api/simulate/start", methods=["GET", "POST"])
def simulate_start():
    started = start_simulation()

    return jsonify({
        "ok": True,
        "started": started,
        "message": (
            "演示已启动"
            if started
            else "演示正在运行"
        )
    })


# =========================================================
# 14. API：手动模拟单个重量
# =========================================================

@app.route("/api/simulate/weight", methods=["POST"])
def simulate_weight():
    data = request.get_json(silent=True) or {}

    try:
        kg = float(data.get("kg", 0))
    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "error": "kg 必须是数字"
        }), 400

    if kg < 0:
        return jsonify({
            "ok": False,
            "error": "重量不能小于 0"
        }), 400

    with state_lock:
        state["kg"] = kg
        state["stable"] = True
        state["active"] = True
        state["stage"] = "result"
        state["seq"] += 1
        state["last_update"] = time.time()

    return jsonify({
        "ok": True,
        "kg": kg,
        "stable": True,
        "seq": get_state()["seq"]
    })


# =========================================================
# 15. API：健康检查
# =========================================================

@app.route("/api/health", methods=["GET"])
def api_health():
    current = get_state()

    return jsonify({
        "ok": True,
        "service": "Minnow or Monster - Windows Simulation",
        "hardware": False,
        "active": current["active"]
    })


# =========================================================
# 16. 启动 Flask
# =========================================================

if __name__ == "__main__":
    print("=" * 50)
    print("Minnow or Monster - Windows 模拟模式")
    print("没有 LED、电子秤、RS485 或树莓派依赖")
    print("自动演示：http://127.0.0.1:8080/?demo=1")
    print("手动演示：http://127.0.0.1:8080/api/simulate/start")
    print("=" * 50)

    app.run(
        host="0.0.0.0",
        port=8080,
        debug=False,
        threaded=True,
        use_reloader=False
    )
