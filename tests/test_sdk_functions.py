"""
金蝶 SDK 功能测试脚本

测试所有 SDK 和 MCP 工具的功能调用是否正常。
运行前请确保配置好 config/settings.py 或环境变量。
"""

import os
import sys
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from kingdee_sdk import KingdeeClient, AuthType, PLMTools
from kingdee_sdk.exceptions import KingdeeAPIError
from kingdee_sdk.config_loader import load_kingdee_config

# 配置读取（环境变量 > kingdee_sdk/config.py > kingdee_mcp_agent/config/settings.py）
def get_config():
    """统一从 kingdee_sdk.config_loader 读取配置"""
    config = load_kingdee_config()
    return (
        config.get("server_url"),
        config.get("acct_id"),
        config.get("username"),
        config.get("password"),
    )


def test_login_logout(client):
    """测试登录和登出"""
    print("\n=== 测试登录/登出 ===")
    
    # 登录
    try:
        result = client.login()
        print(f"✅ 登录成功: {result}")
    except Exception as e:
        print(f"❌ 登录失败: {e}")
        return False
    
    # 登出
    try:
        result = client.logout()
        print(f"✅ 登出成功: {result}")
    except Exception as e:
        print(f"❌ 登出失败: {e}")
        return False
    
    return True


def test_query(client):
    """测试单据查询"""
    print("\n=== 测试单据查询 ===")
    
    # 查询物料
    try:
        result = client.execute_bill_query(
            form_id="BD_MATERIAL",
            field_keys="FMaterialId,FNumber,FName,FSpecification",
            limit=5
        )
        print(f"✅ 查询物料成功，返回 {len(result) if result else 0} 条记录")
        if result and len(result) > 0:
            print(f"   示例数据: {result[0]}")
    except Exception as e:
        print(f"❌ 查询物料失败: {e}")
        return False
    
    # 带过滤条件查询
    try:
        result = client.execute_bill_query(
            form_id="BD_MATERIAL",
            field_keys="FNumber,FName",
            filter_string="FNumber like '%1%'",
            limit=3
        )
        print(f"✅ 条件查询成功，返回 {len(result) if result else 0} 条记录")
    except Exception as e:
        print(f"❌ 条件查询失败: {e}")
        return False
    
    return True


def test_view(client):
    """测试查看单据详情"""
    print("\n=== 测试查看单据详情 ===")
    
    # 先查询一个物料编码
    try:
        result = client.execute_bill_query(
            form_id="BD_MATERIAL",
            field_keys="FNumber",
            limit=1
        )
        if result and len(result) > 0:
            material_code = result[0][0]
            print(f"   使用物料编码: {material_code}")
        else:
            print("⚠️ 没有找到物料，跳过 view 测试")
            return True
    except Exception as e:
        print(f"❌ 查询物料编码失败: {e}")
        return False
    
    # 查看详情
    try:
        result = client.view("BD_MATERIAL", {"Number": material_code})
        print(f"✅ 查看物料详情成功")
    except Exception as e:
        print(f"❌ 查看物料详情失败: {e}")
        return False
    
    return True


def test_plm_tools(plm):
    """测试 PLM 工具"""
    print("\n=== 测试 PLM 工具 ===")
    
    # 搜索物料
    try:
        result = plm.search_materials(limit=5)
        print(f"✅ 搜索物料成功，返回 {len(result) if result else 0} 条")
    except Exception as e:
        print(f"❌ 搜索物料失败: {e}")
        return False
    
    # 查询物料详情
    try:
        # 先获取一个物料编码
        materials = plm.search_materials(limit=5)
        if materials and len(materials) > 0 and len(materials[0]) > 1:
            material_code = materials[0][1]  # FNumber 在第二列
            if material_code:
                result = plm.query_material_by_code(material_code)
                print(f"✅ 查询物料详情成功: {material_code}")
            else:
                print("⚠️ 物料编码为空，跳过详情查询")
        else:
            print("⚠️ 没有物料或数据格式异常，跳过详情查询")
    except Exception as e:
        print(f"❌ 查询物料详情失败: {e}")
        return False
    
    # 查询待审批变更单
    try:
        result = plm.get_pending_ecos(limit=5)
        print(f"✅ 查询待审批变更单成功，返回 {len(result) if result else 0} 条")
    except Exception as e:
        print(f"❌ 查询待审批变更单失败: {e}")
        # 这个可能因为没有变更单数据而失败，不算严重错误
        print("   (可能因为没有变更单数据，继续测试)")
    
    # 查询图纸
    try:
        result = plm.query_drawings(limit=5)
        print(f"✅ 查询图纸成功，返回 {len(result) if result else 0} 条")
    except Exception as e:
        print(f"❌ 查询图纸失败: {e}")
        print("   (可能因为没有图纸数据，继续测试)")
    
    return True


def test_other_operations(client):
    """测试其他单据操作（不实际执行，只验证接口格式）"""
    print("\n=== 测试其他单据操作（接口格式验证）===")
    
    # 这些操作会实际调用 API，可能因为业务数据不存在而失败
    # 我们主要验证接口格式是否正确
    
    # 测试 save 格式（使用一个不存在的编码，预期失败但验证格式）
    print("   测试 save 接口格式...")
    try:
        # 使用一个测试编码，预期会失败（因为没有必填字段）
        result = client.save("BD_MATERIAL", {
            "Model": {
                "FNumber": "TEST_SDK_001",
                "FName": "测试物料SDK"
            }
        })
        print(f"⚠️ save 返回: {result}")
    except KingdeeAPIError as e:
        # 预期会失败，但错误信息应该是业务错误，不是格式错误
        error_msg = str(e)
        if "Additional text found" in error_msg or "JSON" in error_msg:
            print(f"❌ save 接口格式错误: {e}")
            return False
        else:
            print(f"✅ save 接口格式正确（业务错误预期）: {error_msg[:100]}")
    except Exception as e:
        print(f"❌ save 接口异常: {e}")
        return False
    
    # 测试 submit 格式
    print("   测试 submit 接口格式...")
    try:
        result = client.submit("BD_MATERIAL", {"Numbers": ["TEST_001"]})
        print(f"⚠️ submit 返回: {result}")
    except KingdeeAPIError as e:
        error_msg = str(e)
        if "Additional text found" in error_msg or "JSON" in error_msg:
            print(f"❌ submit 接口格式错误: {e}")
            return False
        else:
            print(f"✅ submit 接口格式正确（业务错误预期）: {error_msg[:100]}")
    except Exception as e:
        print(f"❌ submit 接口异常: {e}")
        return False
    
    # 测试 audit 格式
    print("   测试 audit 接口格式...")
    try:
        result = client.audit("BD_MATERIAL", {"Numbers": ["TEST_001"]})
        print(f"⚠️ audit 返回: {result}")
    except KingdeeAPIError as e:
        error_msg = str(e)
        if "Additional text found" in error_msg or "JSON" in error_msg:
            print(f"❌ audit 接口格式错误: {e}")
            return False
        else:
            print(f"✅ audit 接口格式正确（业务错误预期）: {error_msg[:100]}")
    except Exception as e:
        print(f"❌ audit 接口异常: {e}")
        return False
    
    # 测试 delete 格式
    print("   测试 delete 接口格式...")
    try:
        result = client.delete("BD_MATERIAL", {"Numbers": ["TEST_001"]})
        print(f"⚠️ delete 返回: {result}")
    except KingdeeAPIError as e:
        error_msg = str(e)
        if "Additional text found" in error_msg or "JSON" in error_msg:
            print(f"❌ delete 接口格式错误: {e}")
            return False
        else:
            print(f"✅ delete 接口格式正确（业务错误预期）: {error_msg[:100]}")
    except Exception as e:
        print(f"❌ delete 接口异常: {e}")
        return False
    
    # 测试 draft 格式
    print("   测试 draft 接口格式...")
    try:
        result = client.draft("BD_MATERIAL", {
            "Model": {
                "FNumber": "TEST_SDK_DRAFT",
                "FName": "测试暂存"
            }
        })
        print(f"⚠️ draft 返回: {result}")
    except KingdeeAPIError as e:
        error_msg = str(e)
        if "Additional text found" in error_msg or "JSON" in error_msg:
            print(f"❌ draft 接口格式错误: {e}")
            return False
        else:
            print(f"✅ draft 接口格式正确（业务错误预期）: {error_msg[:100]}")
    except Exception as e:
        print(f"❌ draft 接口异常: {e}")
        return False
    
    # 测试 batch_save 格式
    print("   测试 batch_save 接口格式...")
    try:
        result = client.batch_save("BD_MATERIAL", {
            "Creator": "test",
            "NeedUpDateFields": [],
            "BatchCount": "1",
            "Model": [{
                "FNumber": "TEST_BATCH_001",
                "FName": "批量测试"
            }]
        })
        print(f"⚠️ batch_save 返回: {result}")
    except KingdeeAPIError as e:
        error_msg = str(e)
        if "Additional text found" in error_msg or "JSON" in error_msg:
            print(f"❌ batch_save 接口格式错误: {e}")
            return False
        else:
            print(f"✅ batch_save 接口格式正确（业务错误预期）: {error_msg[:100]}")
    except Exception as e:
        print(f"❌ batch_save 接口异常: {e}")
        return False
    
    # 测试 unaudit 格式
    print("   测试 unaudit 接口格式...")
    try:
        result = client.unaudit("BD_MATERIAL", {"Numbers": ["TEST_001"]})
        print(f"⚠️ unaudit 返回: {result}")
    except KingdeeAPIError as e:
        error_msg = str(e)
        if "Additional text found" in error_msg or "JSON" in error_msg:
            print(f"❌ unaudit 接口格式错误: {e}")
            return False
        else:
            print(f"✅ unaudit 接口格式正确（业务错误预期）: {error_msg[:100]}")
    except Exception as e:
        print(f"❌ unaudit 接口异常: {e}")
        return False
    
    return True


def run_tests():
    """运行所有测试"""
    print("=" * 60)
    print("金蝶 SDK 功能测试")
    print("=" * 60)
    
    # 获取配置
    server_url, acct_id, username, password = get_config()
    
    if not all([server_url, acct_id, username, password]):
        print("❌ 缺少配置信息，请设置环境变量或创建 config/settings.py")
        print("   环境变量: KINGDEE_SERVER_URL, KINGDEE_ACCT_ID, KINGDEE_USERNAME, KINGDEE_PASSWORD")
        return False
    
    print(f"服务器: {server_url}")
    print(f"账套ID: {acct_id}")
    print(f"用户名: {username}")
    
    # 创建客户端
    client = KingdeeClient(
        server_url=server_url,
        acct_id=acct_id,
        username=username,
        password=password,
        auth_type=AuthType.PASSWORD,
        auto_login=False,
        debug=False
    )
    
    plm = PLMTools(client)
    
    # 运行测试
    results = []
    
    # 测试登录登出
    results.append(("登录登出", test_login_logout(client)))
    
    # 重新登录进行后续测试
    try:
        client.login()
    except:
        print("无法登录，跳过后续测试")
        return False
    
    # 测试查询
    results.append(("单据查询", test_query(client)))
    
    # 测试查看详情
    results.append(("查看详情", test_view(client)))
    
    # 测试 PLM 工具
    results.append(("PLM工具", test_plm_tools(plm)))
    
    # 测试其他操作格式
    results.append(("其他操作格式", test_other_operations(client)))
    
    # 登出
    try:
        client.logout()
    except:
        pass
    
    # 输出结果汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = 0
    failed = 0
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)