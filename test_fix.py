"""
修正测试 - 解决双重转义问题
"""
import requests
import json

server_url = "http://192.168.1.100/K3Cloud"

# 1. 登录
login_url = f"{server_url}/Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc"
login_data = {
    "acctID": "your_acct_id",
    "username": "your_username",
    "password": "your_password",
    "lcid": 2052
}

session = requests.Session()
resp = session.post(login_url, json=login_data)
print(f"登录状态: {resp.status_code}")
print(f"Cookies: {dict(session.cookies)}")

# 2. 测试View接口 - 使用原始字符串而不是JSON对象
view_url = f"{server_url}/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.View.common.kdsvc"

# 方式1: 手动构建JSON字符串，完全控制格式
view_body = '["BD_MATERIAL", "{\\"Number\\": \\"MAT001\\"}"]'
print(f"\n方式1 - 手动构建JSON:")
print(f"请求体: {view_body}")
resp = session.post(view_url, data=view_body, headers={'Content-Type': 'application/json'})
print(f"响应: {resp.text[:300]}")

# 方式2: 使用单引号避免转义问题  
view_body2 = '["BD_MATERIAL", "{\\"Number\\": \\"MAT001\\"}"]'
print(f"\n方式2:")
resp = session.post(view_url, data=view_body2.encode('utf-8'), headers={'Content-Type': 'application/json'})
print(f"响应: {resp.text[:300]}")

# 方式3: 直接发送原始字节，不进行JSON序列化
raw_data = b'["BD_MATERIAL", "{\\"Number\\": \\"MAT001\\"}"]'
print(f"\n方式3 - 原始字节:")
print(f"请求体: {raw_data}")
resp = session.post(view_url, data=raw_data, headers={'Content-Type': 'application/json'})
print(f"响应: {resp.text[:300]}")

# 方式4: 尝试把第二个参数作为对象而不是字符串
view_body4 = '["BD_MATERIAL", {"Number": "MAT001"}]'
print(f"\n方式4 - 第二个参数作为对象:")
print(f"请求体: {view_body4}")
resp = session.post(view_url, data=view_body4, headers={'Content-Type': 'application/json'})
print(f"响应: {resp.text[:300]}")
