# -*- coding: utf-8 -*-
"""
金蝶WebAPI 登录测试 - 密码认证方式
"""

from kingdee_sdk import KingdeeClient, AuthType


def test_login():
    # 配置参数
    server_url = "http://192.168.1.100/K3Cloud"
    acct_id = "your_acct_id"
    username = "your_username"  # 用户的真实账号
    password = "your_password"

    print("=" * 60)
    print("金蝶WebAPI 密码认证登录测试")
    print("=" * 60)
    print(f"服务器: {server_url}")
    print(f"数据中心ID: {acct_id}")
    print(f"用户名: {username}")
    print()

    client = KingdeeClient(
        server_url=server_url,
        acct_id=acct_id,
        username=username,
        password=password,
        lcid=2052,
        auth_type=AuthType.PASSWORD,
        debug=True
    )

    try:
        print("\n正在登录...")
        client.login()
        print("\n[OK] 登录成功！")

        # 测试查询
        print("\n测试查询物料...")
        result = client.execute_bill_query(
            form_id="BD_MATERIAL",
            field_keys="FMaterialID,FNumber,FName",
            limit=3
        )
        print(f"[OK] 查询成功，返回 {len(result)} 条记录")

        client.logout()
        print("\n[OK] 登出完成")

    except Exception as e:
        print(f"\n[FAIL] 失败: {e}")


if __name__ == "__main__":
    test_login()
