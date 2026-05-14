"""
简化测试 - 直接测试金蝶WebAPI
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

# 2. 测试View接口 - 发送所有cookies
view_url = f"{server_url}/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.View.common.kdsvc"
view_data = ["BD_MATERIAL", json.dumps({"Number": "MAT001"}, ensure_ascii=False)]

# 打印准备发送的请求信息
print(f"\n准备发送View请求...")
print(f"URL: {view_url}")
print(f"Cookies: {dict(session.cookies)}")
print(f"Data: {view_data}")

resp = session.post(view_url, json=view_data)
print(f"\nView 状态: {resp.status_code}")
print(f"响应: {resp.text}")

# 检查请求头
print(f"\n实际请求头: {dict(resp.request.headers)}")
print(f"实际请求体: {resp.request.body}")
