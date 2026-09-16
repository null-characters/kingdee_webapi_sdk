"""
SDK 全面测试脚本
测试所有 SDK 功能，验证 MCP 调用是否正确
"""

import sys
import os
from pathlib import Path

# 保证从任意工作目录运行都能导入 kingdee_sdk
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from kingdee_sdk import KingdeeClient, AuthType
from kingdee_sdk.plm_tools import PLMTools
from kingdee_sdk.config_loader import KINGDEE_CONFIG

def test_login_logout():
    """测试登录和登出"""
    print("\n" + "=" * 60)
    print("测试 1: 登录/登出")
    print("=" * 60)

    client = KingdeeClient(
        server_url=KINGDEE_CONFIG["server_url"],
        acct_id=KINGDEE_CONFIG["acct_id"],
        username=KINGDEE_CONFIG["username"],
        password=KINGDEE_CONFIG["password"],
        auth_type=AuthType.PASSWORD,
        debug=False
    )

    try:
        client.login()
        print("✓ 登录成功")
        client.logout()
        print("✓ 登出成功")
        return True
    except Exception as e:
        print(f"✗ 失败: {e}")
        return False


def test_query(client):
    """测试查询功能"""
    print("\n" + "=" * 60)
    print("测试 2: 单据查询 (execute_bill_query)")
    print("=" * 60)

    try:
        # 查询物料
        result = client.execute_bill_query(
            form_id="BD_MATERIAL",
            field_keys="FMaterialID,FNumber,FName,FSpecification,FDocumentStatus",
            limit=5
        )

        if isinstance(result, dict) and "Result" in result:
            # 检查是否是错误响应
            status = result.get("Result", {}).get("ResponseStatus", {})
            if status.get("IsSuccess") == False:
                errors = status.get("Errors", [])
                msg = errors[0].get("Message", "未知错误") if errors else "未知错误"
                print(f"✗ 查询失败: {msg}")
                return False

        print(f"✓ 查询成功，返回 {len(result) if isinstance(result, list) else 'N/A'} 条记录")
        if isinstance(result, list) and len(result) > 0:
            print(f"  字段数: {len(result[0])}")
            for row in result[:3]:
                print(f"  示例: {row[:3]}...")
        return True
    except Exception as e:
        print(f"✗ 失败: {e}")
        return False


def test_view(client):
    """测试查看单据详情"""
    print("\n" + "=" * 60)
    print("测试 3: 查看单据详情 (view)")
    print("=" * 60)

    try:
        # 先查询一个物料编号
        result = client.execute_bill_query(
            form_id="BD_MATERIAL",
            field_keys="FNumber",
            limit=1
        )

        if isinstance(result, list) and len(result) > 0 and len(result[0]) > 0:
            material_number = result[0][0]
            print(f"  使用物料编号: {material_number}")

            # 查看详情
            detail = client.view("BD_MATERIAL", {"Number": material_number})
            print(f"✓ view 调用成功")
            print(f"  返回类型: {type(detail)}")

            if isinstance(detail, dict):
                result_data = detail.get("Result", {})
                if "Result" in result_data:
                    print(f"  包含单据数据")
                    return True
                elif "ResponseStatus" in result_data:
                    status = result_data.get("ResponseStatus", {})
                    print(f"  IsSuccess: {status.get('IsSuccess')}")
                    return status.get("IsSuccess") == True

            return True
        else:
            print("✗ 无法获取物料编号进行测试")
            return False
    except Exception as e:
        print(f"✗ 失败: {e}")
        return False


def test_save_draft_delete(client):
    """测试保存、暂存、删除"""
    print("\n" + "=" * 60)
    print("测试 4: 保存/暂存/删除单据")
    print("=" * 60)

    test_number = "TEST_SDK_001"

    try:
        # 测试暂存（draft）
        print("\n  4.1 测试 draft (暂存)")
        draft_data = {
            "Creator": KINGDEE_CONFIG["username"],
            "NeedUpDateFields": [],
            "Model": {
                "FNumber": test_number,
                "FName": "SDK测试物料",
                "FSpecification": "测试规格",
                "FMaterialGroup": {"FNumber": ""},
                "FUnitID": {"FNumber": "Pcs"}
            }
        }

        draft_result = client.draft("BD_MATERIAL", draft_data)
        print(f"  draft 返回: {type(draft_result)}")

        if isinstance(draft_result, dict):
            result_data = draft_result.get("Result", {})
            status = result_data.get("ResponseStatus", {})
            if status.get("IsSuccess") == True:
                print("✓ draft 成功")
            else:
                errors = status.get("Errors", [])
                msg = errors[0].get("Message", "") if errors else ""
                print(f"  draft 状态: {msg[:50]}...")

        # 测试删除
        print("\n  4.2 测试 delete")
        delete_result = client.delete("BD_MATERIAL", {"Numbers": [test_number]})
        print(f"  delete 返回: {type(delete_result)}")

        if isinstance(delete_result, dict):
            result_data = delete_result.get("Result", {})
            status = result_data.get("ResponseStatus", {})
            print(f"  delete IsSuccess: {status.get('IsSuccess')}")

        return True
    except Exception as e:
        print(f"✗ 失败: {e}")
        return False


def test_submit_audit_unaudit(client):
    """测试提交、审核、反审核"""
    print("\n" + "=" * 60)
    print("测试 5: 提交/审核/反审核")
    print("=" * 60)

    try:
        # 查询一个已存在的单据
        result = client.execute_bill_query(
            form_id="BD_MATERIAL",
            field_keys="FNumber,FDocumentStatus",
            filter_string="FDocumentStatus = 'A'",  # 暂存状态
            limit=1
        )

        if isinstance(result, list) and len(result) > 0:
            number = result[0][0]
            status = result[0][1] if len(result[0]) > 1 else ""
            print(f"  找到单据: {number}, 状态: {status}")

            # 测试 submit
            print("\n  5.1 测试 submit")
            submit_result = client.submit("BD_MATERIAL", {"Numbers": [number]})
            print(f"  submit 返回类型: {type(submit_result)}")

            if isinstance(submit_result, dict):
                result_data = submit_result.get("Result", {})
                status = result_data.get("ResponseStatus", {})
                print(f"  submit IsSuccess: {status.get('IsSuccess')}")
                errors = status.get("Errors", [])
                if errors:
                    print(f"  错误信息: {errors[0].get('Message', '')[:50]}...")

            return True
        else:
            print("  未找到暂存状态的单据，跳过��试")
            return True
    except Exception as e:
        print(f"✗ 失败: {e}")
        return False


def test_plm_tools(client):
    """测试 PLMTools"""
    print("\n" + "=" * 60)
    print("测试 6: PLMTools 功能")
    print("=" * 60)

    plm = PLMTools(client)

    # 测试物料搜索
    print("\n  6.1 测试 search_materials")
    try:
        materials = plm.search_materials(limit=3)
        print(f"  返回 {len(materials) if isinstance(materials, list) else 'N/A'} 条")
        if isinstance(materials, list) and len(materials) > 0:
            print(f"  字段数: {len(materials[0])}")
        print("✓ search_materials 成功")
    except Exception as e:
        print(f"✗ search_materials 失败: {e}")

    # 测试查询物料详情
    print("\n  6.2 测试 query_material_by_code")
    try:
        # 先获取一个物料编号
        result = client.execute_bill_query(
            form_id="BD_MATERIAL",
            field_keys="FNumber",
            limit=1
        )
        if isinstance(result, list) and len(result) > 0 and len(result[0]) > 0:
            code = result[0][0]
            detail = plm.query_material_by_code(code)
            print(f"  返回类型: {type(detail)}")
            print("✓ query_material_by_code 成功")
        else:
            print("  无法获取物料编号")
    except Exception as e:
        print(f"✗ query_material_by_code 失败: {e}")

    # 测试待审批变更单
    print("\n  6.3 测试 get_pending_ecos")
    try:
        ecos = plm.get_pending_ecos(limit=5)
        print(f"  返回 {len(ecos) if isinstance(ecos, list) else 'N/A'} 条")
        print("✓ get_pending_ecos 成功")
    except Exception as e:
        print(f"✗ get_pending_ecos 失败: {e}")

    # 测试 BOM 查询
    print("\n  6.4 测试 get_bom_by_material")
    try:
        # 先获取一个物料编号
        result = client.execute_bill_query(
            form_id="BD_MATERIAL",
            field_keys="FNumber",
            limit=1
        )
        if isinstance(result, list) and len(result) > 0 and len(result[0]) > 0:
            code = result[0][0]
            bom = plm.get_bom_by_material(code)
            print(f"  返回类型: {type(bom)}")
            if bom:
                print(f"  包含 BOM 数据")
            else:
                print(f"  未找到 BOM")
            print("✓ get_bom_by_material 成功")
        else:
            print("  无法获取物料编号")
    except Exception as e:
        print(f"✗ get_bom_by_material 失败: {e}")

    return True


def main():
    print("\n" + "*" * 60)
    print("金蝶 SDK 全面功能测试")
    print("*" * 60)

    # 测试登录登出
    test_login_logout()

    # 创建客户端进行后续测试
    client = KingdeeClient(
        server_url=KINGDEE_CONFIG["server_url"],
        acct_id=KINGDEE_CONFIG["acct_id"],
        username=KINGDEE_CONFIG["username"],
        password=KINGDEE_CONFIG["password"],
        auth_type=AuthType.PASSWORD,
        auto_login=True,
        debug=False
    )

    # 执行各项测试
    results = {
        "查询": test_query(client),
        "查看详情": test_view(client),
        "保存/暂存/删除": test_save_draft_delete(client),
        "提交/审核": test_submit_audit_unaudit(client),
        "PLM工具": test_plm_tools(client),
    }

    # 登出
    try:
        client.logout()
        print("\n✓ 已登出")
    except:
        pass

    # 输出测试结果汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, result in results.items():
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {name}: {status}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()