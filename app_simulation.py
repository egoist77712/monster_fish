"""
Minnow or Monster - Simulation Mode

Run this file in the same folder as app.py.
It reuses app.py's LED animation, Flask routes, and SSE frontend,
but it NEVER starts the RS485 weighing thread or reads the scale.
"""

import threading
import time

import app as base


def start_simulation_session():
    """Start a frontend session without starting the real scale worker."""
    with base.state_lock:
        if base.active:
            return

        base.active = True
        base.session_id += 1
        base.current_weight = 0.0
        base.capture_seq = 0
        base.button_count += 1
        base.button_time = time.time()
        base.last_read_time = time.time()
        base.no_person_since = None
        base.last_valid_weight = None
        base.last_weight_change_time = time.time()
        base.weight_stable = False

        session_data = {
            "active": True,
            "session_id": base.session_id,
            "count": base.button_count,
            "button_time": base.button_time,
            "kg": 0.0,
            "weight": 0.0,
            "seq": 0,
            "stable": False,
        }

    base.start_led_animation()
    base.publish_event("session_start", session_data)
    print("[SIMULATION] 称重模拟会话已启动")


def set_simulated_weight(weight):
    """Update LEDs and send the simulated weight to the browser."""
    with base.state_lock:
        if not base.active:
            start_needed = True
        else:
            start_needed = False

    if start_needed:
        start_simulation_session()

    now = time.time()

    with base.state_lock:
        base.current_weight = weight
        base.capture_seq += 1
        base.last_read_time = now
        base.last_valid_weight = weight
        base.last_weight_change_time = now
        base.weight_stable = True

        data = {
            "active": True,
            "kg": round(weight, 2),
            "weight": round(weight, 2),
            "seq": base.capture_seq,
            "count": base.button_count,
            "button_time": base.button_time,
            "timestamp": base.last_read_time,
            "stable": True,
        }

    # Reuse the same LED target calculation and animation as app.py.
    base.update_led_target(weight)
    base.publish_event("weight", data)

    target_leds = base.led_target_count
    print(f"[SIMULATION] 输入重量：{weight:.1f} kg")
    print(f"[LED] Target LEDs: {target_leds} / {base.NUM_PIXELS}")
    print("[FRONTEND] 已发送重量更新")


def stop_simulation_session():
    """End the simulated session and turn off the LEDs."""
    with base.state_lock:
        if not base.active:
            print("[SIMULATION] 当前没有进行中的模拟")
            return

        base.active = False
        data = {
            "active": False,
            "kg": round(base.current_weight, 2),
            "weight": round(base.current_weight, 2),
            "seq": base.capture_seq,
            "count": base.button_count,
            "button_time": base.button_time,
            "timestamp": base.last_read_time,
            "stable": base.weight_stable,
        }

    base.publish_event("session_end", data)
    base.stop_led_animation()
    print("[SIMULATION] 模拟会话已结束，LED 已关闭")


def run_flask():
    base.app.run(
        host="0.0.0.0",
        port=8080,
        threaded=True,
        debug=False,
        use_reloader=False,
    )


def main():
    print("=" * 52)
    print("Minnow or Monster - Simulation Mode")
    print("=" * 52)

    print("[SYSTEM] 初始化 LED...")
    base.init_led()

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    print("[SYSTEM] 前端地址：http://127.0.0.1:8080/")
    print()
    print("输入重量，例如：50 或 80")
    print("输入 stop：结束模拟并关闭 LED")
    print("输入 start：重新开始模拟会话")
    print("输入 help：显示指令")
    print("输入 quit：退出程序")
    print("-" * 52)

    try:
        while True:
            command = input("\n输入重量 (kg) / 指令：").strip().lower()

            if command == "quit":
                stop_simulation_session()
                print("[SYSTEM] 退出模拟程序")
                break

            if command == "help":
                print("输入数字重量，例如 50、80、120")
                print("start = 开始新会话")
                print("stop  = 结束会话并关闭 LED")
                print("quit  = 退出程序")
                continue

            if command == "start":
                if base.active:
                    print("[SIMULATION] 会话已经开始")
                else:
                    start_simulation_session()
                continue

            if command == "stop":
                stop_simulation_session()
                continue

            try:
                weight = float(command)
                if weight < 0:
                    print("[ERROR] 重量不能小于 0")
                    continue
                if weight > 10000:
                    print("[ERROR] 输入重量过大，请检查")
                    continue
                set_simulated_weight(weight)
            except ValueError:
                print("[ERROR] 无效输入，请输入数字或 start / stop / quit")

    except (KeyboardInterrupt, EOFError):
        print("\n[SYSTEM] 收到退出指令")
        stop_simulation_session()


if __name__ == "__main__":
    main()
