import pyautogui
import time

print("鼠标自动移动程序已启动，每分钟移动一次")
print("按 Ctrl+C 退出")

while True:
    pyautogui.moveRel(1, 0, duration=0.2)
    time.sleep(0.2)
    pyautogui.moveRel(-1, 0, duration=0.2)

    time.sleep(60)
