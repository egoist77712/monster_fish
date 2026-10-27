import atexit
import json
import math
import queue
import threading
import time

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    stream_with_context,
)

import board
import neopixel
from pymodbus.client import ModbusSerialClient


# =========================================================
# 1. Flask 设置
# =========================================================

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)


# =========================================================
# 2. LED 设置
# =========================================================

LED_PIN = board.D18
NUM_PIXELS = 120
MAX_WEIGHT_KG = 324.0

LED_BRIGHTNESS = 0.2
LED_COLOR = (255, 40, 0)  # 橙红色，NeoPixel 使用 GRB 顺序

LED_FPS = 30
LED_SPEED = 35.0

pixels = neopixel.NeoPixel(
    LED_PIN,
    NUM_PIXELS,
    brightness=LED_BRIGHTNESS,
    auto_write=False,
    pixel_order=neopixel.GRB,
)

led_lock = threading.Lock()
led_state_lock = threading.Lock()

led_target_count = 0.0
led_display_count = 0.0
led_running = False
led_thread = None


def update_led_target(weight):
    """根据重量更新灯带目标亮灯数量。"""
    global led_target_count

    weight = max(0.0, min(float(weight), MAX_WEIGHT_KG))
    count = weight / MAX_WEIGHT_KG * NUM_PIXELS

    with led_state_lock:
        led_target_count = count


def led_worker():
    """平滑更新 LED，重量变化时逐渐改变亮灯数量。"""
    global led_display_count

    previous = time.monotonic()

    while True:
        with led_state_lock:
            running = led_running
            target = led_target_count

        if not running:
            break

        now = time.monotonic()
        elapsed = now - previous
        previous = now

        max_step = max(0.5, LED_SPEED * elapsed)

        if led_display_count < target:
            led_display_count = min(
                target,
                led_display_count + max_step,
            )
        elif led_display_count > target:
            led_display_count = max(
                target,
                led_display_count - max_step,
            )

        count = max(
            0,
            min(NUM_PIXELS, int(round(led_display_count))),
        )

        try:
            with led_lock:
                pixels.fill((0, 0, 0))

                for index in range(count):
                    pixels[index] = LED_COLOR

                pixels.show()

        except Exception as exc:
            print("[LED] 更新失败:", exc)

        time.sleep(1.0 / LED_FPS)


def start_led_animation():
    """启动 LED 动画线程。"""
    global led_running
    global led_thread
    global led_target_count
    global led_display_count

    with led_state_lock:
        if led_running:
            return

        led_running = True
        led_target_count = 0.0
        led_display_count = 0.0

        led_thread = threading.Thread(
            target=led_worker,
            daemon=True,
            name="led-worker",
        )

        led_thread.start()

    print("[LED] 动画已启动")


def stop_led_animation():
    """停止 LED 动画并关闭所有灯。"""
    global led_running
    global led_target_count
    global led_display_count

    with led_state_lock:
        led_running = False
        led_target_count = 0.0
        led_display_count = 0.0

    thread = led_thread

    if (
        thread is not None
        and thread.is_alive()
        and thread is not threading.current_thread()
    ):
        thread.join(timeout=2.0)

    try:
        with led_lock:
            pixels.fill((0, 0, 0))
            pixels.show()

    except Exception as exc:
        print("[LED] 关闭失败:", exc)

    print("[LED] 已关闭")


# =========================================================
# 3. RS485 电子秤设置
# =========================================================

SERIAL_PORT = "/dev/ttyUSB0"
BAUDRATE = 9600

SLAVE_ID = 1
WEIGHT_REGISTER = 1
WEIGHT_DIVISOR = 10.0

# 目标读取间隔：0.2 秒
WEIGHT_INTERVAL = 0.2

# 串口读取超时；若电子秤响应较慢，应适当调高
SERIAL_TIMEOUT = 0.15

# 低于 5 kg 连续 5 秒，真实称重会话自动结束
NO_PERSON_THRESHOLD = 5.0
NO_PERSON_DURATION = 5.0

client = ModbusSerialClient(
    port=SERIAL_PORT,
    baudrate=BAUDRATE,
    bytesize=8,
    parity="N",
    stopbits=1,
    timeout=SERIAL_TIMEOUT,
)

modbus_lock = threading.Lock()


def read_scale_weight():
    """
    读取真实电子秤。
    只在真实称重会话中调用。
    读取失败返回 None。
    """

    try:
        with modbus_lock:

            if not getattr(client, "connected", False):
                if not client.connect():
                    print("[SCALE] 连接失败:", SERIAL_PORT)
                    return None

            try:
                response = client.read_holding_registers(
                    address=WEIGHT_REGISTER,
                    count=1,
                    device_id=SLAVE_ID,
                )

            except TypeError:
                try:
                    response = client.read_holding_registers(
                        address=WEIGHT_REGISTER,
                        count=1,
                        slave=SLAVE_ID,
                    )

                except TypeError:
                    response = client.read_holding_registers(
                        address=WEIGHT_REGISTER,
                        count=1,
                        unit=SLAVE_ID,
                    )

            if response is None or response.isError():
                print("[SCALE] 读取失败")
                return None

            registers = getattr(response, "registers", None)

            if not registers:
                print("[SCALE] 没有寄存器数据")
                return None

            weight = float(registers[0]) / WEIGHT_DIVISOR

            if not math.isfinite(weight) or weight < 0:
                return None

            return weight

    except Exception as exc:
        print("[SCALE] 异常:", exc)
        return None


# =========================================================
# 4. 全局状态
# =========================================================

state_lock = threading.RLock()

active = False
simulation_mode = False

current_weight = 0.0
capture_seq = 0
button_count = 0

button_time = None
last_read_time = None

session_id = 0
no_person_since = None

worker_thread = None


# =========================================================
# 5. SSE 事件推送
# =========================================================

EVENT_QUEUE_SIZE = 100

event_clients = set()
event_clients_lock = threading.Lock()


def get_state_snapshot():
    """读取缓存状态，不主动读取电子秤。"""

    with state_lock:
        return {
            "ok": True,
            "active": active,
            "kg": round(current_weight, 2),
            "weight": round(current_weight, 2),
            "seq": capture_seq,
            "count": button_count,
            "button_time": button_time,
            "timestamp": last_read_time,
            "simulation_mode": simulation_mode,
            "session_id": session_id,
        }


def publish_event(event_name, data):
    """向连接中的浏览器发送事件。"""

    message = {
        "event": event_name,
        "data": data,
    }

    with event_clients_lock:
        clients = list(event_clients)

    for client_queue in clients:
        try:
            client_queue.put_nowait(message)

        except queue.Full:
            try:
                client_queue.get_nowait()
            except queue.Empty:
                pass

            try:
                client_queue.put_nowait(message)
            except queue.Full:
                pass


@app.route("/api/events", methods=["GET"])
def events_api():
    """SSE 长连接：status、session_start、weight、session_end。"""

    client_queue = queue.Queue(maxsize=EVENT_QUEUE_SIZE)

    with event_clients_lock:
        event_clients.add(client_queue)

    def generate():
        try:
            yield "event: status\ndata: {}\n\n".format(
                json.dumps(get_state_snapshot())
            )

            while True:
                try:
                    message = client_queue.get(timeout=15)

                    yield "event: {}\ndata: {}\n\n".format(
                        message["event"],
                        json.dumps(message["data"]),
                    )

                except queue.Empty:
                    yield ": heartbeat\n\n"

        except GeneratorExit:
            pass

        finally:
            with event_clients_lock:
                event_clients.discard(client_queue)

    response = Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
    )

    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"

    return response


# =========================================================
# 6. 真实称重线程
# =========================================================

def weighing_worker(my_session_id):
    """
    只有实体按钮启动后才运行。

    目标每 0.2 秒采样一次。
    连续 5 秒低于 5 kg 自动结束。
    """

    global active
    global current_weight
    global capture_seq
    global last_read_time
    global no_person_since

    print("[SESSION] 真实称重启动:", my_session_id)

    next_sample = time.monotonic()

    try:
        while True:

            with state_lock:
                if (
                    not active
                    or simulation_mode
                    or session_id != my_session_id
                ):
                    break

            weight = read_scale_weight()
            now = time.time()
            should_end = False
            event_data = None

            with state_lock:

                if (
                    not active
                    or simulation_mode
                    or session_id != my_session_id
                ):
                    break

                if weight is not None:

                    current_weight = weight
                    capture_seq += 1
                    last_read_time = now

                    if weight < NO_PERSON_THRESHOLD:

                        if no_person_since is None:
                            no_person_since = now

                        elif (
                            now - no_person_since
                            >= NO_PERSON_DURATION
                        ):
                            active = False
                            no_person_since = None
                            should_end = True

                    else:
                        no_person_since = None

                    event_data = {
                        "ok": True,
                        "active": not should_end,
                        "kg": round(current_weight, 2),
                        "weight": round(current_weight, 2),
                        "seq": capture_seq,
                        "count": button_count,
                        "button_time": button_time,
                        "timestamp": last_read_time,
                        "simulation_mode": False,
                        "session_id": session_id,
                    }

                else:
                    # 读取失败不算作低重量。
                    no_person_since = None

            if event_data is not None:
                update_led_target(weight)
                publish_event("weight", event_data)

            if should_end:
                print("[SESSION] 连续 5 秒低于 5 kg，结束")
                break

            # 按固定周期调度，不额外叠加 0.2 秒等待。
            next_sample += WEIGHT_INTERVAL
            delay = next_sample - time.monotonic()

            if delay > 0:
                time.sleep(delay)
            else:
                next_sample = time.monotonic()

    except Exception as exc:
        print("[SESSION] 称重线程异常:", exc)

    finally:
        end_data = None

        with state_lock:
            if session_id == my_session_id and not simulation_mode:

                active = False

                end_data = {
                    "ok": True,
                    "active": False,
                    "kg": round(current_weight, 2),
                    "weight": round(current_weight, 2),
                    "seq": capture_seq,
                    "count": button_count,
                    "button_time": button_time,
                    "timestamp": last_read_time,
                    "simulation_mode": False,
                    "session_id": session_id,
                }

        if end_data is not None:
            stop_led_animation()
            publish_event("session_end", end_data)

        print("[SESSION] 真实称重线程结束")


# =========================================================
# 7. 启动真实称重
# =========================================================

def start_session():
    global active
    global simulation_mode
    global current_weight
    global capture_seq
    global button_count
    global button_time
    global last_read_time
    global session_id
    global no_person_since
    global worker_thread

    with state_lock:

        if active:
            return {
                "ok": True,
                "started": False,
                "active": True,
                "simulation_mode": simulation_mode,
                "message": "已有会话正在运行",
            }

        active = True
        simulation_mode = False

        session_id += 1
        my_session_id = session_id

        current_weight = 0.0
        capture_seq = 0
        last_read_time = None
        no_person_since = None

        button_count += 1
        button_time = time.time()

    start_led_animation()
    publish_event("session_start", get_state_snapshot())

    worker_thread = threading.Thread(
        target=weighing_worker,
        args=(my_session_id,),
        daemon=True,
        name="real-weighing",
    )

    worker_thread.start()

    return {
        "ok": True,
        "started": True,
        "active": True,
        "simulation_mode": False,
        "session_id": my_session_id,
        "message": "真实称重已启动",
    }


# =========================================================
# 8. 停止会话
# =========================================================

def stop_session():
    global active
    global simulation_mode
    global no_person_since

    with state_lock:
        was_active = active

        active = False
        simulation_mode = False
        no_person_since = None

        final_data = get_state_snapshot()

    stop_led_animation()

    if was_active:
        final_data["active"] = False
        publish_event("session_end", final_data)

    return {
        "ok": True,
        "active": False,
        "message": "会话已停止",
    }


# =========================================================
# 9. 网页与常规 API
# =========================================================

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/api/weight", methods=["GET"])
def weight_api():
    # 只返回缓存，不读取电子秤。
    return jsonify(get_state_snapshot())


@app.route("/api/weight", methods=["POST"])
def weight_post_api():
    return jsonify({
        "ok": False,
        "error": "真实重量不能通过此接口修改，请使用模拟接口。",
    }), 403


@app.route("/api/button", methods=["GET", "POST"])
def button_api():

    if request.method == "POST":
        return jsonify(start_session())

    with state_lock:
        return jsonify({
            "ok": True,
            "active": active,
            "pressed": active,
            "count": button_count,
            "button_time": button_time,
            "simulation_mode": simulation_mode,
        })


@app.route("/api/capture", methods=["GET"])
def capture_api():
    # 兼容旧调试工具。
    return jsonify(get_state_snapshot())


@app.route("/api/stop", methods=["POST"])
def stop_api():
    return jsonify(stop_session())


@app.route("/api/health", methods=["GET"])
def health_api():
    with state_lock:
        return jsonify({
            "ok": True,
            "status": "running",
            "active": active,
            "weight": round(current_weight, 2),
            "seq": capture_seq,
            "simulation_mode": simulation_mode,
            "led_pixels": NUM_PIXELS,
            "sample_interval": WEIGHT_INTERVAL,
            "serial_port": SERIAL_PORT,
        })


# =========================================================
# 10. 模拟测试 API
# =========================================================

@app.route("/api/simulate/start", methods=["POST"])
def simulate_start_api():
    global active
    global simulation_mode
    global session_id
    global current_weight
    global capture_seq
    global last_read_time
    global no_person_since
    global button_count
    global button_time

    with state_lock:

        if active:
            return jsonify({
                "ok": False,
                "error": "已有会话运行中，请先停止。",
            }), 409

        active = True
        simulation_mode = True

        session_id += 1
        current_weight = 0.0
        capture_seq = 0
        last_read_time = time.time()
        no_person_since = None

        button_count += 1
        button_time = time.time()

        this_session = session_id

    start_led_animation()

    start_data = get_state_snapshot()
    start_data["session_id"] = this_session

    publish_event("session_start", start_data)

    print("[SIM] 模拟模式已启动，不读取真实电子秤")

    return jsonify({
        "ok": True,
        "simulation": True,
        "active": True,
        "session_id": this_session,
        "message": "模拟模式已启动",
    })


@app.route("/api/simulate/weight", methods=["POST"])
def simulate_weight_api():
    global current_weight
    global capture_seq
    global last_read_time

    data = request.get_json(silent=True) or {}

    try:
        weight = float(data.get("kg"))
    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "error": '请传入数字重量，例如 {"kg": 80}',
        }), 400

    if (
        not math.isfinite(weight)
        or weight < 0
        or weight > MAX_WEIGHT_KG
    ):
        return jsonify({
            "ok": False,
            "error": "重量必须在 0 到 {} kg 之间".format(
                MAX_WEIGHT_KG
            ),
        }), 400

    with state_lock:

        if not active or not simulation_mode:
            return jsonify({
                "ok": False,
                "error": "请先 POST /api/simulate/start",
            }), 409

        current_weight = weight
        capture_seq += 1
        last_read_time = time.time()

        event_data = {
            "ok": True,
            "active": True,
            "kg": round(current_weight, 2),
            "weight": round(current_weight, 2),
            "seq": capture_seq,
            "count": button_count,
            "button_time": button_time,
            "timestamp": last_read_time,
            "simulation_mode": True,
            "session_id": session_id,
        }

    # 模拟重量改变后，实际更新灯带目标并推送前端事件。
    update_led_target(weight)
    publish_event("weight", event_data)

    return jsonify({
        "ok": True,
        "simulation": True,
        "active": True,
        "kg": round(weight, 2),
        "seq": capture_seq,
        "led_target": round(
            weight / MAX_WEIGHT_KG * NUM_PIXELS,
            2,
        ),
        "message": "模拟重量已更新",
    })


@app.route("/api/simulate/stop", methods=["POST"])
def simulate_stop_api():

    with state_lock:
        if not simulation_mode:
            return jsonify({
                "ok": False,
                "error": "当前不是模拟模式",
            }), 409

    result = stop_session()
    result["simulation"] = False
    result["message"] = "模拟测试已停止"

    return jsonify(result)


# =========================================================
# 11. 清理
# =========================================================

def cleanup():
    try:
        stop_session()
    except Exception as exc:
        print("[SYSTEM] 停止会话失败:", exc)

    try:
        with modbus_lock:
            client.close()
    except Exception as exc:
        print("[SYSTEM] 关闭 RS485 失败:", exc)


atexit.register(cleanup)


# =========================================================
# 12. 启动 Flask
# =========================================================

if __name__ == "__main__":

    # 不在启动时连接电子秤。
    # 只有 POST /api/button 后才开始尝试读取。

    print("=" * 55)
    print("Minnow or Monster")
    print("页面： http://<树莓派IP>:8080/")
    print("SSE： /api/events")
    print("真实称重：POST /api/button")
    print("模拟启动：POST /api/simulate/start")
    print("目标采样周期：{} 秒".format(WEIGHT_INTERVAL))
    print("=" * 55)

    try:
        app.run(
            host="0.0.0.0",
            port=8080,
            debug=False,
            threaded=True,
            use_reloader=False,
        )
    finally:
        cleanup()
