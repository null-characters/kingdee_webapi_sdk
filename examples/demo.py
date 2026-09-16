# -*- coding: utf-8 -*-
"""金蝶云星空 WebAPI SDK - 完整演示"""

import os
import sys

# 保证以 `python examples/demo.py` 直接运行时可以导入 kingdee_sdk
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kingdee_sdk import KingdeeClient, AuthType
from kingdee_sdk.config_loader import KINGDEE_CONFIG, validate_config


def demo_basic():
    """基础登录和查询演示"""
    print("=" * 60)
    print("【演示1】基础登录和物料查询")
    print("=" * 60)
    
    client = KingdeeClient(
        server_url=KINGDEE_CONFIG["server_url"],
        acct_id=KINGDEE_CONFIG["acct_id"],
        username=KINGDEE_CONFIG["username"],
        password=KINGDEE_CONFIG["password"],
        auth_type=KINGDEE_CONFIG.get("auth_type", AuthType.PASSWORD),
        debug=False
    )
    
    try:
        client.login()
        print("[OK] 登录成功")
        
        materials = client.execute_bill_query(
            form_id="BD_MATERIAL",
            field_keys="FMaterialID,FNumber,FName",
            limit=5
        )
        print(f"[OK] 查询到 {len(materials)} 条物料记录")
        for row in list(materials)[:3]:
            print(f"  {row}")
        
        client.logout()
        print("[OK] 登出成功")
    except Exception as e:
        print(f"[FAIL] 错误: {e}")


def demo_filter():
    """带条件查询演示"""
    print("\n" + "=" * 60)
    print("【演示2】带条件查询")
    print("=" * 60)
    
    client = KingdeeClient(
        server_url=KINGDEE_CONFIG["server_url"],
        acct_id=KINGDEE_CONFIG["acct_id"],
        username=KINGDEE_CONFIG["username"],
        password=KINGDEE_CONFIG["password"],
        auth_type=KINGDEE_CONFIG.get("auth_type", AuthType.PASSWORD),
        auto_login=True
    )
    
    try:
        # 查询客户
        customers = client.execute_bill_query(
            form_id="BD_CUSTOMER",
            field_keys="FCustId,FNumber,FName",
            limit=5
        )
        print(f"[OK] 找到 {len(customers)} 个客户")
        for row in list(customers)[:3]:
            print(f"  - {row}")
    except Exception as e:
        print(f"[FAIL] 错误: {e}")


def main():
    print("\n" + "*" * 60)
    print("金蝶云星空 WebAPI SDK 功能演示")
    print("*" * 60 + "\n")
    
    missing = validate_config(KINGDEE_CONFIG)
    if missing:
        print(f"[!] 缺少配置项: {', '.join(missing)}")
        print("    请设置环境变量（推荐，见 kingdee_sdk/config.example.py 顶部说明）")
        print("    或复制 kingdee_sdk/config.example.py 为 kingdee_sdk/config.py 后填写。")
        return
    
    demo_basic()
    demo_filter()
    
    print("\n" + "=" * 60)
    print("演示完成！更多用法请参考：使用指南.md")
    print("=" * 60)


if __name__ == "__main__":
    main()
