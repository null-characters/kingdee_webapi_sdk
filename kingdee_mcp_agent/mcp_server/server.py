"""
金蝶云星空 MCP Server

将金蝶 SDK 封装为 MCP 工具，供 Agent 调用。
"""

import os
import sys
import json
import logging
from typing import Optional, List, Any, Dict
from pathlib import Path

# 添加项目根目录到路径，以便导入 kingdee_sdk 包
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server.fastmcp import FastMCP

# 导入金蝶 SDK
from kingdee_sdk.client import KingdeeClient
from kingdee_sdk.auth import AuthType
from kingdee_sdk.plm_tools import PLMTools

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建 MCP 服务器
mcp = FastMCP(
    "Kingdee MCP Server",
    json_response=True
)

# 全局客户端实例（延迟初始化）
_client: Optional[KingdeeClient] = None
_plm_tools: Optional[PLMTools] = None


def get_client() -> KingdeeClient:
    """获取或创建金蝶客户端实例"""
    global _client, _plm_tools
    
    if _client is None:
        # 从环境变量读取配置（不使用硬编码默认值）
        server_url = os.getenv("KINGDEE_SERVER_URL", "")
        acct_id = os.getenv("KINGDEE_ACCT_ID", "")
        username = os.getenv("KINGDEE_USERNAME", "")
        password = os.getenv("KINGDEE_PASSWORD", "")

        if not all([server_url, acct_id, username, password]):
            raise ValueError("请设置环境变量: KINGDEE_SERVER_URL, KINGDEE_ACCT_ID, KINGDEE_USERNAME, KINGDEE_PASSWORD")
        
        _client = KingdeeClient(
            server_url=server_url,
            acct_id=acct_id,
            username=username,
            password=password,
            auth_type=AuthType.PASSWORD,
            auto_login=True,
            debug=False
        )
        _plm_tools = PLMTools(_client)
        logger.info("金蝶客户端初始化完成")
    
    return _client


def get_plm_tools() -> PLMTools:
    """获取 PLM 工具实例"""
    global _plm_tools
    if _plm_tools is None:
        get_client()
    return _plm_tools


# ==================== 通用单据工具 ====================

@mcp.tool()
def query_bill(
    form_id: str,
    field_keys: str,
    filter_string: Optional[str] = None,
    limit: int = 100
) -> List[List[Any]]:
    """
    查询金蝶单据数据
    
    Args:
        form_id: 表单ID，如 BD_MATERIAL(物料)、BD_CUSTOMER(客户)、SAL_SaleOrder(销售订单)
        field_keys: 要查询的字段，逗号分隔，如 "FNumber,FName,FSpecification"
        filter_string: 过滤条件，如 "FNumber like '%MAT%'"（可选）
        limit: 返回记录数限制，默认100
    
    Returns:
        二维列表，每行是一条记录，每列是一个字段值
    
    Examples:
        # 查询物料
        query_bill("BD_MATERIAL", "FNumber,FName,FSpecification", limit=10)
        
        # 查询特定物料
        query_bill("BD_MATERIAL", "FNumber,FName", filter_string="FNumber='MAT001'")
    """
    client = get_client()
    try:
        result = client.execute_bill_query(
            form_id=form_id,
            field_keys=field_keys,
            filter_string=filter_string,
            limit=limit
        )
        logger.info(f"查询 {form_id} 成功，返回 {len(result)} 条记录")
        return result
    except Exception as e:
        logger.error(f"查询失败: {e}")
        raise


@mcp.tool()
def view_bill(form_id: str, number: Optional[str] = None, bill_id: Optional[str] = None) -> Dict:
    """
    查看单据详情
    
    Args:
        form_id: 表单ID
        number: 单据编号（与 bill_id 二选一）
        bill_id: 单据ID（与 number 二选一）
    
    Returns:
        单据详情字典
    
    Examples:
        view_bill("BD_MATERIAL", number="MAT001")
        view_bill("BD_MATERIAL", bill_id="100001")
    """
    client = get_client()
    try:
        if number:
            data = {"Number": number}
        elif bill_id:
            data = {"Id": bill_id}
        else:
            raise ValueError("必须提供 number 或 bill_id")
        
        result = client.view(form_id, data)
        logger.info(f"查看 {form_id} 详情成功")
        return result
    except Exception as e:
        logger.error(f"查看详情失败: {e}")
        raise


@mcp.tool()
def save_bill(form_id: str, model_json: str) -> Dict:
    """
    保存单据（创建或修改）
    
    Args:
        form_id: 表单ID
        model_json: 单据数据 JSON 字符串，包含 Model 结构
    
    Returns:
        保存结果，包含单据编号、ID 等
    
    Examples:
        # 创建物料
        save_bill("BD_MATERIAL", '{"Model": {"FNumber": "NEW001", "FName": "新物料"}}')
    """
    client = get_client()
    try:
        data = json.loads(model_json)
        result = client.save(form_id, data)
        logger.info(f"保存 {form_id} 成功")
        return result
    except Exception as e:
        logger.error(f"保存失败: {e}")
        raise


@mcp.tool()
def submit_bill(form_id: str, numbers: str) -> Dict:
    """
    提交单据审批
    
    Args:
        form_id: 表单ID
        numbers: 单据编号，多个用逗号分隔
    
    Returns:
        提交结果
    
    Examples:
        submit_bill("BD_MATERIAL", "MAT001,MAT002")
    """
    client = get_client()
    try:
        number_list = [n.strip() for n in numbers.split(",")]
        data = {"Numbers": number_list}
        result = client.submit(form_id, data)
        logger.info(f"提交 {form_id} 成功: {numbers}")
        return result
    except Exception as e:
        logger.error(f"提交失败: {e}")
        raise


@mcp.tool()
def audit_bill(form_id: str, numbers: str) -> Dict:
    """
    审核单据
    
    Args:
        form_id: 表单ID
        numbers: 单据编号，多个用逗号分隔
    
    Returns:
        审核结果
    
    Examples:
        audit_bill("BD_MATERIAL", "MAT001")
    """
    client = get_client()
    try:
        number_list = [n.strip() for n in numbers.split(",")]
        data = {"Numbers": number_list}
        result = client.audit(form_id, data)
        logger.info(f"审核 {form_id} 成功: {numbers}")
        return result
    except Exception as e:
        logger.error(f"审核失败: {e}")
        raise


@mcp.tool()
def delete_bill(form_id: str, numbers: str) -> Dict:
    """
    删除单据
    
    Args:
        form_id: 表单ID
        numbers: 单据编号，多个用逗号分隔
    
    Returns:
        删除结果
    
    Examples:
        delete_bill("BD_MATERIAL", "MAT001")
    """
    client = get_client()
    try:
        number_list = [n.strip() for n in numbers.split(",")]
        data = {"Numbers": number_list}
        result = client.delete(form_id, data)
        logger.info(f"删除 {form_id} 成功: {numbers}")
        return result
    except Exception as e:
        logger.error(f"删除失败: {e}")
        raise


# ==================== PLM 物料管理工具 ====================

@mcp.tool()
def search_materials(
    keyword: Optional[str] = None,
    material_group: Optional[str] = None,
    limit: int = 50
) -> List[List[Any]]:
    """
    搜索物料
    
    Args:
        keyword: 关键词（模糊匹配名称）
        material_group: 物料分组编码
        limit: 返回数量限制
    
    Returns:
        物料列表，包含编码、名称、规格、分组、单位、重量、创建人、创建日期、状态等
    
    Examples:
        search_materials(keyword="螺丝")
        search_materials(material_group="01", limit=20)
    """
    plm = get_plm_tools()
    try:
        result = plm.search_materials(
            keyword=keyword,
            material_group=material_group,
            limit=limit
        )
        logger.info(f"搜索物料成功，返回 {len(result)} 条")
        return result
    except Exception as e:
        logger.error(f"搜索物料失败: {e}")
        raise


@mcp.tool()
def get_material_detail(material_code: str) -> Optional[Dict]:
    """
    获取物料详情
    
    Args:
        material_code: 物料编码
    
    Returns:
        物料详情字典，或 None（未找到）
    
    Examples:
        get_material_detail("MAT001")
    """
    plm = get_plm_tools()
    try:
        result = plm.query_material_by_code(material_code)
        logger.info(f"查询物料 {material_code} 详情")
        return result
    except Exception as e:
        logger.error(f"查询物料详情失败: {e}")
        raise


@mcp.tool()
def create_material(
    material_code: str,
    material_name: str,
    specification: Optional[str] = None,
    material_group: str = "",
    unit: str = "Pcs"
) -> Dict:
    """
    创建新物料
    
    Args:
        material_code: 物料编码
        material_name: 物料名称
        specification: 规格型号（可选）
        material_group: 物料分组编码（可选）
        unit: 计量单位编码，默认 Pcs
    
    Returns:
        创建结果
    
    Examples:
        create_material("NEW001", "新物料", "100x50mm", "01", "Pcs")
    """
    plm = get_plm_tools()
    try:
        result = plm.create_material(
            material_code=material_code,
            material_name=material_name,
            specification=specification,
            material_group=material_group,
            unit=unit
        )
        logger.info(f"创建物料 {material_code} 成功")
        return result
    except Exception as e:
        logger.error(f"创建物料失败: {e}")
        raise


# ==================== PLM BOM 管理工具 ====================

@mcp.tool()
def get_bom(material_code: str, version: str = "V1.0") -> Optional[Dict]:
    """
    获取物料的 BOM 结构
    
    Args:
        material_code: 父件物料编码
        version: BOM 版本，默认 V1.0
    
    Returns:
        BOM 详情，包含所有子件信息
    
    Examples:
        get_bom("PRODUCT001", "V1.0")
    """
    plm = get_plm_tools()
    try:
        result = plm.get_bom_by_material(material_code, version)
        logger.info(f"获取 {material_code} 的 BOM")
        return result
    except Exception as e:
        logger.error(f"获取 BOM 失败: {e}")
        raise


@mcp.tool()
def create_bom(
    bom_no: str,
    parent_material_code: str,
    items_json: str,
    version: str = "V1.0",
    bom_name: Optional[str] = None
) -> Dict:
    """
    创建 BOM
    
    Args:
        bom_no: BOM 编号
        parent_material_code: 父件物料编码
        items_json: 子件列表 JSON，格式: [{"material_code": "子件编码", "qty": 数量}, ...]
        version: BOM 版本，默认 V1.0
        bom_name: BOM 名称（可选）
    
    Returns:
        创建结果
    
    Examples:
        create_bom("BOM001", "PRODUCT001", '[{"material_code": "PART001", "qty": 2}]')
    """
    plm = get_plm_tools()
    try:
        items = json.loads(items_json)
        result = plm.create_bom(
            bom_no=bom_no,
            parent_material_code=parent_material_code,
            items=items,
            version=version,
            bom_name=bom_name
        )
        logger.info(f"创建 BOM {bom_no} 成功")
        return result
    except Exception as e:
        logger.error(f"创建 BOM 失败: {e}")
        raise


# ==================== PLM 变更单工具 ====================

@mcp.tool()
def get_pending_ecos(limit: int = 50) -> List[List[Any]]:
    """
    获取待审批的工程变更单列表
    
    Args:
        limit: 返回数量限制
    
    Returns:
        变更单列表，包含单号、类型、创建日期、创建人、状态、描述等
    
    Examples:
        get_pending_ecos()
    """
    plm = get_plm_tools()
    try:
        result = plm.get_pending_ecos(limit=limit)
        logger.info(f"获取待审批变更单 {len(result)} 条")
        return result
    except Exception as e:
        logger.error(f"获取变更单失败: {e}")
        raise


@mcp.tool()
def approve_eco(bill_no: str) -> Dict:
    """
    审批工程变更单
    
    Args:
        bill_no: 变更单单号
    
    Returns:
        审批结果
    
    Examples:
        approve_eco("ECO2026001")
    """
    plm = get_plm_tools()
    try:
        result = plm.approve_eco(bill_no)
        logger.info(f"审批变更单 {bill_no} 成功")
        return result
    except Exception as e:
        logger.error(f"审批变更单失败: {e}")
        raise


@mcp.tool()
def reject_eco(bill_no: str) -> Dict:
    """
    驳回工程变更单（反审核）
    
    Args:
        bill_no: 变更单单号
    
    Returns:
        驳回结果
    
    Examples:
        reject_eco("ECO2026001")
    """
    plm = get_plm_tools()
    try:
        result = plm.reject_eco(bill_no)
        logger.info(f"驳回变更单 {bill_no} 成功")
        return result
    except Exception as e:
        logger.error(f"驳回变更单失败: {e}")
        raise


# ==================== 辅助资源 ====================

@mcp.resource("kingdee://form-ids")
def get_form_ids() -> str:
    """获取常用的金蝶表单 ID 列表"""
    form_ids = """
# 金蝶云星空常用表单 ID

## 基础资料
| 名称 | FormId |
|------|--------|
| 物料 | BD_MATERIAL |
| 物料分组 | BD_MATERIALGROUP |
| 客户 | BD_CUSTOMER |
| 供应商 | BD_SUPPLIER |
| 仓库 | BD_STOCK |
| 部门 | BD_DEPARTMENT |
| 员工 | BD_STAFF |
| 币别 | BD_CURRENCY |
| 计量单位 | BD_UNIT |

## 销售管理
| 名称 | FormId |
|------|--------|
| 销售订单 | SAL_SaleOrder |
| 销售出库单 | SAL_OUTSTOCK |

## 采购管理
| 名称 | FormId |
|------|--------|
| 采购订单 | PUR_PurchaseOrder |
| 采购入库单 | STK_InStock |

## 库存管理
| 名称 | FormId |
|------|--------|
| 直接调拨单 | STK_TRANSFER |
| 盘点单 | STK_StockCount |

## 生产管理
| 名称 | FormId |
|------|--------|
| 生产订单 | PRD_MO |
| BOM | ENG_BOM |

## PLM 模块
| 名称 | FormId |
|------|--------|
| 工程变更单 | ENG_ECO |
| 图纸管理 | PLM_DRAWING |
"""
    return form_ids


@mcp.prompt()
def analyze_material_query(query: str) -> str:
    """
    帮助用户分析物料查询需求
    
    Args:
        query: 用户的自然语言查询
    """
    return f"""分析以下用户查询，确定需要调用哪个金蝶工具：

用户查询: "{query}"

请判断：
1. 是否需要查询物料？如果是，使用 search_materials 或 query_bill
2. 是否需要查看物料详情？使用 get_material_detail 或 view_bill
3. 是否需要创建物料？使用 create_material
4. 是否涉及 BOM？使用 get_bom 或 create_bom
5. 是否涉及变更单审批？使用 get_pending_ecos、approve_eco 或 reject_eco

请给出你的分析和建议的工具调用方案。"""


# ==================== 启动服务器 ====================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="金蝶云星空 MCP Server")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "sse", "streamable-http"],
                       help="传输方式: stdio, sse, streamable-http")
    parser.add_argument("--port", type=int, default=8000, help="HTTP 端口号（仅 sse/streamable-http 模式）")
    
    args = parser.parse_args()
    
    logger.info(f"启动金蝶 MCP Server，传输方式: {args.transport}")
    
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        mcp.run(transport="sse", port=args.port)
    elif args.transport == "streamable-http":
        mcp.run(transport="streamable-http", port=args.port)
