"""
金蝶PLM WebAPI 使用示例 - 完整版
支持：查询物料、创建BOM、审批变更单、上传图纸、附件管理等操作
"""

import os
import sys

# 保证以 `python examples/example.py` 直接运行时可以导入 kingdee_sdk
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kingdee_sdk import KingdeeClient, PLMTools
from kingdee_sdk.config_loader import KINGDEE_CONFIG, validate_config


def demo_api_sign_auth():
    """
    演示1: API签名认证方式（推荐，支持版本 PT-146911 之后）
    """
    print("=" * 60)
    print("演示1: API签名认证（SHA256）")
    print("=" * 60)

    # 初始化客户端
    client = KingdeeClient(
        server_url=KINGDEE_CONFIG["server_url"],
        acct_id=KINGDEE_CONFIG["acct_id"],
        username=KINGDEE_CONFIG["username"],
        app_id=KINGDEE_CONFIG["app_id"],
        app_secret=KINGDEE_CONFIG["app_secret"],
        lcid=KINGDEE_CONFIG["lcid"]
    )

    # 开启调试模式（输出请求详情，便于排查问题）
    client.set_debug(True)

    # 登录
    try:
        client.login()
        print("✓ 登录成功!\n")
    except Exception as e:
        print(f"✗ 登录失败: {e}")
        return None

    return client


def demo_password_auth():
    """
    演示2: 用户名密码认证方式（兼容旧版本）
    """
    print("=" * 60)
    print("演示2: 用户名密码认证")
    print("=" * 60)

    client = KingdeeClient(
        server_url=KINGDEE_CONFIG["server_url"],
        acct_id=KINGDEE_CONFIG["acct_id"],
        username=KINGDEE_CONFIG["username"],
        password=KINGDEE_CONFIG.get("password", ""),  # 需要配置密码
        lcid=KINGDEE_CONFIG["lcid"]
    )

    # 禁用自动签名（纯密码方式）
    client.use_sign_auth = False

    try:
        client.login()
        print("✓ 登录成功!\n")
    except Exception as e:
        print(f"✗ 登录失败: {e}")
        return None

    return client


def demo_query_materials(plm: PLMTools):
    """
    演示3: 查询物料
    """
    print("=" * 60)
    print("演示3: 查询物料")
    print("=" * 60)

    # 方式1: 根据物料编码精确查询
    material_code = "MAT001"  # 替换为实际的物料编码
    print(f"\n1. 查询物料 {material_code}:")
    material = plm.query_material_by_code(material_code)
    if material:
        print(f"   ✓ 找到物料: {material.get('FMaterialID', 'N/A')}")
        print(f"   名称: {material.get('FName', 'N/A')}")
        print(f"   规格: {material.get('FSpecification', 'N/A')}")
    else:
        print("   ✗ 未找到物料")

    # 方式2: 模糊搜索
    keyword = "电阻"
    print(f"\n2. 搜索关键字 '{keyword}':")
    materials = plm.search_materials(keyword=keyword, limit=5)
    print(f"   ✓ 找到 {len(materials)} 条记录")
    for mat in materials[:3]:  # 只显示前3条
        print(f"   - {mat.get('FNumber', 'N/A')}: {mat.get('FName', 'N/A')}")

    return materials


def demo_create_bom(plm: PLMTools):
    """
    演示4: 创建BOM
    """
    print("=" * 60)
    print("演示4: 创建BOM")
    print("=" * 60)

    bom_no = "1.LE.CC.050010_V.0"   # ENG_BOM 没有独立版本字段，版本并入编号
    print(f"\n创建BOM: {bom_no}")

    items = [
        {"material_code": "CHILD001", "qty": 2.0, "position": "1"},
        {"material_code": "CHILD002", "qty": 1.0, "position": "2"},
        {"material_code": "CHILD003", "qty": 3.0, "position": "3"},
    ]

    try:
        result = plm.create_bom(
            bom_no=bom_no,
            parent_material_code="1.LE.CC.050010",
            items=items,
            org_id=1  # 默认组织ID
        )
        print(f"   ✓ BOM创建成功，内码: {result.get('Id', 'N/A')}")
        print(f"   编号: {result.get('Number', 'N/A')}")
    except Exception as e:
        print(f"   ✗ 创建失败: {e}")


def demo_eco_workflow(plm: PLMTools):
    """
    演示5: 变更单审批流程
    """
    print("=" * 60)
    print("演示5: 变更单审批")
    print("=" * 60)

    # 获取待审批变更单
    print("\n1. 查询待审批变更单:")
    pending = plm.get_pending_ecos(limit=10)
    print(f"   ✓ 找到 {len(pending)} 条待审批变更单")

    if pending:
        # 显示前几条
        for eco_id, eco_no, eco_name in pending[:3]:
            print(f"   - ID:{eco_id}, 编号:{eco_no}, 名称:{eco_name}")

        # 演示审核第一个变更单（实际使用时请确认）
        first_eco = pending[0]
        print(f"\n2. 审核变更单: {first_eco[1]}")

        try:
            plm.approve_eco(first_eco[0])
            print("   ✓ 审批成功")
        except Exception as e:
            print(f"   ✗ 审批失败: {e}")
    else:
        print("   暂无待审批变更单")


def demo_attachment_operations(client: KingdeeClient, plm: PLMTools):
    """
    演示6: 附件上传/下载（通用附件接口）

    说明：通用附件接口（AttachmentUpload / AttachmentDownLoad）适用于任何单据，
          附件数据存放在 BOS_Attachment（关键字段 FFileId / FAttachmentName / FExtName）。
          图纸专用接口 PLMTools.upload_drawing 需要账套启用 PLM 图纸单据（PLM_DRAWING），
          未启用的账套会返回“业务对象不存在”。
    """
    print("=" * 60)
    print("演示6: 附件操作（通用附件接口）")
    print("=" * 60)

    file_path = "/path/to/sample.pdf"  # 替换为实际路径
    print(f"\n1. 上传附件: {file_path}")
    print("   [注：文件不存在时会跳过，此演示仅供参考]")

    try:
        # 通用附件上传（官方 AttachmentUpLoad，整文件上传）
        result = client.upload_attachment(
            file_path=file_path,
            form_id="BD_MATERIAL",
            bill_no="1.LA.LE.001001"   # 官方要求：FormId + BillNO 指向要挂附件的单据
        )
        print(f"   ✓ 上传结果: {result}")
    except (FileNotFoundError, ValueError) as e:
        print(f"   ! 文件不存在，跳过上传演示（{e}）")
    except Exception as e:
        print(f"   ✗ 上传失败: {e}")

    # 图纸接口（需要账套启用 PLM 图纸单据）
    print("\n2. 图纸上传接口签名（需要账套启用 PLM_DRAWING）:")
    print("   plm.upload_drawing(file_path=..., material_code='1.LA.LE.001001', version='V1.0')")

    # 下载附件示例
    print("\n3. 下载附件:")
    print("   file_id 取自 BOS_Attachment 的 FFileId（形如 Temp_xxx-xxx）")
    print("   client.download_attachment(file_id, save_path='./attachment.pdf')")


def demo_batch_operations(plm: PLMTools):
    """
    演示7: 批量操作
    """
    print("=" * 60)
    print("演示7: 批量操作")
    print("=" * 60)

    # 批量创建物料示例
    materials_data = [
        {
            "FNumber": "MAT-BATCH-001",
            "FName": "批量物料1",
            "FSpecification": "规格1",
            "FMaterialGroup": "01"
        },
        {
            "FNumber": "MAT-BATCH-002",
            "FName": "批量物料2",
            "FSpecification": "规格2",
            "FMaterialGroup": "01"
        }
    ]

    print(f"\n批量创建 {len(materials_data)} 个物料:")
    try:
        result = plm.batch_create_materials(materials_data)
        print(f"   ✓ 批量操作完成")
        print(f"   成功: {result.get('success_count', 0)}")
        print(f"   失败: {result.get('failure_count', 0)}")

        if result.get('errors'):
            print("   错误详情:")
            for msg in result['errors']:
                print(f"   - {msg}")
    except Exception as e:
        print(f"   ✗ 批量操作失败: {e}")


def demo_custom_query(client: KingdeeClient):
    """
    演示8: 自定义查询
    """
    print("=" * 60)
    print("演示8: 自定义SQL查询")
    print("=" * 60)

    # 使用ExecuteBillQuery进行复杂查询
    sql = """
        SELECT 
            a.FMaterialID,
            a.FNumber,
            a.FName,
            a.FSpecification,
            b.FDocumentStatus
        FROM T_BD_MATERIAL a
        LEFT JOIN T_BD_MATERIAL_L b ON a.FMaterialID = b.FMaterialID
        WHERE a.FNumber LIKE '%MAT%'
        ORDER BY a.FMaterialID DESC
    """

    print(f"\n执行查询:")
    try:
        result = client.execute_bill_query(sql, top=50)
        print(f"   ✓ 查询成功，返回 {len(result)} 条记录")

        # 显示字段名
        if result and len(result) > 0:
            print(f"   字段: {result[0]}")
    except Exception as e:
        print(f"   ✗ 查询失败: {e}")


def demo_logout(client: KingdeeClient):
    """
    演示9: 安全登出
    """
    print("=" * 60)
    print("演示9: 安全登出")
    print("=" * 60)

    try:
        client.logout()
        print("   ✓ 登出成功\n")
    except Exception as e:
        print(f"   ✗ 登出失败: {e}\n")


def main():
    """
    主函数：运行所有演示
    """
    print("\n" + "=" * 60)
    print("  金蝶云星空 PLM WebAPI SDK 使用示例")
    print("=" * 60)
    print()

    # 检查配置
    missing = validate_config(KINGDEE_CONFIG)
    if missing:
        print(f"⚠ 警告: 缺少配置项: {', '.join(missing)}")
        print("   请设置环境变量（推荐），或复制 kingdee_sdk/config.example.py 为 kingdee_sdk/config.py")
        print()
        return

    # 1. 登录（使用API签名认证）
    client = demo_api_sign_auth()
    if not client:
        print("\n登录失败，请检查配置和网络连接。")
        return

    # 初始化PLM工具
    plm = PLMTools(client)

    # 2. 查询物料
    demo_query_materials(plm)

    # 3. 创建BOM
    demo_create_bom(plm)

    # 4. 变更单审批
    demo_eco_workflow(plm)

    # 5. 附件操作
    demo_attachment_operations(client, plm)

    # 6. 批量操作
    demo_batch_operations(plm)

    # 7. 自定义查询
    demo_custom_query(client)

    # 8. 登出
    demo_logout(client)

    print("=" * 60)
    print("  所有演示完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
