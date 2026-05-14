# -*- coding: utf-8 -*-
"""直接测试金蝶API，绕过SDK"""
import requests
import json

server_url = "http://192.168.1.100/K3Cloud"
login_url = f"{server_url}/Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc"

# 测试数据 - ValidateUser 接口参数格式
payload = {
    "acctID": "your_acct_id",
    "username": "your_username",
    "password": "your_password",
    "lcid": 2052
}

print("测试1: JSON格式直接发送（保持Unicode）")
json_str = json.dumps(payload, ensure_ascii=False)
print(f"JSON字符串: {repr(json_str)}")
print(f"JSON字节: {json_str.encode('utf-8')}")
headers = {'Content-Type': 'application/json; charset=UTF-8'}
resp = requests.post(login_url, data=json_str.encode('utf-8'), headers=headers)
print(f"\n状态: {resp.status_code}")
print(f"Headers: {dict(resp.headers)}")
print(f"Content-Type: {resp.headers.get('Content-Type')}")
print(f"响应内容长度: {len(resp.content)}")
print(f"响应字节: {resp.content}")

print("\n" + "="*60)
print("\n测试2: 使用session保持cookie")
session = requests.Session()
resp = session.post(login_url, data=json_str.encode('utf-8'), headers=headers)
print(f"状态: {resp.status_code}")
print(f"响应: {resp.text}")
print(f"Cookies: {dict(session.cookies)}")

print("\n" + "="*60)
print("\n测试2: 使用session保持cookie")
session = requests.Session()
resp = session.post(login_url, data=json_str.encode('utf-8'), headers=headers)
print(f"状态: {resp.status_code}")
print(f"响应: {resp.text}")
print(f"响应字节: {resp.content}")
print(f"Cookies: {dict(session.cookies)}")

if resp.status_code == 200:
    try:
        result = resp.json()
        print(f"JSON解析成功: {result}")
    except Exception as e:
        print(f"JSON解析失败: {e}")
        print(f"原始内容: {resp.text!r}")
        result = {}
    if result.get("LoginResultType") == 1 or result.get("IsSuccessByAPI"):
        print("\n登录成功！测试View接口...")
        view_url = f"{server_url}/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.View.common.kdsvc"
        view_data = ["BD_MATERIAL", json.dumps({"Number": "MAT001"}, ensure_ascii=False)]
        view_resp = session.post(view_url, data=json.dumps(view_data, ensure_ascii=False).encode('utf-8'), headers=headers)
        print(f"View状态: {view_resp.status_code}")
        print(f"View响应: {view_resp.text[:500]}")
