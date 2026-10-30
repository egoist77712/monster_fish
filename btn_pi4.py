```python
import requests
import time
import RPi.GPIO as GPIO

# Flask 服务地址
URL = "http://127.0.0.1:8080/api/button"

# 树莓派 GPIO 设置
BUTTON_PIN = 17  # BCM 编号 GPIO17，对应物理引脚 11

# 防止按钮抖动或重复触发
COOLDOWN = 0.5

last_press = 0

# 初始化 GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("程序已启动")
print("按下 GPIO17 按钮，发送 POST /api/button")
print("按 Ctrl+C 退出程序")

try:
    while True:
        # 按钮按下时，GPIO 读取 LOW
        if GPIO.input(BUTTON_PIN) == GPIO.LOW:
            now = time.time()

            if now - last_press >= COOLDOWN:
                try:
                    response = requests.post(URL, timeout=3)

                    print("POST /api/button")
                    print("HTTP 状态码:", response.status_code)
                    print("服务器返回:", response.text)

                except requests.RequestException as e:
                    print("请求失败:", e)

                last_press = time.time()

            # 等待按钮松开，避免长按重复触发
            while GPIO.input(BUTTON_PIN) == GPIO.LOW:
                time.sleep(0.05)

        time.sleep(0.02)

except KeyboardInterrupt:
    print("\n程序已退出")

finally:
    GPIO.cleanup()
    print("GPIO 已清理")
```
