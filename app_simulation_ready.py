import time
import threading
import atexit

from flask import Flask, jsonify, render_template, request

import board
import neopixel
from pymodbus.client import ModbusSerialClient


# =========================================================
# 1. Flask 设置：保留原来的前端
# =========================================================

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)



# =========================================================
# 2. LED 灯带设置：120 颗 LED 对应 324 kg
# =========================================================

LED_PIN = board.D18
NUM_PIXELS = 120

# 最大对应重量：324 kg
MAX_WEIGHT_KG = 324.0

# 每颗 LED 代表的重量
KG_PER_LED = MAX_WEIGHT_KG / NUM_PIXELS  # 2.7 kg

LED_BRIGHTNESS = 0.2

# 保留原来的 LED 颜色设置
LED_COLOR = (255, 40, 0)

# 动画参数
ANIMATION_FPS = 30
ANIMATION_SPEED = 35
ANIMATION_INTERVAL = 1.0 / ANIMATION_FPS

pixels = neopixel.NeoPixel(
    LED_PIN,
    NUM_PIXELS,
    brightness=LED_BRIGHTNESS,
    auto_write=False,
    pixel_order=neopixel.GRB
)

# LED 硬件锁
led_lock = threading.Lock()

# 动画状态锁
animation_lock = threading.Lock()

# 当前动画目标和显示位置
target_led_count = 0.0
display_led_count = 0.0

# 动画运行状态
animation_running = False
animation_thread = None


def update_leds(weight):
    """
    根据重量更新 LED 点亮数量。

    120 颗 LED 对应 324 kg。
    每颗 LED 对应 2.7 kg。

    例如：
        2.7 kg   -> 1 颗 LED
        27 kg    -> 10 颗 LED
        162 kg   -> 60 颗 LED
        270 kg   -> 100 颗 LED
        324 kg   -> 120 颗 LED

    只更新目标数量，由动画线程平滑调整灯带。
    """

    global target_led_count

    weight = float(weight)

    # 将重量限制在 0 至 324 kg
    weight = max(0.0, min(weight, MAX_WEIGHT_KG))

    # 换算为需要点亮的 LED 数量
    count = weight / KG_PER_LED

    # 限制在 0 至 120 颗
    count = max(0.0, min(count, float(NUM_PIXELS)))

    with animation_lock:
        target_led_count = count

    print(
        "重量: {:.1f} kg | 目标 LED: {:.1f}/{} | "
        "每颗 LED: {:.2f} kg".format(
            weight,
            count,
            NUM_PIXELS,
            KG_PER_LED
        )
    )


def led_animation_worker():
    """
    LED 动画线程。

    逐渐增加或减少点亮数量，
    让灯带平滑地跟随真实重量变化。
    """

    global display_led_count

    while True:

        with animation_lock:
            running = animation_running
            target = target_led_count

        # 动画停止后退出线程
        if not running:
            break

        # 当前显示数量逐渐接近目标数量
        difference = target - display_led_count

        max_step = ANIMATION_SPEED * ANIMATION_INTERVAL

        if abs(difference) <= max_step:
            display_led_count = target
        elif difference > 0:
            display_led_count += max_step
        else:
            display_led_count -= max_step

        # 计算实际点亮数量
        count = int(display_led_count)

        # 刷新 LED 灯带
        with led_lock:
            pixels.fill((0, 0, 0))

            for i in range(min(count, NUM_PIXELS)):
                pixels[i] = LED_COLOR

            pixels.show()

        time.sleep(ANIMATION_INTERVAL)


def start_led_animation():
    """
    启动 LED 动画线程。
    如果动画已经运行，则不重复创建线程。
    """

    global animation_running
    global animation_thread
    global display_led_count
    global target_led_count

    with animation_lock:

        if animation_running:
            return

        # 从 0 颗开始播放点亮动画
        display_led_count = 0.0
        target_led_count = 0.0
        animation_running = True

        animation_thread = threading.Thread(
            target=led_animation_worker,
            daemon=True
        )

        animation_thread.start()

    print("LED 平滑动画已启动")


def stop_led_animation():
    """
    停止 LED 动画，并关闭所有灯。
    """

    global animation_running
    global display_led_count
    global target_led_count

    with animation_lock:
        animation_running = False
        target_led_count = 0.0
        display_led_count = 0.0

    with led_lock:
        pixels.fill((0, 0, 0))
        pixels.show()

    print("LED 动画已停止，灯带已关闭")


def turn_off_leds():
    """
    关闭所有 LED。
    保留此函数名称，兼容原来的其他代码。
    """

    stop_led_animation()


# 启动时关闭所有 LED
turn_off_leds()



# =========================================================
# 3. RS485 / Modbus 电子秤设置
# =========================================================

SERIAL_PORT = "/dev/ttyUSB0"
BAUDRATE = 9600
SLAVE_ID = 1

# 以下两个参数需要与电子秤协议一致
WEIGHT_REGISTER = 1
WEIGHT_DIVISOR = 10.0

client = ModbusSerialClient(
    port=SERIAL_PORT,
    baudrate=BAUDRATE,
    bytesize=8,
    parity="N",
    stopbits=1,
    timeout=1
)

modbus_lock = threading.Lock()


def read_scale_weight():
    """
    读取电子秤的重量。

    返回：
        float：读取成功，单位 kg
        None：读取失败

    兼容部分不同版本的 pymodbus 参数名称。
    """

    try:
        with modbus_lock:

            # 如果串口尚未连接，尝试连接
            if not getattr(client, "connected", False):
                if not client.connect():
                    print("RS485 连接失败：", SERIAL_PORT)
                    return None

            # 读取一个保持寄存器
            try:
                result = client.read_holding_registers(
                    address=WEIGHT_REGISTER,
                    count=1,
                    device_id=SLAVE_ID
                )

            except TypeError:
                try:
                    result = client.read_holding_registers(
                        address=WEIGHT_REGISTER,
                        count=1,
                        slave=SLAVE_ID
                    )
                except TypeError:
                    result = client.read_holding_registers(
                        address=WEIGHT_REGISTER,
                        count=1,
                        unit=SLAVE_ID
                    )

            if result is None or result.isError():
                print("Modbus 读取失败，请检查电子秤通信参数")
                return None

            if not result.registers:
                print("电子秤没有返回寄存器数据")
                return None

            raw_weight = result.registers[0]
            weight = raw_weight / WEIGHT_DIVISOR

            return float(weight)

    except Exception as exc:
        print("读取电子秤异常：", exc)
        return None


# =========================================================
# 4. 共享状态
# =========================================================

state_lock = threading.RLock()

active = False
current_weight = 0.0

# 自动测试模式：True 时不读取真实电子秤
simulation_mode = False

button_count = 0
button_time = 0.0

capture_seq = 0
last_read_time = 0.0

# 记录重量连续低于 5 kg 的起始时间
no_person_since = None

# 每次启动新会话时递增，避免旧线程干扰新会话
session_id = 0

worker_thread = None


# =========================================================
# 5. 后台称重线程
# =========================================================

def weighing_worker(my_session_id):
    """
    会话开始后每 0.5 秒读取一次电子秤。

    连续 5 秒重量低于 5 kg：
        1. active = False
        2. 停止采样
        3. 关闭全部 LED
    """

    global active
    global current_weight
    global capture_seq
    global last_read_time
    global no_person_since

    print("称重会话开始")

    try:
        while True:

            # 检查会话是否还在运行
            with state_lock:
                if not active or my_session_id != session_id:
                    break

            # 从真实电子秤读取重量
            weight = read_scale_weight()

            if weight is None:
                # 读数失败不能当成无人
                with state_lock:
                    if my_session_id == session_id:
                        no_person_since = None

                time.sleep(0.5)
                continue

            now = time.time()
            should_stop = False

            with state_lock:

                if not active or my_session_id != session_id:
                    break

                current_weight = weight
                capture_seq += 1
                last_read_time = now

                if weight < 5.0:

                    # 第一次低于 5 kg，开始计时
                    if no_person_since is None:
                        no_person_since = now

                    # 连续低于 5 kg 达到 5 秒，结束会话
                    elif now - no_person_since >= 5.0:
                        active = False
                        no_person_since = None
                        should_stop = True

                else:
                    # 重量恢复到 5 kg 或以上，重置计时
                    no_person_since = None

            if should_stop:
                print("重量连续 5 秒低于 5 kg，会话自动结束")
                break

            # 根据重量点亮 LED
            update_leds(weight)

            time.sleep(0.5)

    finally:

        with state_lock:
            is_current_session = (my_session_id == session_id)

        # 只允许当前会话的线程关闭灯带
        if is_current_session:
            turn_off_leds()

        print("称重线程结束")


# =========================================================
# 6. 开始和停止称重
# =========================================================

def start_session():
    """启动称重会话。"""

    global active
    global button_count
    global button_time
    global capture_seq
    global session_id
    global no_person_since
    global worker_thread
    global simulation_mode

    with state_lock:

        if active:
            return False

        active = True
        session_id += 1
        
        # 启动蓝色 LED 平滑动画
        start_led_animation()

        button_count += 1
        button_time = time.time()

        capture_seq = 0
        no_person_since = None

        my_session_id = session_id

        worker_thread = threading.Thread(
            target=weighing_worker,
            args=(my_session_id,),
            daemon=True
        )

        worker_thread.start()

    print("收到开始指令")
    return True


def stop_session():
    """停止称重并关闭 LED。"""

    global active
    global no_person_since
    global simulation_mode

    with state_lock:
        active = False
        simulation_mode = False
        no_person_since = None

    turn_off_leds()
    print("称重已停止")


# =========================================================
# 7. 前端首页：保留原来的 index.html
# =========================================================

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


# =========================================================
# 8. GET /api/weight
#    获取当前重量
# =========================================================

@app.route("/api/weight", methods=["GET"])
def get_weight():

    with state_lock:
        data = {
            "kg": current_weight,
            "weight": current_weight,
            "active": active,
            "seq": capture_seq
        }

    return jsonify(data)


# =========================================================
# 9. GET /api/button
#    获取按钮 / 会话状态
#
#    POST /api/button
#    开始称重
# =========================================================

@app.route("/api/button", methods=["GET", "POST"])
def button_api():

    if request.method == "POST":

        started = start_session()

        with state_lock:
            data = {
                "ok": True,
                "started": started,
                "active": active,
                "count": button_count
            }

        return jsonify(data)

    with state_lock:
        data = {
            "active": active,
            "pressed": active,
            "count": button_count,
            "time": button_time
        }

    return jsonify(data)


# =========================================================
# 10. GET /api/capture
#     前端轮询称重数据
# =========================================================

@app.route("/api/capture", methods=["GET"])
def capture_api():

    with state_lock:
        data = {
            "active": active,
            "kg": current_weight,
            "weight": current_weight,
            "seq": capture_seq,
            "count": button_count,
            "button_time": button_time,
            "timestamp": last_read_time
        }

    return jsonify(data)


# =========================================================
# 11. POST /api/weight
#     模拟测试接口
#
#     真机模式不允许通过 HTTP 覆盖真实重量。
# =========================================================

@app.route("/api/weight", methods=["POST"])
def set_weight():

    return jsonify({
        "ok": False,
        "error": "真实硬件模式下不能通过 POST 修改重量。自动测试请使用 /api/simulate/weight。"
    }), 403


# =========================================================
# 12. 自动模拟测试 API
#     仅在显式启动模拟模式后，才允许写入模拟重量
# =========================================================

@app.route("/api/simulate/start", methods=["POST"])
def simulate_start_api():
    global active, simulation_mode, session_id
    global current_weight, capture_seq, last_read_time, no_person_since
    global button_count, button_time

    with state_lock:
        # 防止模拟模式与真实称重会话同时运行
        if active:
            return jsonify({
                "ok": False,
                "error": "当前已有称重会话，请先停止后再开始模拟"
            }), 409

        simulation_mode = True
        active = True
        session_id += 1
        current_weight = 0.0
        capture_seq = 0
        last_read_time = time.time()
        no_person_since = None
        button_count += 1
        button_time = time.time()

    start_led_animation()

    return jsonify({
        "ok": True,
        "simulation": True,
        "active": True,
        "message": "模拟模式已启动"
    })


@app.route("/api/simulate/weight", methods=["POST"])
def simulate_weight_api():
    global current_weight, capture_seq, last_read_time

    data = request.get_json(silent=True) or {}
    try:
        weight = float(data.get("kg"))
    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "error": "请传入数字重量，例如 {"kg": 80}"
        }), 400

    if weight < 0 or weight > MAX_WEIGHT_KG:
        return jsonify({
            "ok": False,
            "error": f"模拟重量必须在 0 至 {MAX_WEIGHT_KG:.1f} kg 之间"
        }), 400

    with state_lock:
        if not active or not simulation_mode:
            return jsonify({
                "ok": False,
                "error": "模拟模式尚未启动，请先 POST /api/simulate/start"
            }), 409

        current_weight = weight
        capture_seq += 1
        last_read_time = time.time()

    # 复用真实灯带控制函数，LED 会平滑变化
    update_leds(weight)

    return jsonify({
        "ok": True,
        "simulation": True,
        "kg": weight,
        "seq": capture_seq,
        "led_target": round(weight / KG_PER_LED, 2)
    })


@app.route("/api/simulate/stop", methods=["POST"])
def simulate_stop_api():
    with state_lock:
        if not simulation_mode:
            return jsonify({
                "ok": False,
                "error": "当前不是模拟模式"
            }), 409

    stop_session()
    return jsonify({
        "ok": True,
        "active": False,
        "simulation": False,
        "message": "模拟测试已停止，LED 已关闭"
    })


# =========================================================
# 12. POST /api/stop
#     手动停止称重
# =========================================================

@app.route("/api/stop", methods=["POST"])
def stop_api():

    stop_session()

    return jsonify({
        "ok": True,
        "active": False,
        "message": "称重已停止，LED 已关闭"
    })


# =========================================================
# 13. GET /api/health
#     检查 Flask 服务是否正常
# =========================================================

@app.route("/api/health", methods=["GET"])
def health_api():

    with state_lock:
        data = {
            "ok": True,
            "active": active,
            "weight": current_weight,
            "seq": capture_seq,
            "serial_port": SERIAL_PORT,
            "simulation_mode": simulation_mode
        }

    return jsonify(data)


# =========================================================
# 14. 退出时清理硬件
# =========================================================

def cleanup():
    """程序退出时关闭 LED 和 RS485 串口。"""

    try:
        stop_session()
    except Exception as exc:
        print("关闭 LED 时发生异常：", exc)

    try:
        client.close()
    except Exception as exc:
        print("关闭 RS485 时发生异常：", exc)


atexit.register(cleanup)


# =========================================================
# 15. 启动 Flask
# =========================================================

if __name__ == "__main__":

    # 先尝试连接电子秤
    if client.connect():
        print("RS485 已连接：", SERIAL_PORT)
    else:
        print("警告：RS485 暂时无法连接，后台读取时会继续尝试")

    print("Minnow or Monster 已启动")
    print("浏览器访问：http://<树莓派IP>:8080/")
    print("硬件模式：Raspberry Pi")

    try:
        app.run(
            host="0.0.0.0",
            port=8080,
            debug=False,
            threaded=True
        )
    finally:
        cleanup()
