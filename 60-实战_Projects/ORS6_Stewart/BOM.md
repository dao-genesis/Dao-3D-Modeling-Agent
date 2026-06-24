# ORS6 VAM 摇匀器 · 物料清单 (BOM)

**道生一: 31 STL + 6 舵机 + 硬件螺栓一览, 一生万物.**

- SR6 版本: TempestMAx Beta1 + T-wist4
- ESP32 自制件: ESP32_Mount (已反向工程)
- 总打印件: 31 件
- 舵机: 4× main + 2× pitch = 6 servo

## 一 · 3D 打印件 (31 STL)

| # | 零件名 | 文件 | 颜色 | 组 | 位置 | 变体默认 |
|---|--------|------|------|----|----|----------|
| 1 | `Base` | SR6 底座 Beta1A.stl | #bb1a1a | core | · 主视图 | - |
| 2 | `L_Frame` | SR6 L形框架 Beta1.stl | #cc2020 | core | · 主视图 | - |
| 3 | `R_Frame` | SR6 R-Frame Beta1.stl | #cc2020 | core | · 主视图 | - |
| 4 | `L_Pitcher` | SR6 L-投手 Beta1.stl | #cc2020 | core | · 主视图 | - |
| 5 | `R_Pitcher` | SR6 R-投手 Beta1.stl | #cc2020 | core | · 主视图 | - |
| 6 | `Arm` | SR6 臂 Beta1.stl | #e0ddd8 | core | · 主视图 | - |
| 7 | `Receiver` | SR6 Receiver Beta1.stl | #2a3a6a | core | · 升至 HOME_H | - |
| 8 | `Lid` | SR6 盖子 Beta1.stl | #cc2020 | core | · 主视图 | 默认 (组: lid) |
| 9 | `WindowLid` | SR6 Window Lid Beta1.stl | #cc2020 | core | · 默认隐藏 | - |
| 10 | `PowerBus` | SR6 电源总线支架 Beta1.stl | #e0ddd8 | core | · 主视图 | - |
| 11 | `Spacer` | SR6 4x3mm 垫片 Beta1.stl | #aaaaaa | core | · 默认隐藏 | - |
| 12 | `BearingMain` | SR6 轴承主连杆 Beta1.stl | #f0ede8 | linkage | · 默认隐藏 | 默认 (组: main_link) |
| 13 | `BearingPitch` | SR6 轴承投手链接 Beta1.stl | #f0ede8 | linkage | · 默认隐藏 | 默认 (组: pitch_link) |
| 14 | `MainLink` | SR6 Main Link Alpha1.stl | #f0ede8 | linkage | · 默认隐藏 | - |
| 15 | `PitcherLink` | SR6 Pitcher Link Alpha1.stl | #f0ede8 | linkage | · 默认隐藏 | - |
| 16 | `Shield` | SR6 Shield 40mm Fan.stl | #cc2020 | shield | · 主视图 | 默认 (组: shield) |
| 17 | `Shield_OLED` | SR6 Shield 40mm Fan + OLED Display.stl | #cc2020 | shield | · 默认隐藏 | - |
| 18 | `Shield_Alt` | SR6 Shield 40mm Fan + OLED Display(alternate dimen | #cc2020 | shield | · 默认隐藏 | - |
| 19 | `Tray` | SR6 Tray Standard Beta1.stl | #e0ddd8 | tray | · 升至 HOME_H | 默认 (组: tray) |
| 20 | `Tray_ScrewJack` | SR6 Tray Screw Jack Beta1.stl | #e0ddd8 | tray | · 升至 HOME_H | - |
| 21 | `Tray_XT60` | SR6 Tray XT60E1-M Beta1.stl | #e0ddd8 | tray | · 升至 HOME_H | - |
| 22 | `Twist_Base` | T-wist4 SR6 Base Beta1.stl | #cc2020 | twist | · 升至 HOME_H | - |
| 23 | `Twist_Body` | T-wist4 SR6 Body Beta1.stl | #cc2020 | twist | · 升至 HOME_H | 默认 (组: receiver) |
| 24 | `Twist_Lid` | T-wist4 Lid Beta1.stl | #e0ddd8 | twist | · 升至 HOME_H | - |
| 25 | `RingGear` | T-wist Clip Ring Gear Beta4.stl | #444444 | twist | · 升至 HOME_H | - |
| 26 | `ExchangeGear` | T-wist Exchange Gear Beta1.stl | #444444 | twist | · 升至 HOME_H | - |
| 27 | `DriveGear` | T-wist4 Drive Beta1.stl | #444444 | twist | · 升至 HOME_H | - |
| 28 | `GrommetLink` | SR6 Grommet Pitcher Link Beta1.stl | #f0ede8 | twist | · 升至 HOME_H | - |
| 29 | `L_AngleLink` | SR6 L-Pitcher Angle Link Beta1.stl | #f0ede8 | twist | · 升至 HOME_H | - |
| 30 | `R_AngleLink` | SR6 R-Pitcher Angle Link Beta1.stl | #f0ede8 | twist | · 升至 HOME_H | - |
| 31 | `ESP32_Mount` | ESP32_Mount.stl | #2288aa | custom | · 默认隐藏 | - |

## 二 · 舵机 (6×)

| # | 名称 | 类型 | X (mm) | Y (mm) | 方向 | 说明 |
|---|------|------|--------|--------|------|------|
| 1 | `LowerLeft` | main | -99.6 | +37.0 | ← | 下左主轴 |
| 2 | `UpperLeft` | main | -99.6 | -37.0 | ← | 上左主轴 |
| 3 | `LeftPitch` | pitch | -99.6 | +0.0 | ← | 左 pitch |
| 4 | `RightPitch` | pitch | +99.6 | +0.0 | → | 右 pitch |
| 5 | `UpperRight` | main | +99.6 | -37.0 | → | 上右主轴 |
| 6 | `LowerRight` | main | +99.6 | +37.0 | → | 下右主轴 |

**推荐舵机**: DS3225/DS3235 (25kg·cm, 数字, 270° 行程, 金属齿轮).

## 三 · 硬件 (螺栓 / 轴承 / 杆件)

| 类别 | 规格 | 数量 | 说明 |
|------|------|------|------|
| 主连杆 | M5 × 175mm | 4× | `mainRod=175.0mm`, √30625, PDF p.26 |
| pitch 连杆 | M5 × 175mm | 2× | 共享规格, 两端球头 |
| 主臂 | **50mm** | 4× | `mainArm=50mm` (firmware 2a=100→a=50) |
| pitch 臂 | **75mm** | 2× | `pitchArm=75mm` (firmware 2a=150→a=75) |
| 主轴承 | BearingMain | 4× | 轴承主连杆 Beta1 |
| pitch 轴承 | BearingPitch | 2× | 轴承投手链接 Beta1 |
| 受托盘 | Tray | 1× | 默认 Standard (可选 ScrewJack/XT60) |
| T-wist 齿轮组 | 环+交换+驱动 | 1 套 | T-wist4 Beta4 |
| 底盘 | Base | 1× | SR6 底座 Beta1A |
| 框架 | L_Frame + R_Frame | 1 对 | 矩形布局, 间距 199.2mm |

## 四 · 电子

| 器件 | 规格 | 说明 |
|------|------|------|
| 主控 | ESP32 DevKit C | 6× PWM 舵机 + TCode 串口 + WiFi OTA |
| 承载器 | ESP32_Mount | 自制 STL (已逆向) |
| 电源 | 5V @ 15A | DS3225 峰值 2.5A/台 × 6 = 15A |
| 电源总线 | PowerBus | STL |
| 连接器 | XT60 / XT90 | 主电源入口 |
| OLED (可选) | 0.96" I2C | Shield_OLED 配套 |
| 风扇 (可选) | 40mm 12V | Shield 预留 |

## 五 · 关键几何常数 (不可变)

```python
SR6 = {
    'baseH'         : 162.48,
    'mainArm'       : 50.0,
    'mainRod'       : 175.0,
    'pitchArm'      : 75.0,
    'pitchOff'      : 55.0,
    'pitchAng'      : 15.0,
    'msPerRad'      : 637,
    'servoPivotH'   : 46.0,
}
HOME_H = 208.48  # = servoPivotH + baseH
ROD_LEN_MM = 175.0  # 物理真相: 所有 6 杆严等
```

## 六 · 变体选择 (打一套留两套)

- **lid** → 默认 `Lid`, 可选 `WindowLid`
- **shield** → 默认 `Shield`, 可选 `Shield_OLED`, `Shield_Alt`
- **tray** → 默认 `Tray`, 可选 `Tray_ScrewJack`, `Tray_XT60`
- **main_link** → 默认 `BearingMain`, 可选 `MainLink`
- **pitch_link** → 默认 `BearingPitch`, 可选 `PitcherLink`, `GrommetLink`
- **receiver** → 默认 `Twist_Body`, 可选 `Receiver`

## 七 · 打印参数建议

- **材料**: PLA+ (强度足, 易后处理) 或 PETG (耐温, 用于舵机附近)
- **层高**: 0.2mm (结构件) / 0.15mm (齿轮)
- **填充**: 40% (默认), 60% (受力件: Arm/Pitcher/Frame)
- **支撑**: 树形支撑 (L/R 框架内腔需要)
- **方向**:
  - `Base`, `L_Frame`, `R_Frame`: 平放
  - `Arm`, `L/R_Pitcher`: 舵盘面朝下
  - `Receiver`, `Twist_*`: 平放, 防 warping

## 八 · 体积估算 (总耗材)

(调用 `python -m ORS6_Stewart.cli mass` 得到精确值)

| 估算 | 值 |
|------|-----|
| 总件数 | {} |
| 总件数 | 31 |
| 必选打印 | ~16 件 (31 − 15 隐藏变体) |
| 默认变体隐藏 | 15 件 |

---

_生成时间_: 2026-05-09 22:39:36  
_工具_: `python ORS6_Stewart/tools/gen_deliverables.py`  
_真相来源_: `ORS6_Stewart.parts.PARTS` + `SERVO_SLOTS` + `SR6`  
