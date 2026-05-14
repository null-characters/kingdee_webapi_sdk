"""
金蝶数据中心ID检测工具
根据服务器地址和登录信息，自动获取数据中心ID
"""

import requests
import json
import re


def get_datacenter_list(server_url: str):
    """
    获取服务器上所有数据中心列表
    """
    url = f"{server_url}/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.SystemProfile.LoadDataCenters.common.kdsvc"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("ResponseStatus", {}).get("IsSuccess", False):
                result = data.get("Result", {}).get("Result", [])
                return result
    except Exception as e:
        print(f"获取数据中心列表失败: {e}")

    return None


def try_login_get_acct_id(server_url: str, username: str, password: str = ""):
    """
    尝试登录并获取数据中心ID
    """
    # 默认尝试几个常见的数据中心ID
    common_acct_ids = [
        "A",      # 默认测试账套
        "1",      # 常见ID
        "1001",   # 常见ID
        "6123456789ABC",  # 示例格式
    ]

    datacenters = get_datacenter_list(server_url)

    if datacenters:
        print("\n✓ 成功获取数据中心列表！")
        print("-" * 60)
        for dc in datacenters:
            print(f"  名称: {dc.get('FDataCenterName', 'N/A')}")
            print(f"  ID: {dc.get('FDataCenterID', 'N/A')}")
            print(f"  状态: {'已启用' if dc.get('FStatus') == 1 else '未启用'}")
            print("-" * 60)
        return datacenters

    return None


def detect_from_webconsole(server_url: str):
    """
    尝试从Web控制台页面获取数据中心信息
    """
    try:
        # 访问登录相关的API
        url = f"{server_url}/K3Cloud/html5/index.aspx"
        response = requests.get(url, timeout=10, allow_redirects=True)

        # 查找页面中的数据中心信息
        html = response.text

        # 尝试匹配常见的数据中心ID格式
        patterns = [
            r'dbid[=:]\s*["\']?([^"\'\s&]+)',  # dbid=xxx
            r'datacenter[=:]\s*["\']?([^"\'\s&]+)',  # datacenter=xxx
            r'acctid[=:]\s*["\']?([^"\'\s&]+)',  # acctid=xxx
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                print(f"\n✓ 从页面中找到可能的ID: {matches}")
                return matches

    except Exception as e:
        print(f"页面分析失败: {e}")

    return None


def manual_guide():
    """
    手动获取指南
    """
    print("\n" + "=" * 60)
    print("手动获取数据中心ID的方法")
    print("=" * 60)
    print("""
方法1：从Web端界面查看
  1. 登录 http://192.168.1.100/K3Cloud/
  2. 点击顶部菜单【系统管理】
  3. 选择【数据中心】或【查询用户】
  4. 在列表中查看"数据中心标识"列

方法2：询问管理员
  - 直接问："金蝶系统的数据中心ID是多少？"
  - 或者问："DBACCTNAME是什么？"

方法3：从数据库查看（需要管理员权限）
  - 登录数据库，执行：SELECT * FROM T_BAS_DATACENTER

方法4：配置文件查找
  - 在服务器上找 K3Cloud 配置文件
  - 搜索 "DataCenter" 关键字
""")


def main():
    print("=" * 60)
    print("  金蝶数据中心ID检测工具")
    print("=" * 60)

    # 配置（请根据实际情况修改）
    server_url = "http://192.168.1.100/K3Cloud"
    username = input("请输入用户名（直接回车使用Administrator）：").strip() or "Administrator"

    print(f"\n服务器地址: {server_url}")
    print(f"用户名: {username}")
    print("\n正在检测...")

    # 方法1: 获取数据中心列表
    print("\n[方法1] 尝试获取数据中心列表...")
    datacenters = try_login_get_acct_id(server_url, username)

    if datacenters:
        print("\n✓ 检测完成！请使用上表中的 'ID' 值作为 acct_id")
        return

    # 方法2: 从页面分析
    print("\n[方法2] 尝试分析页面...")
    ids = detect_from_webconsole(server_url)

    if ids:
        print(f"\n✓ 找到可能的ID: {ids}")
        print("  请尝试使用这些ID值")
        return

    # 失败，显示手动指南
    print("\n✗ 自动检测失败，请尝试手动获取：")
    manual_guide()

    # 提供常用测试ID
    print("\n" + "=" * 60)
    print("常见数据中心ID格式（可以尝试）：")
    print("=" * 60)
    test_ids = ["A", "1", "1001", "2024", "default", "test"]
    for tid in test_ids:
        print(f"  - {tid}")
    print("\n提示：可以先尝试 'A' 或 '1'")


if __name__ == "__main__":
    main()
