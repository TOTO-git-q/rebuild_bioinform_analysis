# 测试目录与 fixture 生命周期规则（T-01-09）

本目录定义 `auto-bioinfo` 的测试骨架与 **fixture 生命周期规则**。所有测试必须
**离线、确定性、互相隔离**：不联网、不连数据库、不连对象存储、不调付费 LLM，
重复运行结果一致，且运行后不在仓库或系统里留下残留。

## 运行方式

命令集中在仓库根的 `Makefile`（T-01-07，单一真相源）：

```bash
make test        # python -m unittest discover -t . -s tests -p "test_*.py"
make coverage    # 同一套件，coverage 包裹
make check       # 本地完整门禁：lint + format-check + typecheck + test
```

未装 `make` 时，等价命令：

```bash
python -m unittest discover -t . -s tests -p "test_*.py"
```

## 目录布局

```
tests/
├─ __init__.py                  使 tests 成为包，便于 `from tests._helpers import ...`
├─ _helpers.py                  共享离线 fixture 工厂 + 临时工作区生命周期助手
├─ test_fixture_lifecycle.py    fixture 生命周期/隔离的可执行校验（本规则的看门狗）
└─ test_*.py                    其余单元/端到端测试
```

## 三类 fixture

| 类别 | 位置 | 写入范围 | 性质 |
|---|---|---|---|
| **提交的参考 fixture** | `auto_bioinfo/fixtures/bulk_deg_demo/`（随包提交） | 只读 | 合成、离线、确定性；`source_class=SYNTHETIC_FIXTURE`、`retrieval_mode=LOCAL_CACHE`，诚实标注，**不是真实生物数据** |
| **运行期临时工作区** | 系统临时目录（`tempfile`） | 每次测试新建、用后清理 | 状态/事件/复现包等运行产物的隔离落地点 |
| **helper 合成 fixture** | 系统临时目录（`tests._helpers`） | 同上 | `tiny_fixture()` / `real_like_fixture()` 动态生成的合成矩阵 |

`real_like_fixture()` 把卡片重标为 `PUBLIC_DATABASE`，仅供资格门禁测试有一个
“看起来像真实”的基线去对抗篡改——**字节仍是同一份合成 fixture，没有真实人类来源数据**。

## 生命周期规则（强制）

1. **离线**：fixture 只从本地文件读取；`retrieval_mode` 必须是 `LOCAL_CACHE`，
   测试中不得发起任何网络请求。
2. **确定性**：相同入参产出字节一致的 fixture（无随机、无时间戳依赖）。
3. **隔离落地**：测试产物只写系统临时目录，**绝不写进仓库树**，也不写真实数据库
   或对象存储——预留的 Postgres / 对象存储端口在测试中不被实例化为外部服务。
4. **用后清理**：
   - 需要显式、即时清理的用 `tests._helpers.temp_workspace()` 上下文管理器；
   - `tiny_fixture()` / `real_like_fixture()` 创建的临时根会登记到
     `_helpers._TEMP_ROOTS`，并在解释器退出时由 `atexit` 统一清扫；
   - 直接用标准库的 `tempfile.TemporaryDirectory()` 也可（多数现有测试如此）。
5. **无敏感数据**：fixture 一律合成；真实人类来源数据、患者可识别信息、密钥
   绝不进入测试、fixture 或协调日志（见 CONSTITUTION 不变量 #5、强制停审点 #3/#4）。

`test_fixture_lifecycle.py` 把上述规则编码成测试：提交 fixture 的离线/合成标注、
helper fixture 落在系统临时目录而非仓库、临时工作区清理、`atexit` 清扫、以及
字节级确定性。新增 fixture 或改动生命周期时，先让这些测试保持绿。
