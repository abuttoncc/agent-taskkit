# Agent 执行手册

由 Agent 执行，用户用自然语言交代目标。PACKAGE 是当前 Skill 目录，INSTANCE 是工作区，TASK 是任务路径；所有路径按当前 shell 正确引用。只需 Python 3.9+ 标准库。

## 工作区与任务

```sh
python3 PACKAGE/scripts/harness.py init --root INSTANCE
python3 PACKAGE/scripts/harness.py tasks --root INSTANCE
python3 PACKAGE/scripts/harness.py new --root INSTANCE --topic brief --question '用户的具体目标'
```

init 可单独使用；已有项目保留 AGENTS.md、CLAUDE.md、README.md 和个人文件，只补自己的入口。需要既有任务位置时 init 加 `--tasks-dir work/tasks`（相对 INSTANCE）。已初始化实例不可用此参数偷偷搬家。任务文件夹首次 new 时才出现。

new 默认 **general/task**，只生成任务 README、request 和 task.json；非空外来目录须先明确 init，或选择允许的子目录。已有同名任务拒绝重建，先回读并续做。旧任务保留原类型和结构，不迁移。

专门任务明确选择类型：

```sh
python3 PACKAGE/scripts/harness.py new --root INSTANCE --template verify --scene api --topic api-check --question '验证目标'
python3 PACKAGE/scripts/harness.py new --root INSTANCE --template research --scene company --topic company-review --question '研究问题'
```

research 还支持 earnings、peers。详见 [验证](verify.md)、[研究](research.md)、[通用任务](general.md)。创建后仅为 DRAFT，Agent 要填写目标与完成条件再执行。inputs 等必要文件的父目录自动建立；outputs/deliverables 等空目录不预建，需要写文件时由 Agent 或相应脚本建立。

## 留交接与续做

```sh
python3 PACKAGE/scripts/harness.py checkpoint --root INSTANCE --topic brief --status active --summary '已完成材料对照' --next '补齐方案并检查交付'
python3 PACKAGE/scripts/harness.py checkpoint --root INSTANCE --topic brief --status blocked --summary '已有部分结果' --next '材料到齐后继续核对' --blocker '缺少附件；收到附件即可解除'
python3 PACKAGE/scripts/harness.py checkpoint --root INSTANCE --topic brief --status done --summary '交付已完成' --deliverable deliverables/brief.md --review '按 request 的三项要求核对内容，并重新打开文件检查'
python3 PACKAGE/scripts/harness.py handoff --root INSTANCE --topic brief
```

上面说明需替换为真实内容；不能为通过检查填示例话。`--deliverable` 可重复传入，路径相对 TASK；原位代码交付可引用任务内的交付说明和实际检查日志。done 至少需要非空交付文件、实查说明且无阻塞；unfinished 需要下一步，blocked 需要阻塞及解除条件。状态描述工作是否交付，与 API/研究的验收结论分开。

每次 checkpoint 写新 handoffs/000001.json，绑定任务定义与交付文件的指纹，不覆盖旧快照。修改定义或交付后，旧快照会报变更；核对变更原因后保存下一版。`handoff` 无快照或指纹不符退出 1，格式或路径错误退出 2。检查不证明语义正确，也不能抵抗同时恶意改写记录与文件。

tasks 只读任务文件生成总览，显示最新状态、下一步及交接问题，不重建另一份索引。多个可能的续做对象由 Agent 对照用户目标判断；不能确定才问。旧任务没有快照时显示 NO_HANDOFF，按原 README 续做，可在阶段结束时补第一份快照。

## 查看与体检

```sh
python3 PACKAGE/scripts/harness.py list
python3 PACKAGE/scripts/harness.py doctor --root INSTANCE
```

list 展示公共资源目录；tasks 展示本工作区任务。doctor 检查 general 交接、verify 合同或 research 记录；草稿显示未就绪。脚本检查、记录状态、业务结果是不同事实；授权、连通、生效没实测则为 unknown。脚本不执行任务合同里的 run_command。

## 安装与更新

先识别宿主用户级技能目录及原安装渠道。平台管理的插件沿用平台更新流程。

```sh
python3 PACKAGE/scripts/install.py install --source PACKAGE --dest 用户级技能目录/task-harness
python3 新包/scripts/install.py update --source 新包 --dest 用户级技能目录/task-harness
```

确认目标可读、当前运行时能发现 Skill；需要重载时告知。自带更新器只替换中央包，不扫描实例；目标必须由此安装器创建，有本地改动时拒绝覆盖。新包来源必须明确，hash 只说明字节一致，不代替来源信任。

v0.4 的 new 默认由 verify 改为 general，旧自动化需要显式加 `--template verify`。旧实例无 tasks_dir 时默认 projects，无需改任务文件；旧实例缺 WORKSPACE.md 也不自动重写其入口。跨机器时按原入口修正旧公共包路径；依赖旧版流程的任务可以保留独立版本，并记录原因。
