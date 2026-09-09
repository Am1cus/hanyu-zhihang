# 本地全链路演示与版本范围

本仓库同时保存模型与平台源码：

- `Phase1`至`Phase4`：原有模型研究与推理；V1/V2保留，V3仅为待独立确认的仿真候选。
- `platform/cold-region-aviation-frontend`：实际Vue网页。
- `platform/cold-region-aviation-backend`：实际Spring Boot后台、H2初始化和测试。
- `demo`：启动、回放和验收辅助脚本。脚本兼容原工作区布局和本仓库布局。

从新克隆的仓库根目录执行：

```bash
./demo/start_demo.sh
# 另一个终端；数据由团队另行提供，替换为本机实际路径。
./demo/replay.sh /path/to/dataset_v2.zip F022 2
```

需要Python、Java 21、Node/npm，首次启动安装依赖。数据ZIP不随此次更新公开上传。默认H2历史库在`.demo-runtime/data`；新回放不清空已有记录。不要同时启动两套服务占用同一端口。

当前接口尚无完整鉴权，不要暴露公网。本次GitHub更新是源码版本保存，不是网站部署。`application-dev.yml`含本机开发配置，不发布；运行时显式使用`demo`配置，生产数据库迁移另行处理。

## 原工作区的同步规则

原目录`大创项目/LSTM/learn`仍是Git仓库，前后端的实际开发目录仍在`大创项目/project`。为避免搬动运行中的项目，使用显式源码同步：

```bash
.venv/bin/python tools/sync_workspace_sources.py --workspace /path/to/大创项目
```

同步后检查`git diff`和`workspace-source-manifest.json`再提交。该文件记录每个镜像源码的SHA-256；不自动删除文件、不复制数据库/依赖/原始数据，也不会自动提交或推送。新克隆用户可直接开发`platform`，无需运行此本机同步工具。

2026-09-10先保存界面优化前完整基线，再提交易读性与上手流程优化。两个GitHub提交分别保留，便于比较或回到旧界面。模型参数和实验选型结果不随界面优化改变。
