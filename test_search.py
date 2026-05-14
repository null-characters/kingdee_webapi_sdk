# -*- coding: utf-8 -*-
"""
验证查找功能测试脚本
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kingdee_sdk import KingdeeClient, AuthType
from kingdee_sdk.config import KINGDEE_CONFIG


def test_basic_query():
    """测试基础查询"""
    print("\n" + "="*60)
    print("测试: 基础单据查询")
    print("="*60)
    
    client = KingdeeClient(
        server_url=KINGDEE_CONFIG["server_url"],
        acct_id=KINGDEE_CONFIG["acct_id"],
        username=KINGDEE_CONFIG["username"],
        password=KINGDEE_CONFIG["password"],
        auth_type=AuthType.PASSWORD
    )
    
    try:
        client.login()
        print("[OK] 登录成功")
        
        # 查询物料
        print("\n>>> 查询物料 (BD_MATERIAL)")
        materials = client.execute_bill_query(
            form_id="BD_MATERIAL",
            field_keys="FMaterialID,FNumber,FName",
            limit=5
        )
        print(f"返回 {len(materials)} 条记录")
        for row in materials:
            print(f"  {row}")
        
        client.logout()
        print("\n[OK] 基础查询测试通过")
        return True
    except Exception as e:
        print(f"\n[FAIL] 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_filter():
    """测试过滤查询"""
    print("\n" + "="*60)
    print("测试: 带过滤条件的查询")
    print("="*60)
    
    client = KingdeeClient(
        server_url=KINGDEE_CONFIG["server_url"],
        acct_id=KINGDEE_CONFIG["acct_id"],
        username=KINGDEE_CONFIG["username"],
        password=KINGDEE_CONFIG["password"],
        auth_type=AuthType.PASSWORD
    )
    
    try:
        client.login()
        print("[OK] 登录成功")
        
        print("\n>>> 模糊查询编号包含M的物料")
        result = client.execute_bill_query(
            form_id="BD_MATERIAL",
            field_keys="FNumber,FName",
            filter_string="FNumber like '%M%'",
            limit=5
        )
        print(f"返回 {len(result)} 条记录")
        for row in result:
            print(f"  {row}")
        
        client.logout()
        print("\n[OK] 过滤查询测试通过")
        return True
    except Exception as e:
        print(f"\n[FAIL] 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("="*60)
    print("金蝶SDK 查找功能验证测试")
    print("="*60)
    
    r1 = test_basic_query()
    r2 = test_filter()
    
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    print(f"  [{'OK' if r1 else 'FAIL'}] 基础查询")
    print(f"  [{'OK' if r2 else 'FAIL'}] 过滤查询")
    print(f"\n总计: {sum([r1,r2])}/2 通过")
