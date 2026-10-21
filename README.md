# 称重互动「Minnow or Monster」

访客站上秤、按一下按钮,竖屏告诉他"你和哪种巨型淡水鱼差不多重"。
启动后打开 <http://127.0.0.1:8080/> 就是展台界面,模拟模式下也能完整走完流程。

```
   浏览器(展台竖屏界面)                后端                        硬件
   static/js/app.js         GET /api/weight   ┌──────────────┐
   自己决定显示哪一屏  ─────────────────────► │              │ ◄── HX711 秤
                        GET /api/button       │  Flask 后端   │ ◄── 按钮
                        GET /api/capture      │              │
                                         └──────────────┘
```

**分工**:后端只管秤和按钮的读数,以及"按下按钮后每 0.5 秒抓一次体重";
显示哪一页、什么时候回主页面,全部在前端 `static/js/app.js` 里。
墙上的 LED 灯带不在这个后端里(由另一套控制)。

---

## 1. 直接跑起来

```powershell
cd D:\项目\新加坡博物馆2\weighing-scale
python app.py --simulate          # 或者 VS Code 打开本文件夹按 F5
```

打开 <http://127.0.0.1:8080/> 就是展台画面(**页面上没有任何按钮/调试控件**,
模拟体重和按按钮都用 Postman 打接口)。

用 Postman 走一遍完整流程:

| 步骤 | 请求 | 结果 |
|---|---|---|
| 1 | `POST /api/weight` body `{"kg": 87}` | 平台"站上"一个 87 kg 的人 |
| 2 | `POST /api/button` | 开始一次抓取会话 |
| 3 | 看画面 | **立刻**跳到 "almost as heavy as … American paddlefish"(没有中间页) |
| 4 | `POST /api/weight` body `{"kg": 320}` | 0.5 秒内画面换到 OUT OF THIS WORLD |
| 5 | `POST /api/weight` body `{"kg": 0}` | 等 5 秒,自动回主页面 |

不加 `--simulate` 时程序会自动判断:能 `import RPi.GPIO` 就用真硬件,
否则自动进模拟模式(接真秤后 `POST /api/weight` 会返回 409,重量只能来自传感器)。

---

## 2. 一次完整交互

| 步骤 | 后端在做什么 | 前端在做什么 |
|---|---|---|
| 主页面 | 每 0.1 秒读一次秤 | 显示 PDF 第一屏 "ARE YOU A MONSTER FISH?" |
| 按下按钮 | 计数 +1,**开始一次抓取会话**:每 0.5 秒把当前体重记一次(`seq` +1) | 等下一次轮询 |
| 有体重了 | `/api/capture` 返回 `active=true` 和最新 `kg` | **按重量区间直接切到对应那一页**(没有"显示重量"的中间页) |
| 重量变了 | 继续每 0.5 秒抓 | 区间变了就换页(一群人陆续站上来时会一路往上换) |
| 人走了 | 体重 < 5 kg **连续 5 秒** → 会话结束,`active=false` | 回主页面 |

* 没有"测量中/显示重量"的页面 —— 客户明确不要那一页;
* 结果页不是定时消失的:只要秤上有人就一直停在他那个区间对应的页面,
  人下去 5 秒后自动回主页面;
* 中途再按一次按钮不会重置 `seq`,只是把"连续没人"的计时清零。

---

## 3. 接口

三个 GET 接口就是全部数据来源,响应的 `Cache-Control` 都是 `no-store`。

### 3.1 `GET /api/weight` — 实时重量

```json
{ "kg": 62.35, "stable": true, "at": 1760000000.123 }
```

| 字段 | 说明 |
|---|---|
| `kg` | 平滑后的实时重量(2 位小数),平台上没人时为 0 |
| `stable` | 读数是否已稳定(最近 10 个读数极差 ≤ 1.0 kg) |
| `at` | 最近一次成功读数的时间戳(Unix 秒),0 = 还没读到过 |

用途:调试/排查用(比如 Postman 里直接看秤有没有读数)。
**界面用的是 `GET /api/capture`** —— 按下按钮后每 0.5 秒抓一次的那个值。

### 3.2 `GET /api/button` — 按钮状态

```json
{ "pressed": false, "count": 7, "at": 1760000000.123 }
```

| 字段 | 说明 |
|---|---|
| `pressed` | 按钮**当前**是否被按住(真按钮只短暂为 true) |
| `count` | 后端启动以来累计按下的次数 |
| `at` | 最后一次按下的时间戳(Unix 秒),0 = 还没按过 |

> ⚠️ 判断"按了没"请用 `count`。真实按钮按一下就松手,如果两次轮询之间正好
> 错过,`pressed` 会看不到;`count` 单调递增,数字变大就说明按过了。

### 3.3 `GET /api/capture` — 每 0.5 秒抓一次的体重(**前端主要用这个**)

```json
{ "active": true, "seq": 12, "kg": 62.4, "at": 1760000000.123 }
```

| 字段 | 说明 |
|---|---|
| `active` | 这次会话是否还在抓:按下按钮开始;**连续 5 秒没人(< 5 kg)结束** |
| `seq` | 抓取序号,每 0.5 秒 +1;前端发现变大就说明有新数据 |
| `kg` | 最近一次抓到的重量(2 位小数);还没抓到时为 `null` |
| `at` | 最近一次抓取的时间戳(Unix 秒) |

前端逻辑只有两句:

```
active = true  -> 用 kg 算出该显示哪一页,立刻切过去(区间变了就换页)
active = false -> 回到主页面
```

**没有"显示重量"的中间页** —— 按下按钮后第一笔数据一到(约 0.1 秒)就直接出结果页。

### 3.4 其它

| 接口 | 用途 |
|---|---|
| `GET /` | 展台竖屏界面 |
| `GET /api/health` | 运行状态(`ok / uptimeSec / secondsSinceReading / simulated / hardware`),给监控用 |
| `POST /api/weight` `{"kg": 62.4}` | 设置模拟重量,只有模拟模式可用(真机 409) |
| `POST /api/button` | 模拟按一下按钮(真机也能用,现场测试方便) |

**Postman 联调三步**

1. `POST /api/weight` body `{"kg": 87}`
2. `POST /api/button`
3. `GET /api/capture` → `{"active":true,"seq":3,"kg":87.1,...}`;
   把体重设成 `0`,等 5 秒再看 → `active` 变回 `false`

---

## 4. 显示规则(在前端 `static/js/prompts.js`)

按抓到的重量决定显示哪一屏,规则来自客户 PDF:

| 重量 | 那一屏 |
|---|---|
| > 300 kg | OUT OF THIS WORLD(目前没有更重的记录) |
| < 20 kg | "Awww…. Just a small baby fish." + 提示叫上朋友 |
| 落在某条鱼 ±3% | "EXCELLENT! / AMAZING! / OUTSTANDING! / SUPERB!" —— 你和它一样重 |
| 其它 | "You are almost as heavy as …"(比下一条鱼轻) |

鱼的体重阶梯(来自客户文档):

| 鱼 | 学名 | 体重 |
|---|---|---|
| GOONCH | *Bagarius bagarius* | 75 kg |
| AMERICAN PADDLEFISH | *Polyodon spathula* | 100 kg |
| ARAPAIMA | *Arapaima gigas* | 200 kg |
| GIANT BARB | *Catlocarpio siamensis* | 300 kg |

11 屏文案(含换行)、科学名、鱼图路径都在 `static/js/prompts.js`,
改文案只需要动这一个文件。

---

## 5. 版式

竖屏 1080 × 1920,严格照客户 PDF `Section 1_Interactive_MinnowOrMonster_TVPrompts.pdf`:
背景 `#005338`、标题 `#AADFF6`、Oswald 压缩体 + Chivo、居中列。
所有尺寸/间距都是从 PDF 里量出来的,写在 `static/css/style.css` 顶部注释里,
前端只切换 `data-band`(五套布局)和 `data-layout`(居中列 / 手工摆位)。

---

## 6. 目录结构

```
weighing-scale/
├── app.py              Flask 路由:展台界面 + 三个数据接口 + 模拟接口
├── monitor.py          后台采样线程:读秤 / 平滑 / 按钮 / 每 0.5 秒抓一次
├── config.py           引脚、标定、采样节奏、抓取间隔、回主页判定 —— 唯一要改的配置
├── hardware/
│   ├── __init__.py     硬件工厂:真机 or 模拟,自动判断
│   ├── scale.py        HX711 称重 · SimulatedScale
│   └── button.py       GPIO 按钮(中断去抖)· SimulatedButton
├── templates/index.html    展台竖屏页面
├── static/css/style.css    按客户 PDF 逐项量出来的版式
├── static/js/app.js        前端:按重量区间切页 / 回主页面
├── static/js/prompts.js    11 屏文案 + 分档规则
├── static/fonts/           Oswald + Chivo
├── static/images/fish/     四条鱼的插画
├── tools/build_fish_assets.py  从 ../fishes/ 母版生成上面四张插画
├── tests/test_api.py       接口 + 采样 + 连续抓取测试(不需要 pytest)
└── .vscode/                F5 直接跑、测试任务
```

---

## 7. 测试

```bash
python tests/test_api.py
```

覆盖:

1. 采样逻辑:中位数平滑、超量程剔除、稳定判定、按键计数;
2. **连续抓取**:按下按钮后每 0.5 秒抓一次、`seq` 递增、连续 5 秒没人结束会话;
3. HTTP 接口:每个接口都走一遍,包括 400 / 409 错误路径。

全部通过时打印「全部通过」,任何一项失败会列出来并以非 0 退出。
前端另有一份浏览器端验证:`_preview/verify_scale_capture.js`(不在本目录)。

---

## 8. 接硬件时要改哪里

代码里的硬件层已经是真实实现,你们接自己的硬件时只需要:

1. 在 `config.py` 改引脚(`HX711_DT_PIN` / `HX711_SCK_PIN` / `BUTTON_PIN`);
2. 标定秤:`SCALE_OFFSET` 和 `SCALE_DIVISOR`(读空秤和已知重量的原始值算出来,
   注释里写了步骤);
3. 装依赖:`pip3 install RPi.GPIO`;
4. 跑 `python app.py`(不带 `--simulate`)。

如果实际硬件和 HX711 不是一个型号,只要在 `hardware/` 里照着现有类的接口
(`read_kg()` / `is_down()` / `on_press()` / `show_kg()`)写一个新实现,
然后在 `hardware/__init__.py` 的 `build()` 里换掉即可 —— 上层代码不用动。

---

## 9. 常见问题

**Q: 打开页面只有背景色,什么都没有?**
先看浏览器控制台。如果 `prompts.js` 或 `app.js` 404,检查是不是从 `file://` 直接
打开了 `templates/index.html` —— 页面必须通过 Flask 访问(`python app.py` 后打开
<http://127.0.0.1:8080/>)。

**Q: 按了按钮,画面没有反应?**
看 `GET /api/capture` 的 `active` 和 `seq`。点按钮后 `active` 应该立刻变 true、
`seq` 每 0.5 秒 +1;如果 `seq` 不涨,说明采样线程没在跑(秤没读到东西)。
模拟模式下不应该出现;真机请检查 HX711 接线。

**Q: 结果重量总是 0?**
`SCALE_OFFSET` / `SCALE_DIVISOR` 还没标定。模拟模式下检查是不是忘记先
`POST /api/weight` 设体重。

**Q: 想改抓取频率 / 多久没人回主页面?**
都在后端 `config.py`:`CAPTURE_INTERVAL_MS`(默认 500 ms)、
`EMPTY_KG`(默认 5 kg)、`EMPTY_RESET_MS`(默认 5000 ms)。
前端 `static/js/app.js` 里的 `EMPTY_KG` 要和 `config.py` 保持一致。

**Q: `ModuleNotFoundError: No module named 'flask'`?**
VS Code 里 `Ctrl+Shift+P` → `Python: Select Interpreter` → 选
`.venv\Scripts\python.exe`。项目已带好 `.venv`。

---

## 10. 变更说明

**2026-10-18(第三次)** — 去掉页面上的模拟调试面板:

* 展台界面上**不再有任何控件**(体重输入框 / "设为体重" / "按一下按钮" / 状态栏
  全部删掉,空格键快捷触发也删了),模拟体重和按按钮一律用 Postman 打接口;
* 前端只轮询 `/api/capture`(页面切换只跟抓取数据有关),`/api/weight` 和
  `/api/button` 保留给联调;
* `/api/weight`、`/api/button`、`/api/capture` 三个接口的行为没有变化。

**2026-10-18(第二次)** — 按客户要求改成"按钮后连续抓取 + 按区间直接切页":

* **每 0.5 秒抓一次**:按下按钮开始一次抓取会话,`GET /api/capture` 的 `seq` 每
  0.5 秒 +1、`kg` 跟着更新;取代原来"采样 2.2 秒出一次结果"的 `/api/result`;
* **按重量区间直接跳页**:前端拿到体重就算该显示哪一页,没有"测量中/显示重量"
  的中间页(客户明确不要那一页);
* **连续 5 秒体重 < 5 kg 回主页面**:判定在后端(`config.EMPTY_KG` /
  `EMPTY_RESET_MS`),`active` 变 false 后前端回第一屏;
* 结果页不再定时消失:秤上有人就一直停在他那个区间对应的页面;
* 去掉了 `#meter` 那一屏(HTML/CSS/JS 里都清了)。

**2026-10-18(第一次)**

* 后端 + 前端合到一处:启动即出展台界面(`GET /`),不用再单独开一个前端;
* 显示逻辑(11 屏文案、分档规则)搬到前端 `static/js/prompts.js`,后端只给数据;
* 去掉原来的调试页(改成展台界面);
* 注释全部中文、按模块写详细。
