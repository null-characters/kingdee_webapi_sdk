# 交接说明（金蝶云星空 WebAPI SDK + 成本核算工具）

> 更新时间：2026-09 · 当前状态：**成本核算功能已实现并验证；Windows exe 已在 Windows 机器上打包成功，已交财务试用，等待反馈。**

## 1. 仓库与环境

| 项 | 值 |
|---|---|
| 仓库路径 | `/Users/fengbing/git_prj/kingdee_webapi_sdk` |
| 远端 | `https://github.com/null-characters/kingdee_webapi_sdk.git`（分支 `main`） |
| 工作区 | 干净；`data/sample_export/`、`.reasonix/` 已被 `.gitignore` 忽略（抽样数据含真实客户/价格，不入库） |
| Python | ⚠️ 本机 `python3` = `/usr/bin/python3`（3.9.6）**没装 requests**；能跑项目的是 **`/opt/anaconda3/bin/python3`**（3.13.9，requests / openpyxl 齐全）。所有命令示例都用后者 |

### 1.1 运行配置（凭证只从环境变量读取，不入库）

```bash
export KINGDEE_SERVER_URL="http://192.168.0.200/K3Cloud"
export KINGDEE_ACCT_ID="668f7c152248a3"
export KINGDEE_USERNAME="冯冰"
export KINGDEE_PASSWORD="<口令>"
```

配置优先级：代码显式传入 > 环境变量 > `kingdee_sdk/config.py` > `kingdee_mcp_agent/config/settings.py` > 内置默认值
（实现见 `kingdee_sdk/config_loader.py`）。

### 1.2 常用命令

```bash
PY=/opt/anaconda3/bin/python3

# 权限/字段探测
KINGDEE_PASSWORD='<口令>' $PY scripts/probe_cost_data_access.py

# 抽样导出（销售订单 / 物料清单 / 采购订单）→ data/sample_export/
KINGDEE_PASSWORD='<口令>' $PY scripts/explore_sample_data.py

# 按月核算并导出 Excel（命令行）
KINGDEE_PASSWORD='<口令>' $PY scripts/run_costing.py --month 2026-09 [--tax 含税] [--rate 6.7809]

# 核对核算输出（重复计数 / 层级 / 缺价 / 老价）
$PY scripts/check_costing_output.py

# Windows 工具（源码环境）
cd windows_tool && KINGDEE_PASSWORD='<口令>' $PY _smoke_check.py --month 2026-09
```

## 2. 已完成的工作

### 2.1 SDK 与 MCP（更早的提交）

- `kingdee_sdk/`：认证（密码 / API 签名）、`execute_bill_query`（含嵌套错误体识别）、`view/save/submit/audit/...`、附件上传下载、`PLMTools`（物料 / BOM / 变更单）。
- `kingdee_mcp_agent/`：MCP Server（24 个工具）+ 客户端 + Agent。
- `kingdee_sdk/config_loader.py`：环境变量优先的统一配置加载。

### 2.2 成本核算（本次新增，已推送）

| 提交 | 内容 |
|---|---|
| `eb973f9` | 取数探测脚本：币别 / 汇率 / 最近采购价 / BOM 连接率 |
| `becf9d1` | 成本核算功能：按月逐条算料本与毛利并导出 Excel + Windows 界面接上核算 |

- `kingdee_sdk/costing.py`：核算核心（`CostingCalculator` / `export_xlsx` / `month_range`）。
- `scripts/run_costing.py`：命令行核算入口。
- `scripts/check_costing_output.py`：输出核对（按「销售单号+产品」查重复计数、BOM 层级、缺价、老价分布）。
- `windows_tool/`：财务用的小工具（tkinter 界面 + PyInstaller 单文件 exe）。

### 2.3 验证状态（实测）

- 只读抽样：销售订单 50 行 / 采购订单 20 行 / BOM（含 18 行子件、54 行查询展开）落盘成功。
- 核算试算：2026-09 前 6 条销售记录跑通，合计销售额 218,105.39 / 料本 131,523.06 / 毛利 86,582.33（毛利率 39.7%）；美元单折算正确（原币 17.00 × 6.7809 = 115.2753）。
- 输出核对：按「销售单号+产品」分组后**完全重复行 0**；BOM 层级 L1~L4。
- Windows 工具四项冒烟：`[1/4] 语法检查` + `[2/4] GUI 构建` + `[3/4] 登录自检` + `[4/4] 核算验证` **全部通过**。
- ✅ **exe 已在 Windows 机器上打包成功并交给财务试用**（Mac 无法交叉生成 Windows exe，这一步只能由 Windows 完成）。

## 3. 账套事实（实测，2026-09）

### 3.1 成本核算相关的关键字段

| 用途 | 正确字段 | 备注 |
|---|---|---|
| 销售/采购结算币别 | `FSettleCurrId` | **`FCurrencyId` 不存在**（会报"字段不存在"）；`PRE001`=人民币、`PRE007`=美元 |
| 汇率 | `FExchangeRate` + `FExchangeTypeId`（`HLTX01_SYS`） | 美元单实测 6.7809 |
| 未税 / 含税单价 | `FPrice` / `FTaxPrice` | 人民币单价 = 原币单价 × 汇率；实测 82.300885 / 93.0（数量 5 → 411.5 / 465.0） |
| BOM 子件 | `FMaterialIdChild.FNumber` | **不是 `FMaterialIdCoby`**（不报错但值全为 None）、不是表列名 `FMATERIALIDCHILD`（只回内码） |
| BOM 用量 | `FNumerator` / `FDenominator` | View 接口里叫 `NUMERATOR` / `DENOMINATOR`（无 F 前缀） |
| BOM 子件单位 | `FChildUnitID.FNumber` | 如 `Pcs` |

### 3.2 四个容易踩的坑

1. **同一 BOM 编号有多条重复单据**（实测 `1.LA.LE.001083_V.0` 有 3 条不同 FID）→ 取 `FID` 最大的那张，否则用量会翻倍。
2. **采购订单 `FAmount`（未税金额）恒为 0**，未税金额必须用「单价 × 数量」自算；本位币金额要用 `FAmount_LC`。
3. **销售订单 `FCostAmount` / `FCostPercent` 全是 0**（自带成本字段没值）→ 这正是要自算的原因。
4. **价格为 0 的采购行不算成交**（实测外币采购单 `PO260916011` 价格全 0）→ 取价时自动跳过，否则会把料本算成 0。

### 3.3 不可用 / 需注意的对象

- **汇率表对象不存在**：`BD_ExchangeRate` / `BD_EXCHANGERATE` / `BD_CurrencyRate` / `BD_ExchangeRateEntry` / `SEC_ExchangeRate` 全部报"业务对象不存在"；`BD_Currency` 存在（币别清单）。→ **「当月初汇率」没有数据源**，只能默认用单据自带汇率（下单日），或人工填「覆盖汇率」。
- **「物料清单成本查询」不是业务对象**：6 个候选标识全部报"不存在"（冯冰与管理员账号结果一致，**已排除权限因素**）。它是报表/动态表单，数据由 BOM 正向展开模型实时算，WebAPI 取不到 → 成本只能自算（现已实现）。
- **PLM 文档/图纸/项目/任务**：`PLM_*` 对象不存在，需随单挂图纸时改用通用附件接口。
- `BD_MATERIALGROUP`（物料分组）不存在 → 创建物料不要传 `FMaterialGroup`。
- `ENG_ECO` / `ENG_ECN` / `ENG_BOMVERSION` 不存在（旧代码写错的标识），正确是 `ENG_ECNOrder` / `ENG_ECRApply`。

### 3.4 业务数据分布（抽样）

- 销售订单：最近 200 条已审核行里人民币 130 行、**美元 70 行（35%）**。
- 销售物料的 BOM 覆盖率：抽查 30 个销售物料，**29 个有 BOM**（例外的如 `3.D.W01.001190 磁控开关输出线`）。
- 叶子件采购价新旧：633 行叶子件里 6 行用的是 2025 年的价（最老 2025-04-28）。

## 4. 成本核算口径（与财务确认，2026-09）

| 项 | 口径 | 实现位置 |
|---|---|---|
| 结算方式 | 按月结算，每月里**每一条销售记录单独计算** | `CostingCalculator.run(date_from, date_to)` |
| 销售取价 | 销售订单的「单价」列（未税 `FPrice` / 含税 `FTaxPrice`，界面可切） | `tax_mode` |
| 采购取价 | 该物料**最近一次成交价**（最新一条已审核采购行，**不限时点**；单价为 0 不算成交） | `latest_purchase()` |
| 外币处理 | 按结算币别折人民币，**默认用单据自带汇率**，界面可填「覆盖汇率」整批指定 | `rate_of()` |
| 成本口径 | 销售产品的 BOM 递归展开到「没有 BOM 的叶子件」，叶子件用量 × 最近采购价汇总 | `expand()` / `cost_of()` |

### 已知限制（按现有口径有意为之）

1. 采购价不限时点 → 可能用到很久以前的老价（实测 6/633 行是 2025 年的价）。
2. 叶子件按「没有 BOM 就算采购件」；自制件若没维护 BOM，会被当成采购件（无采购价则按 0 计并在「备注」标注）。
3. 「当月初汇率」无数据源 → 默认下单日汇率，需要月初汇率时用界面「覆盖汇率」。
4. 未处理**单位换算**（BOM 用量单位与采购单位不同时会有偏差），明细里有「单位」列供人工核对。

## 5. Windows 工具（windows_tool/）

| 文件 | 作用 |
|---|---|
| `app.py` | tkinter 界面：登录自检 + 「结算月份 / 未税-含税 / 覆盖汇率 / 开始核算并导出 Excel」；结果导出到桌面 |
| `selfcheck.py` | 固定配置（服务器 / 账套写死）+ 登录自检逻辑；命令行 `--check` |
| `build.bat` | Windows 一键打包（`--onefile --noconsole --paths ".." --collect-submodules kingdee_sdk`） |
| `_smoke_check.py` | 打包前四项自查（语法 / 界面 / 登录 / 核算） |
| `requirements.txt` | `requests`、`openpyxl` |
| `README.md` | 打包步骤、财务使用步骤、常见问题、改动指引 |

安全约定：密码只驻内存、不落盘、不写日志；所有操作都是**只读查询**。

## 6. 脚本清单（scripts/）

| 脚本 | 用途 |
|---|---|
| `probe_cost_data_access.py` | 账号权限 + 三表单字段清单探测 |
| `explore_sample_data.py` | 三张表单抽样导出（含 BOM 全量 View）→ `data/sample_export/` |
| `explore_bom_expand.py` | BOM 子件拍平、层级判断、子件采购价 |
| `explore_bom_query_fields.py` | 定位 BOM 子件字段名的正确写法 |
| `explore_pricing_rules.py` | 币别 / 汇率 / 外币分布 / BOM 连接率 / 最近成交价取法 |
| `explore_currency.py` | 币别清单、结算币别分布、外币折算关系 |
| `run_costing.py` | 命令行核算 + 导出 Excel |
| `check_costing_output.py` | 核算输出核对 |
| `detect_acct_id.py` / `verify_material_codes.py` / `extract_submitted_items.py` | 更早的辅助脚本 |

以上除 `run_costing.py` 外都是**只读**探测/核对。

## 7. 待办 / 可选后续

1. **等财务反馈**（当前最重要）：数字口径是否认可，特别是负毛利的记录、缺价子件、以及「老价」是否需要改成"近 N 个月内的最近价"。
2. 若财务要严格按**月初汇率**：需要在工具里加「月初汇率表」的维护入口（CSV 导入或手工填），目前只有单值覆盖。
3. **单位换算**：BOM 用量单位与采购单位不一致时，料本会有偏差；需要时接 `BD_UNITCONVERT`（换算率）。
4. `docs/reference/金蝶云API探索记录.md` 是较早的探索记录，字段信息以**本文件（handoff.md）**为准（已修正工程数据模块的过时字段，其余章节若有疑问先核对账套）。
5. `tests/test_sdk_full.py`、`tests/test_sdk_functions.py` 是**可执行脚本**而非 pytest 用例（`python3 -m unittest discover -s tests` 得到 `Ran 0 tests`），可改造成 pytest，写操作用例默认 skip。
6. `examples/example.py` 的 `demo_custom_query` 把 SQL 传给 `execute_bill_query`（该接口要 `form_id` + `field_keys`），属既有缺陷。
7. 账套里遗留 2 条测试附件记录（附件内码 `2170523`、`2170536`，都挂在采购订单 `WW2551` 上），需要时人工删除。
8. 若要启用 PLM 图纸/文档管理，需由金蝶实施安装/启用对应模块。

## 8. 工具环境注意事项（省时间）

1. **解释器**：一律用 `/opt/anaconda3/bin/python3`（`/usr/bin/python3` 没有 requests）。
2. **delivery 模式下 `python3 -c`、heredoc 会被禁**：要写成脚本文件再 `python3 xxx.py`；只读命令（`grep`/`wc`/`cat`/`git status`）不受影响。
3. **写完/改完文件后必须再 `read_file` 读一次**，否则 `bash` 会被 read-evidence 规则拦下（报 `bash cannot declare which files it changes while a read-evidence requirement is outstanding`）。实测 `edit_file` 之后比 `write_file` 之后更容易卡住；被卡住时改用 `write_file` 整文件重写 + 再读一次通常能解开。子代理（`use_capability` → `tool:task`）在本项目里**不可用**（会被权限层拦）。
4. **只读探测的两种探针**：`execute_bill_query(form_id=X, field_keys='FID', limit=1)` 判断对象是否存在；`QueryBusinessInfo`（`Kingdee.Bos.WebApi.ServicesStub.DynamicFormService.QueryBusinessInfo.common.kdsvc`，参数 `{"data": "{\"FormId\":\"X\"}"}`）拿对象的表名与全部字段。
5. 取全量业务对象清单：查 `BOS_BillType` 的 `FNumber,FName,FBillFormID`（见 `docs/reference/formids_list.tsv`）。
