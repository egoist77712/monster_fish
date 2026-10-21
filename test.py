
import time
import threading

from flask import Flask, jsonify, render_template, request

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)

# =====================================================
# 1. 模拟称重数据
# =====================================================

state_lock = threading.Lock()

current_weight = 0.0
active = False
button_count = 0
button_time = 0.0
capture_seq = 0
last_read_time = 0.0


# =====================================================
# 2. 前端首页
# =====================================================

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


# =====================================================
# 3. 检查 Flask 是否正常
# GET /api/health
# =====================================================

@app.route("/api/health", methods=["GET"])
def health_api():
    with state_lock:
        return jsonify({
            "ok": True,
            "active": active,
            "weight": current_weight,
            "seq": capture_seq,
            "mode": "simulation"
        })


# =====================================================
# 4. 获取当前重量
# GET /api/weight
# =====================================================

@app.route("/api/weight", methods=["GET"])
def get_weight():
    with state_lock:
        return jsonify({
            "kg": current_weight,
            "weight": current_weight,
            "active": active,
            "seq": capture_seq
        })


# =====================================================
# 5. Postman 发送模拟重量
# POST /api/weight
# =====================================================

@app.route("/api/weight", methods=["POST"])
def set_weight():
    global current_weight, capture_seq, last_read_time

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "ok": False,
            "error": "请使用 JSON 格式发送数据"
        }), 400

    weight = data.get("kg", data.get("weight"))

    if weight is None:
        return jsonify({
            "ok": False,
            "error": "请提供 kg 或 weight 字段"
        }), 400

    try:
        weight = float(weight)
    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "error": "重量必须是数字"
        }), 400

    if not 0 <= weight <= 1000:
        return jsonify({
            "ok": False,
            "error": "重量必须在 0 到 1000 kg 之间"
        }), 400

    with state_lock:
        current_weight = weight
        capture_seq += 1
        last_read_time = time.time()

        result = {
            "ok": True,
            "kg": current_weight,
            "weight": current_weight,
            "active": active,
            "seq": capture_seq
        }

    print(f"[POST] 收到重量：{weight:.1f} kg")

    return jsonify(result)


# =====================================================
# 6. 查询按钮状态
# GET /api/button
# =====================================================

@app.route("/api/button", methods=["GET"])
def get_button():
    with state_lock:
        return jsonify({
            "active": active,
            "pressed": active,
            "count": button_count,
            "time": button_time
        })


# =====================================================
# 7. 模拟按下开始按钮
# POST /api/button
# =====================================================

@app.route("/api/button", methods=["POST"])
def press_button():
    global active, button_count, button_time

    with state_lock:
        started = not active

        if started:
            active = True
            button_count += 1
            button_time = time.time()

        return jsonify({
            "ok": True,
            "started": started,
            "active": active,
            "count": button_count
        })


# =====================================================
# 8. 前端轮询接口
# GET /api/capture
# =====================================================

@app.route("/api/capture", methods=["GET"])
def capture_api():
    with state_lock:
        return jsonify({
            "active": active,
            "kg": current_weight,
            "weight": current_weight,
            "seq": capture_seq,
            "count": button_count,
            "button_time": button_time,
            "timestamp": last_read_time
        })


# =====================================================
# 9. 停止模拟称重
# POST /api/stop
# =====================================================

@app.route("/api/stop", methods=["POST"])
def stop_api():
    global active

    with state_lock:
        active = False

    return jsonify({
        "ok": True,
        "active": False,
        "message": "模拟称重已停止"
    })


# =====================================================
# 10. 启动服务
# =====================================================

if __name__ == "__main__":
    print("Minnow or Monster 前后端测试服务已启动")
    print("网页地址：http://127.0.0.1:8080")
    print("测试模式：不连接电子秤和 LED")

    app.run(
        host="0.0.0.0",
        port=8080,
        debug=False,
        threaded=True
    )
