import requests
import keyboard
import time

# Flask 服务地址
URL = "http://127.0.0.1:8080/api/button"

print("程序已启动")
print("按键盘左方向键 ← 发送 POST /api/button")
print("按 ESC 退出程序")

last_press = 0
cooldown = 0.5  # 防止长按时重复发送


while True:
    try:
        if keyboard.is_pressed("left"):
            now = time.time()

            if now - last_press >= cooldown:
                response = requests.post(URL, timeout=3)

                print("POST /api/button")
                print("HTTP 状态码:", response.status_code)
                print("服务器返回:", response.text)

                last_press = now

            # 等待按键松开，避免长按连续触发
            while keyboard.is_pressed("left"):
                time.sleep(0.05)

        if keyboard.is_pressed("esc"):
            print("程序已退出")
            break

        time.sleep(0.02)

    except requests.RequestException as e:
        print("请求失败:", e)
        time.sleep(1)

    except KeyboardInterrupt:
        print("程序已退出")
        break