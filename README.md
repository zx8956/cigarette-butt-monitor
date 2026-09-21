# 烟头与高空抛物录像辅助分析

**cigarette-butt-monitor** 是运行在 macOS 上的本地实验项目：连接 USB 摄像机录制视频，使用 YOLO / ByteTrack 分析人员，使用 YOLO-World 提取香烟与烟头候选，并提供逐帧运动回查工具，供人工复核。

**当前为 PoC，不是成熟的自动执法或高空抛物溯源系统。** 远距离快速下落的小烟头尚不能可靠识别，不能自动确定来源楼层、窗口或责任人。未检出不代表没有发生事件。仓库不包含现场录像、抓拍、住户资料、日志、数据库或模型权重。

## 摄像机与运行方式

| 项目 | 本项目使用 / 验证情况 |
| --- | --- |
| 摄像机 | 海康威视 Hikvision **DS-UVC-U168R 4K**（项目使用型号） |
| 接口 | Type-C 数据线接 Mac；线材必须支持数据传输 |
| macOS 设备名 | 实际枚举为 **4K USB Camera** |
| 采集方式 | UVC / AVFoundation；也可由 OBS 采集，再通过虚拟摄像头给 AI 提供快照 |
| 默认直连模式 | **2560×1440、30fps、NV12**；历史一分钟 HEVC 测试通过，不能据此宣称 24 小时稳定 |
| 4K 实测 | 4K30 UYVY422 和 4K25 NV12 出现缓冲区尺寸异常；4K30 NV12 完成一分钟录像但有较多重复/丢帧，因此默认不启用 |
| OBS 历史配置 | 竖屏输出 1080×1920、30fps；输出分辨率不等于摄像头原始采集分辨率 |
| 存储 | 已挂载且可写的外接硬盘，数据目录由操作者明确设置 |

这里列的是项目实测，不是厂商完整规格或对所有 Mac 的兼容性承诺。详见 [硬件验证记录](docs/hardware-validation.md)。

## 现有功能

- 枚举 AVFoundation 摄像头，探测真实 MP4 / MOV / MKV 视频。
- FFmpeg 有时长限制的分段 MKV 录像，优先使用 Apple VideoToolbox HEVC / H.264。
- 真实视频人员检测、ByteTrack ID 与轨迹摘要、带框视频导出。
- 图片 / 实时快照的 YOLO-World 开放词汇候选检测；保存原图、标注图、JSON、时间与校验信息。
- OBS AI 启动器：快照采集、失败重试、子进程管理、输入时效检查。
- 录像运动候选、连续帧拼图、启发式路径排序，辅助人工定位片段。
- 存储路径与容量策略模块，以及自动化测试。

**尚未完成：** 完整的“人员吸烟 → 新增烟头 → 人员关联”事件链、自动前 10 秒后 20 秒事件录像、来源楼层判定、SQLite 事件系统、FastAPI 审核页面和 24 小时无人值守验收。`app/api`、`app/events` 等目录与部分配置项是预留结构，不代表功能已经实现。清理策略模块存在，但目前录像命令没有完整接入持续容量巡检/自动清理。

## 安装

需要 macOS、Python 3.11–3.14、Git、FFmpeg（含 ffprobe）；本地 AI 优先使用 Apple Silicon MPS，不可用时使用 CPU。Intel 性能与摄像头组合需自行验证。OBS 工作流另需安装 [OBS Studio](https://obsproject.com/)。

```bash
git clone https://github.com/zx8956/cigarette-butt-monitor.git
cd cigarette-butt-monitor
# 已有依赖可跳过；以下命令以已安装 Homebrew 为前提
brew install python@3.11 ffmpeg
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cbm --help
```

在“系统设置 → 隐私与安全性 → 摄像头”中，为实际运行程序的 Terminal / Codex / OBS 开启权限。

### 模型准备与离线运行

默认人员模型为 `models/yolo11n.pt`，开放词汇模型为 `models/yolov8s-worldv2.pt`。首次加载可能从上游下载模型、安装文本编码依赖，并下载 CLIP 文本编码权重；**首次准备不是离线过程**。权重应来自可信的官方上游，不要加载来源不明的 `.pt`。

联网初始化模型及文本编码缓存（仅下载/加载模型，不上传录像）：

```bash
python - <<'PY'
from app.core.config import load_config
from app.detection.cigarette import CigaretteObjectDetector
from ultralytics import YOLO
YOLO('models/yolo11n.pt')
CigaretteObjectDetector(load_config())
print('模型初始化完成；请再用自己的真实图片/视频进行断网验证。')
PY
```

项目不使用付费云端推理 API。准备好模型、依赖和缓存后，可在本机执行推理；请断网跑一次自己的样本，确认缓存齐全。模型使用方式与许可证参见 [第三方说明](THIRD_PARTY_NOTICES.md)。

## 使用方法

以下命令均在仓库根目录、已激活 `.venv` 的终端执行。所有示例输入都要替换为自己的真实文件。

### 1. 离线分析真实视频或图片

```bash
cbm probe-video '/path/to/real-video.mkv'
cbm analyze-people '/path/to/real-video.mkv' --output outputs/people --max-seconds 60
cbm detect-cigarette-butts '/path/to/real-frame.jpg' --output outputs/candidates
```

人员检测输出带框视频与 Track JSON；图片检测输出带框图片与候选 JSON。YOLO-World 的文本提示不是经过本场景训练验证的烟头分类器，结果必须人工复核。

### 2. 设置外接硬盘

开源默认 `external_data_root: null`，不会直接采用开发者的硬盘。先用 `ls /Volumes` 确认硬盘已挂载，再把下例 `YOUR_DISK` 替换为真实卷名：

```bash
export CBM_DATA_ROOT='/Volumes/YOUR_DISK/cigarette-butt-monitor-data'
# 检查真实挂载点，避免误在系统盘创建同名路径
python - <<'PY'
import os
from pathlib import Path
root = Path(os.environ['CBM_DATA_ROOT']).expanduser().resolve()
assert len(root.parts) >= 4 and root.parts[1] == 'Volumes', '需使用外接卷内的独立目录'
mount = Path(*root.parts[:3])
assert mount.is_mount(), f'硬盘未挂载: {mount}'
root.mkdir(parents=True, exist_ok=True)
assert os.access(root, os.W_OK), '目录不可写'
print(root)
PY
```

该目录中会建立 `recordings/`、`events/`、`snapshots/` 等子目录。每个运行终端都需设置同一变量。`.env.example` 仅为示例，程序**不会自动读取 `.env`**；配置通过环境变量或 YAML 读取。

需要调整参数时复制 `config/default.yaml` 为 `config/local.yaml`，再执行 `export CBM_CONFIG=config/local.yaml`。不要提交本地配置或实际证据。

### 3. 直连摄像头短时录像

先关闭其他占用同一物理摄像头的程序，再运行：

```bash
cbm devices
caffeinate -dimsu cbm record-camera --duration-seconds 60
```

录像保存到外接盘 `recordings/camera01/`，同时生成 AI 输入快照。默认 30 分钟分段，60 秒测试只有一个短文件；返回报告列出编码器、实际模式、FFmpeg 状态、掉帧/重复帧与 ffprobe 信息。当前命令只使用 `preferred_modes` 中的**第一项**，不会自动遍历降级模式。

检查短测后才逐步增加时长。在另一个已设置相同 `CBM_DATA_ROOT` 的终端，可运行：

```bash
cbm monitor-cigarette-butts --duration-seconds 60
```

该命令只分析现有快照，不会自行启动摄像头。直接录像命令不是完整的长期运行守护服务，过程中应人工关注硬盘剩余容量与挂载状态。

### 4. OBS 录像 + 本地 AI

1. 在 OBS 添加“视频采集设备”，选择 `4K USB Camera`，先确认真实画面和分辨率；如旋转为竖屏，画布可设为 1080×1920。
2. 在 OBS 录制设置中选择外接盘的本项目 `recordings/camera01/`，使用 MKV，按 30 分钟分段；检查编码器与负载。
3. 点击“开始录制”和“启动虚拟摄像头”。不要同时启动直连录像命令争抢物理摄像头。
4. 确认 `pgrep -x OBS` 返回的实际 PID，再执行（将 `12345` 替换为本次 PID）：

```bash
pgrep -x OBS
python -u -m app.capture.obs_session --obs-pid 12345
```

用 `Ctrl+C` 停止 AI，录像需在 OBS 单独停止。AI 启动器不会控制 OBS 录制按钮。历史 OBS 场景为 1080×1920，但启动器当前仍请求虚拟设备 1920×1080、60fps、UYVY422。不同 OBS 版本或画布可能拒绝此模式；请先核实虚拟设备模式，必要时调整 `app/capture/obs_session.py` 中的 FFmpeg 参数后短测，不能直接假定适配。

详见 [OBS 运行说明](docs/obs-window-monitoring.md)。逐次快照采集存在间隙，不能替代连续帧分析。MacBook 需接电并避免合盖睡眠。OBS 异常退出可能造成缺录，不能宣称无人值守可靠性。

### 5. 逐帧回查运动候选

实验脚本要求 OBS 文件名为 `YYYY-MM-DD HH-MM-SS.mkv`；时间由文件名与视频时间戳相加得到，只是近似时间。以下日期和路径是格式示例：

```bash
python scripts/review_motion.py '/path/to/2026-01-01 12-00-00.mkv' outputs/review --start 0 --end 60 --scale 0.5 --top 30
python scripts/review_paths.py outputs/review/motion.json outputs/paths
python scripts/review_motion.py '/path/to/2026-01-01 12-00-00.mkv' outputs/sequence --start 10 --sequence-only --crop 0,0,400,400
```

`--crop` 为原图的 `x,y,width,height`，必须位于画面内。`motion.json`、候选拼图和路径图用于人工回查；帧差和启发式路径不是已确认烟头，也不能用于认定抛出窗口。建议先回查一分钟，长视频逐帧解码可能耗时且占用较多内存。

## 测试与项目结构

```bash
python -m pytest -q
```

自动化测试验证配置、采集命令、存储约束、快照与追踪等逻辑；不能替代真实录像和检测准确率测试。

```text
app/capture/     AVFoundation、录像、OBS AI 启动器
app/detection/   人员与开放词汇候选检测
app/storage/     路径、容量与清理策略模块
app/tracking/    Track 摘要
config/          默认配置（无个人路径）
scripts/         人工运动回查与辅助启动脚本
tests/           自动化测试
docs/            硬件实测与 OBS 使用说明
```

## 开源许可

本项目源码以 **GNU AGPL-3.0-only** 发布，见 [LICENSE](LICENSE)。依赖与模型保留其各自许可证，参见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。不随仓库分发模型权重或现场素材；模型来源链接及初始化方法见第三方说明与上文。

仅拍摄获得授权的必要区域，避免窗内私密空间，不做人脸或住户身份识别。分享问题时使用不含个人信息的日志或经脱敏的样例，不要直接上传现场证据。
