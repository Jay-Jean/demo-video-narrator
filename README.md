# Demo Video Narrator · 演示视频讲解制作

把软件录屏变成**有解释、有节奏、字幕同步的演示视频**。这是一套可由不同 AI agent 执行的 skill，附带 Python 制作脚本，不依赖某一个聊天记录或专有 agent API。

它不只是“给视频读一段文字”：agent 先查看带时间戳的画面，确认操作、状态与结果，再为真实演示节奏设计旁白。脚本负责分段配音、时间对齐、字幕渲染和技术检查；agent 负责内容判断与最终视听复核。

## 默认效果与交付

- 普通话女声：**Microsoft `zh-CN-XiaoxiaoNeural`**，通过社区客户端 [`edge-tts`](https://github.com/rany2/edge-tts) 调用；自然语速、中性音调。
- 按场景分段生成语音，用 **WordBoundary** 对齐字幕，避免整段配音硬塞进视频。
- 仅在需要时小幅加速，默认上限 **1.18×**，保留音高。超过上限就修改文稿或时间窗口，不截断语音。
- 白字配半透明深色字幕底，使用真实中文字体；根据本次视频和用户要求裁剪，保持界面比例。
- H.264/AAC MP4（适合常用 PPT 播放）、独立 M4A、SRT、文稿、可编辑 JSON 计划和检查记录。
- 完整解码检查、每段声音检查、字幕时间检查和分阶段 QA 画面；这些技术检查不能替代看画面、听配音。

## 在不同 agent 中使用

仓库根目录就是 skill 目录，入口是 [`SKILL.md`](SKILL.md)。支持目录型 skill 的工具可以直接安装；不支持自动发现的 agent，也可以读取这个文件后按流程执行。需要文件/命令行工具、图像阅读能力，以及用于最终视听复核的音视频工具。

**Codex：**将仓库复制或克隆到 `~/.codex/skills/demo-video-narrator`，重载技能后调用 `$demo-video-narrator`。

**Claude Code 等目录型 skill 工具：**把仓库放到该工具的个人或项目 skill 目录，保持 `SKILL.md` 与相对目录结构。Claude Code 常见个人目录为 `~/.claude/skills/demo-video-narrator`；目录约定以所用工具为准。

**其他 agent：**把下面的请求与 `SKILL.md` 的内容交给 agent，并让它能访问仓库中的脚本与 references。仅使用文本聊天、无法读取视频画面或执行脚本的模型，不能独立完成这套流程。

```text
使用 demo-video-narrator，给 /absolute/path/demo.mp4 制作中文讲解字幕和语音旁白。
受众是业务管理者，突出主要作用与未来研究方向；只保留平台界面。
先看视频再编稿，使用默认普通话女声，按画面对齐字幕，完成后检查并交付 MP4、SRT 和文稿。
```

不要将某个项目、受众、公司名或示例裁剪坐标硬编码成所有任务的默认值。用户明确选择的语言、声音、原音保留方式和剪辑范围优先。

## 安装运行依赖

建议 Python **3.10 或更新版本**。制作代码也在 Python 3.9 环境中运行验证过，但旧 Python/pip 可能解析出不兼容依赖；推荐使用现代 Python。

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell 可改用：.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

FFmpeg 可使用系统版本，或让 `imageio-ffmpeg` 提供二进制；自定义路径可设置环境变量 `FFMPEG_EXE`。必须有 **libass、libx264 和 AAC**。无需 FFprobe。安装可用的中文字体，例如 Noto Sans CJK；macOS/Windows 常见系统字体也会自动查找。字体不随仓库分发。

Edge 配音需要联网，无需付费 API key。**旁白文字会发送到微软的在线语音端点；源视频不会由脚本上传。** 这是社区客户端，服务可用性、声音和条款由上游决定。内部保密内容应使用获准的服务或已有音频，不应默认发送。更换服务可通过下文的 `audio_file` 输入，不需更换整个制作流程。

## 跑一个不含私人内容的完整示例

```bash
python scripts/create_example.py --output work/example
python scripts/narrator.py inspect work/example/demo.mp4 --work work/inspection --interval 8
python scripts/narrator.py validate work/example/plan.json
python scripts/narrator.py build work/example/plan.json --work work/build --output output
python scripts/narrator.py verify output
```

示例由代码生成，含模拟浏览器外框和三个场景。JSON 计划裁掉外框，仅留下演示界面。**这只是制作流程的合成测试，不是实际产品功能或性能演示。** 配音会发送示例的通用中文文稿。运行后请打开 `output/video.mp4`，检查字幕、听配音，并打开 `output/qa-frames/`。

输出目录非空时，脚本默认拒绝覆盖；确认需要重做同一成片时加 `--overwrite`。中间文件保存在 `--work` 指定目录，旁白按文本、声音、语速和客户端版本缓存。不要把私有 work/output 内容提交到公开仓库。

## 制作真实视频

1. 执行 `inspect`，让 agent 打开时间戳联系表和全尺寸帧；在复杂变化处加密取帧。
2. 依据 [`references/narration-guide.md`](references/narration-guide.md) 撰写旁白，区分可见功能、预测、仿真、实测和未来目标。
3. 按 [`references/plan.md`](references/plan.md) 创建 JSON，填写源视频、每段时间窗口、声音和字幕设置。裁剪必须依据本次视频实际像素。
4. 执行 `validate`、`build`、`verify`。
5. agent 查看 QA 帧并听实际导出视频，重点检查密集内容、转场、加速段和结尾。若没有音频感知工具，应明确说明未听检，不能声称已经听过。

`verify` 会生成 `verification.json`，但其中的 `perceptual_review` 仍为 `pending`，避免把程序解码成功误写成内容与视听质量全部合格。确认过的视听结论可由使用者另行记录。

### 不同配音服务与现成录音

默认声音是可复现的偏好，不是唯一选择。其他服务、人工录音或本地 TTS 可以为每段指定：

```json
{"start": 0.5, "end": 8.5, "text": "对应的讲解文字。", "audio_file": "clips/01.wav"}
```

如有词级时间戳，再提供 `boundaries_file`。没有时间戳时脚本会标记字幕时序为近似，必须加强同步复核。脚本不会在 Edge 失败后偷偷切换为较差的系统声音，也不会用空音轨冒充完成。

## 检查和限制

```bash
python -m unittest discover -s tests -v
```

测试覆盖：时间窗口重叠、非法裁剪、字幕丢字/重复、变速后的词级时间映射、外部音频的近似对齐标记和非法字幕时序。另做过合成录屏的完整配音/裁剪/字幕/解码验证，以及独立 agent 的合成任务验证。发布前在 macOS 上运行；Windows/Linux 路径和字体做了可移植设计，尚不等于在这两个系统完成实机测试。

语音合成具有服务依赖；听感也受文稿、术语读法、场景节奏和最终音响环境影响。`loudnorm` 的单次归一化与峰值检查不是广播级响度认证。原视频字幕、复杂音轨、旋转元数据等特殊输入应先检查，再决定是否预处理。

## English summary

A portable agent skill for **scene-grounded demo narration**, not generic TTS or transcription. Read `SKILL.md`, inspect timestamped frames, author a timeline-aware JSON plan, then run `inspect → validate → build → verify` with `scripts/narrator.py`. Default: Microsoft `zh-CN-XiaoxiaoNeural` via the community Edge client, word-level alignment, limited pitch-preserving speed correction and burned-in CJK subtitles. External audio is supported per segment. Final perceptual review remains an explicit agent/user responsibility. No private reference recordings are included.

## License

MIT for this repository's code and documentation. Dependencies, voices and fonts retain their respective terms; no third-party font or voice model is redistributed.
