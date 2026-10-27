import atexit
import json
import math
import queue
import threading
import time

from flask import Flask, Response, jsonify, render_template, stream_with_context

import board
import neopixel
from pymodbus.client import ModbusSerialClient


# =========================================================
# 1. Flask 设置
# =========================================================

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)


# =========================================================
# 2. WS2812 LED 灯带设置
# =========================================================

LED_PIN = board.D18
NUM_PIXELS = 120
LED_BRIGHTNESS = 0.2

# 橙色，RGB 顺序
LED_COLOR = (255, 40, 0)

# 电子秤显示范围
MAX_DISPLAY_WEIGHT = 324.0

# 灯带动画速度
LED_FPS = 30
LED_SPEED = 35

# 灯带资源
pixels = None
led_lock = threading.Lock()

led_animation_thread = None
led_animation_stop = threading.Event()

# 当前重量与灯带显示状态
led_target_count = 0
led_display_count = 0


def init_led():
    """初始化 WS2812 灯带。"""

    global pixels

    try:
        pixels = neopixel.NeoPixel(
            LED_PIN,
            NUM_PIXELS,
            brightness=LED_BRIGHTNESS,
            auto_write=False,
            pixel_order=neopixel.GRB
        )

        pixels.fill((0, 0, 0))
        pixels.show()

        print("[LED] WS2812 初始化成功")

    except Exception as e:
        pixels = None
        print("[LED] 初始化失败：{}".format(e))


def turn_off_leds():
    """关闭所有 LED。"""

    if pixels is None:
        return

    try:
        with led_lock:
            pixels.fill((0, 0, 0))
            pixels.show()

    except Exception as e:
        print("[LED] 关闭失败：{}".format(e))


def update_led_target(weight):
    """
    根据当前重量更新灯带目标数量。

    120 颗 LED 对应 0～324 kg 的显示范围。
    """

    global led_target_count

    try:
        weight = max(0.0, float(weight))

        ratio = min(
            weight / MAX_DISPLAY_WEIGHT,
            1.0
        )

        led_target_count = int(
            round(ratio * NUM_PIXELS)
        )

    except (TypeError, ValueError):
        led_target_count = 0


def led_animation_loop():
    """
    平滑调整亮灯数量。

    每次重量变化后，灯带会逐步调整亮灯数量，
    而不是突然从一个状态跳到另一个状态。
    """

    global led_display_count

    last_update = time.monotonic()

    while not led_animation_stop.is_set():

        now = time.monotonic()
        elapsed = now - last_update
        last_update = now

        with led_lock:
            target = led_target_count
            current = led_display_count

            max_change = max(
                1,
                int(LED_SPEED * elapsed)
            )

            if current < target:
                current = min(
                    target,
                    current + max_change
                )

            elif current > target:
                current = max(
                    target,
                    current - max_change
                )

            led_display_count = current

            if pixels is not None:
                try:
                    # 从灯带底部开始点亮
                    for i in range(NUM_PIXELS):

                        if i < current:
                            pixels[i] = LED_COLOR
                        else:
                            pixels[i] = (0, 0, 0)

                    pixels.show()

                except Exception as e:
                    print("[LED] 更新失败：{}".format(e))

        led_animation_stop.wait(1.0 / LED_FPS)


def start_led_animation():
    """启动灯带动画线程。"""

    global led_animation_thread
    global led_display_count
    global led_target_count

    if (
        led_animation_thread is not None
        and led_animation_thread.is_alive()
    ):
        return

    led_animation_stop.clear()

    with led_lock:
        led_display_count = 0
        led_target_count = 0

    led_animation_thread = threading.Thread(
        target=led_animation_loop,
        daemon=True
    )

    led_animation_thread.start()

    print("[LED] 动画已启动")


def stop_led_animation():
    """停止灯带动画并关闭灯带。"""

    global led_display_count
    global led_target_count

    led_animation_stop.set()

    if (
        led_animation_thread is not None
        and led_animation_thread.is_alive()
    ):
        led_animation_thread.join(timeout=2)

    with led_lock:
        led_display_count = 0
        led_target_count = 0

    turn_off_leds()

    print("[LED] 动画已停止")


# =========================================================
# 3. RS485 电子秤设置
# =========================================================

SERIAL_PORT = "/dev/ttyUSB0"
BAUDRATE = 9600

SLAVE_ID = 1
WEIGHT_REGISTER = 1

# 例如寄存器读到 250，除以 10 得到 25.0 kg
WEIGHT_DIVISOR = 10.0

# 每次称重间隔
WEIGHT_INTERVAL = 0.2

# 低于此重量并持续指定时间后结束
NO_PERSON_THRESHOLD = 5.0
NO_PERSON_DURATION = 5.0

client = ModbusSerialClient(
    port=SERIAL_PORT,
    baudrate=BAUDRATE,
    bytesize=8,
    parity="N",
    stopbits=1,
    timeout=2
)

scale_lock = threading.Lock()


def connect_scale():
    """连接 RS485 电子秤。"""

    try:
        if client.connected:
            return True

        connected = client.connect()

        if connected:
            print("[SCALE] 已连接：{}".format(SERIAL_PORT))
        else:
            print("[SCALE] 连接失败：{}".format(SERIAL_PORT))

        return connected

    except Exception as e:
        print("[SCALE] 连接异常：{}".format(e))
        return False


def read_scale_weight():
    """
    读取电子秤重量。

    兼容不同版本 pymodbus 的参数名称。
    返回 kg 数值；读取失败时返回 None。
    """

    with scale_lock:

        try:
            if not connect_scale():
                return None

            try:
                # 较新版本 pymodbus
                response = client.read_holding_registers(
                    address=WEIGHT_REGISTER,
                    count=1,
                    device_id=SLAVE_ID
                )

            except TypeError:
                # 部分旧版本 pymodbus
                try:
                    response = client.read_holding_registers(
                        address=WEIGHT_REGISTER,
                        count=1,
                        slave=SLAVE_ID
                    )

                except TypeError:
                    response = client.read_holding_registers(
                        address=WEIGHT_REGISTER,
                        count=1,
                        unit=SLAVE_ID
                    )

            if response is None:
                print("[SCALE] 没有收到响应")
                return None

            if response.isError():
                print("[SCALE] Modbus 返回错误：{}".format(response))
                return None

            registers = getattr(response, "registers", None)

            if not registers:
                print("[SCALE] 没有可读取的寄存器")
                return None

            raw_value = registers[0]

            weight = float(raw_value) / WEIGHT_DIVISOR

            if not math.isfinite(weight):
                return None

            return max(0.0, weight)

        except Exception as e:
            print("[SCALE] 读取失败：{}".format(e))
            return None


# =========================================================
# 4. 称重会话状态
# =========================================================

state_lock = threading.Lock()

active = False

current_weight = 0.0

capture_seq = 0
button_count = 0

button_time = None
last_read_time = None

session_id = 0

no_person_since = None

# 最近一次有效重量
last_valid_weight = None

# 最近一次有效重量发生明显变化的时间
last_weight_change_time = None

# 方便前端读取的稳定状态
weight_stable = False


# =========================================================
# 5. SSE 事件推送
# =========================================================

# 每个浏览器连接拥有自己的事件队列
event_clients = set()
event_clients_lock = threading.Lock()

EVENT_QUEUE_SIZE = 100


def publish_event(event_name, data):
    """
    将事件推送给所有连接的浏览器。

    支持的事件：
        status
        session_start
        weight
        session_end
    """

    message = {
        "event": event_name,
        "data": data
    }

    with event_clients_lock:

        clients = list(event_clients)

        for event_queue in clients:

            try:
                event_queue.put_nowait(message)

            except queue.Full:

                # 如果浏览器处理不及时，丢弃最旧事件，
                # 避免事件队列无限增长。
                try:
                    event_queue.get_nowait()
                except queue.Empty:
                    pass

                try:
                    event_queue.put_nowait(message)
                except queue.Full:
                    pass


def get_state_snapshot():
    """获取当前状态快照。"""

    with state_lock:

        return {
            "active": active,
            "kg": round(current_weight, 2),
            "weight": round(current_weight, 2),
            "seq": capture_seq,
            "count": button_count,
            "button_time": button_time,
            "timestamp": last_read_time,
            "stable": weight_stable
        }


@app.route("/api/events", methods=["GET"])
def api_events():
    """
    SSE 长连接。

    浏览器建立连接后，后端会在状态变化时推送事件，
    不需要前端每隔几十毫秒轮询一次接口。
    """

    event_queue = queue.Queue(maxsize=EVENT_QUEUE_SIZE)

    with event_clients_lock:
        event_clients.add(event_queue)

    def generate():

        try:
            # 新连接先收到当前状态。
            initial_state = get_state_snapshot()

            yield (
                "event: status\n"
                "data: {}\n\n"
            ).format(json.dumps(initial_state))

            while True:

                try:
                    message = event_queue.get(timeout=15)

                    event_name = message["event"]
                    data = message["data"]

                    yield (
                        "event: {}\n"
                        "data: {}\n\n"
                    ).format(
                        event_name,
                        json.dumps(data)
                    )

                except queue.Empty:

                    # 心跳：保持连接，避免代理或浏览器
                    # 将长时间没有数据的连接关闭。
                    yield ": heartbeat\n\n"

        except GeneratorExit:
            pass

        finally:
            with event_clients_lock:
                event_clients.discard(event_queue)

    response = Response(
        stream_with_context(generate()),
        mimetype="text/event-stream"
    )

    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"

    return response


# =========================================================
# 6. 称重线程
# =========================================================

def weighing_worker(my_session_id):
    """
    本次称重的后台线程。

    只有按下实体按钮、启动会话后才会运行。
    每 0.5 秒读取一次电子秤。
    """

    global active
    global current_weight
    global capture_seq
    global last_read_time
    global no_person_since
    global last_valid_weight
    global last_weight_change_time
    global weight_stable

    print("[SESSION] 称重线程启动，session={}".format(my_session_id))

    try:

        while True:

            with state_lock:

                should_run = (
                    active
                    and session_id == my_session_id
                )

            if not should_run:
                break

            # 读取电子秤
            weight = read_scale_weight()

            now = time.time()

            if weight is not None:

                with state_lock:

                    # 防止旧线程覆盖新会话的数据
                    if (
                        not active
                        or session_id != my_session_id
                    ):
                        break

                    current_weight = weight
                    capture_seq += 1
                    last_read_time = now

                    # 判断重量是否明显变化
                    if last_valid_weight is None:

                        last_valid_weight = weight
                        last_weight_change_time = now
                        weight_stable = False

                    elif abs(weight - last_valid_weight) >= 0.2:

                        last_valid_weight = weight
                        last_weight_change_time = now
                        weight_stable = False

                    else:

                        if last_weight_change_time is None:
                            last_weight_change_time = now

                        weight_stable = (
                            now - last_weight_change_time >= 1.5
                        )

                    # 记录低重量持续时间
                    if weight < NO_PERSON_THRESHOLD:

                        if no_person_since is None:
                            no_person_since = now

                        elif (
                            now - no_person_since
                            >= NO_PERSON_DURATION
                        ):

                            active = False

                    else:
                        no_person_since = None

                    should_end = (
                        not active
                        or session_id != my_session_id
                    )

                    weight_data = {
                        "active": active,
                        "kg": round(current_weight, 2),
                        "weight": round(current_weight, 2),
                        "seq": capture_seq,
                        "count": button_count,
                        "button_time": button_time,
                        "timestamp": last_read_time,
                        "stable": weight_stable
                    }

                # 更新灯带目标
                update_led_target(weight)

                # 推送最新重量
                publish_event("weight", weight_data)

                if should_end:
                    break

            time.sleep(WEIGHT_INTERVAL)

    except Exception as e:
        print("[SESSION] 称重线程异常：{}".format(e))

    finally:

        should_publish_end = False

        with state_lock:

            # 只允许当前会话结束自己，
            # 避免旧线程误结束后来启动的新会话。
            if session_id == my_session_id:

                if active:
                    active = False

                should_publish_end = True

                final_data = {
                    "active": False,
                    "kg": round(current_weight, 2),
                    "weight": round(current_weight, 2),
                    "seq": capture_seq,
                    "count": button_count,
                    "button_time": button_time,
                    "timestamp": last_read_time,
                    "stable": weight_stable
                }

        if should_publish_end:

            publish_event(
                "session_end",
                final_data
            )

            stop_led_animation()

            print(
                "[SESSION] 称重结束，最终重量：{} kg".format(
                    final_data["kg"]
                )
            )


# =========================================================
# 7. 启动与停止称重会话
# =========================================================

def start_session():
    """
    启动一次新的称重会话。

    实体按钮脚本可以通过 POST /api/button 调用。
    """

    global active
    global current_weight
    global capture_seq
    global button_count
    global button_time
    global last_read_time
    global session_id
    global no_person_since
    global last_valid_weight
    global last_weight_change_time
    global weight_stable

    with state_lock:

        # 已经在称重，不重复启动
        if active:

            return {
                "success": True,
                "started": False,
                "active": True,
                "message": "称重已经进行中"
            }

        active = True

        session_id += 1
        my_session_id = session_id

        current_weight = 0.0

        capture_seq = 0
        button_count += 1

        button_time = time.time()
        last_read_time = None

        no_person_since = None

        last_valid_weight = None
        last_weight_change_time = None

        weight_stable = False

    # 启动灯带动画
    start_led_animation()

    # 通知前端新会话开始
    start_data = {
        "active": True,
        "session_id": my_session_id,
        "count": button_count,
        "button_time": button_time,
        "kg": 0.0,
        "weight": 0.0,
        "seq": 0,
        "stable": False
    }

    publish_event(
        "session_start",
        start_data
    )

    # 启动本次称重线程
    worker = threading.Thread(
        target=weighing_worker,
        args=(my_session_id,),
        daemon=True
    )

    worker.start()

    print(
        "[SESSION] 新会话启动，session={}".format(
            my_session_id
        )
    )

    return {
        "success": True,
        "started": True,
        "active": True,
        "session_id": my_session_id,
        "message": "称重已启动"
    }


def stop_session():
    """手动结束当前称重会话。"""

    global active

    with state_lock:

        if not active:
            return {
                "success": True,
                "active": False,
                "message": "当前没有进行中的称重"
            }

        active = False

        final_data = {
            "active": False,
            "kg": round(current_weight, 2),
            "weight": round(current_weight, 2),
            "seq": capture_seq,
            "count": button_count,
            "button_time": button_time,
            "timestamp": last_read_time,
            "stable": weight_stable
        }

    publish_event(
        "session_end",
        final_data
    )

    stop_led_animation()

    print("[SESSION] 已手动停止")

    return {
        "success": True,
        "active": False,
        "weight": final_data["weight"],
        "message": "称重已停止"
    }


# =========================================================
# 8. 首页
# =========================================================

@app.route("/", methods=["GET"])
def index():
    """显示 Minnow or Monster 主页面。"""

    return render_template("index.html")


# =========================================================
# 9. 获取重量
# =========================================================

@app.route("/api/weight", methods=["GET"])
def api_weight():
    """
    返回当前重量和会话状态。

    此接口不主动读取电子秤。
    电子秤只由称重线程读取。
    """

    return jsonify(get_state_snapshot())


# =========================================================
# 10. 实体按钮接口
# =========================================================

@app.route("/api/button", methods=["GET", "POST"])
def api_button():
    """
    POST：启动称重。
    GET：查询按钮计数和当前会话状态。
    """

    if request.method == "POST":

        result = start_session()

        status_code = 200 if result["success"] else 500

        return jsonify(result), status_code

    with state_lock:

        return jsonify({
            "active": active,
            "count": button_count,
            "button_time": button_time,
            "session_id": session_id
        })


# =========================================================
# 11. 获取称重采样数据
# =========================================================

@app.route("/api/capture", methods=["GET"])
def api_capture():
    """
    返回当前称重状态。

    为旧版前端或 Postman 调试保留。
    新版前端可以使用 /api/events 接收 SSE 事件。
    """

    return jsonify(get_state_snapshot())


# =========================================================
# 12. 手动停止接口
# =========================================================

@app.route("/api/stop", methods=["POST"])
def api_stop():

    result = stop_session()

    return jsonify(result)


# =========================================================
# 13. 健康检查
# =========================================================

@app.route("/api/health", methods=["GET"])
def api_health():

    with state_lock:

        state = {
            "active": active,
            "session_id": session_id,
            "button_count": button_count,
            "weight": round(current_weight, 2)
        }

    return jsonify({
        "success": True,
        "status": "running",
        "application": "Minnow or Monster",
        "state": state,
        "led_available": pixels is not None
    })


# =========================================================
# 14. 关闭清理
# =========================================================

def cleanup():

    print("[SYSTEM] 正在清理硬件资源")

    try:
        stop_led_animation()
    except Exception as e:
        print("[LED] 清理失败：{}".format(e))

    try:
        with scale_lock:
            client.close()
    except Exception as e:
        print("[SCALE] 关闭连接失败：{}".format(e))

    print("[SYSTEM] 清理完成")


atexit.register(cleanup)


# =========================================================
# 15. 启动 Flask
# =========================================================

if __name__ == "__main__":

    print("=" * 50)
    print("Minnow or Monster")
    print("=" * 50)

    print("[SYSTEM] 初始化 LED")
    init_led()

    # 不在启动时连接电子秤。
    # 只有实体按钮启动称重会话后，才尝试连接和读取。

    print("[SYSTEM] Flask 即将启动")
    print("[SYSTEM] 本机访问：http://127.0.0.1:8080/")
    print("[SYSTEM] SSE 接口：/api/events")
    print("[SYSTEM] 按钮接口：POST /api/button")

    app.run(
        host="0.0.0.0",
        port=8080,
        threaded=True,
        debug=False,
        use_reloader=False
    )
