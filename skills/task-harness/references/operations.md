# Agent 执行手册

本页供执行任务的 Agent 使用，不要求用户手动操作。`PACKAGE` 替换成本 SKILL.md 所在目录，`INSTANCE` 是用户任务实例，`TASK` 是实例中的 `projects/<id>/`。路径带空格时按当前 shell 正确引用。需要 Python 3.9+ 标准库。

## 新建或继续

```sh
python3 PACKAGE/scripts/harness.py new --root INSTANCE --topic api-check --question '用户的具体问题'
```

已有实例可增加不同 topic；已有任务应继续它。外来目录或文件冲突时选新目录，不接管其他项目。生成文件只是 DRAFT：由 Agent 根据用户请求填写 spec 和 expected CSV，不把空模板交回用户当作成果。

当前实例生成器提供 verify/api。支持范围以 catalog 为准，不凭任务名字猜测底座已经实现。详细合同与后续命令见 [验证流程](verify.md)。`run_command` 只是记录，不会被公共脚本自动执行。

续做先读任务 README 的当前基线、最近结果与下一步；已有对账可用 contract.py replay 检查后再继续，不盲目重跑付费或有副作用的请求。

## 查看与体检

```sh
python3 PACKAGE/scripts/harness.py list
python3 PACKAGE/scripts/harness.py doctor --root INSTANCE
```

list 展示本包目录。doctor 是只读检查；DRAFT 合同没填完整时会报 NEEDS_ATTENTION，应由 Agent 补完已知信息。授权、连通、生效没有实测就保持 unknown。检查通过不代表业务任务已完成。

## 安装与更新

先识别当前 Agent 的用户级技能目录和原安装渠道。平台管理的插件使用平台自己的安装/更新机制，不在只读插件目录里运行自带更新器。

独立文件夹安装可使用：

```sh
python3 PACKAGE/scripts/install.py install --source PACKAGE --dest 用户级技能目录/task-harness
python3 新包/scripts/install.py update --source 新包 --dest 用户级技能目录/task-harness
```

不能把 ZIP 存在磁盘上就报告安装成功。确认目标下可读 SKILL.md 和目录资源，并检查当前运行时是否能发现这个 Skill；如运行时需要重载或重启，明确告知。文件复制、Agent 发现和真实任务通过分别报告。

自带 update 只替换中央包，不扫描实例；目标必须由本安装器创建，中央包本地改过会拒绝覆盖。新包来源必须明确，hash 只能验证字节一致，不能代替来源可信性。非本安装器创建的包沿用其原渠道更新，不强行覆盖。

跨机器后若实例入口中的公共包路径失效，修正该引用即可。依赖旧版的个人任务可使用独立版本目录，并记录版本与原因，不自动迁移冻结合同。
