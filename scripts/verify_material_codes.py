#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校验子物料编码脚本

从已提交项目清单.md 中提取子物料编码，通过金蝶 SDK 查询验证其是否存在。
"""

import sys
import re
import os
from datetime import datetime
from pathlib import Path

# 添加 kingdee_sdk 到路径
KINGDEE_SDK_PATH = '/Users/fengbing/git_prj/kingdee_webapi_sdk'
sys.path.insert(0, KINGDEE_SDK_PATH)

# 添加 kingdee_mcp_agent/config 到路径（获取金蝶配置）
sys.path.insert(0, str(Path(KINGDEE_SDK_PATH) / 'kingdee_mcp_agent' / 'config'))

# 文件路径
MD_FILE = '/Users/fengbing/svn/trunk/software/Code/code_update/已提交项目清单.md'
OUTPUT_FILE = '/Users/fengbing/svn/trunk/software/Code/code_update/子物料编码校验结果.md'

def parse_markdown_table(md_file):
    """解析 Markdown 表格，提取子物料编码"""
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 匹配表格行
    pattern = r'\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(3\.R\.C01\.\d+)\s*\|\s*(.*?)\s*\|'
    matches = re.findall(pattern, content)
    
    results = []
    for match in matches:
        seq = int(match[0])
        product_spec = match[1].strip()
        material_code = match[2].strip()
        program_desc = match[3].strip()
        results.append({
            'seq': seq,
            'product_spec': product_spec,
            'material_code': material_code,
            'program_desc': program_desc
        })
    
    return results

def verify_material_code(client, material_code):
    """通过金蝶 SDK 验证物料编码是否存在"""
    try:
        result = client.execute_bill_query(
            form_id="BD_MATERIAL",
            field_keys="FMaterialID,FNumber,FName,FSpecification",
            filter_string=f"FNumber = '{material_code}'",
            limit=1
        )
        
        if result and len(result) > 0:
            # result 格式: [[FMaterialID, FNumber, FName, FSpecification]]
            row = result[0]
            if isinstance(row, list) and len(row) >= 3:
                return {
                    'exists': True,
                    'material_id': row[0],
                    'number': row[1],
                    'name': row[2],
                    'specification': row[3] if len(row) > 3 else ''
                }
        return {'exists': False}
    except Exception as e:
        return {'exists': False, 'error': str(e)}

def main():
    print(f"{'='*70}")
    print(f"子物料编码校验脚本")
    print(f"{'='*70}\n")
    
    # 1. 解析 Markdown 文件
    print("步骤1: 解析已提交项目清单.md...")
    items = parse_markdown_table(MD_FILE)
    print(f"   - 提取到 {len(items)} 个子物料编码\n")
    
    if len(items) == 0:
        print("错误: 未提取到任何子物料编码")
        return False
    
    # 2. 连接金蝶系统
    print("步骤2: 连接金蝶系统...")
    
    try:
        from kingdee_sdk import KingdeeClient, AuthType
        from settings import KINGDEE_CONFIG
        
        client = KingdeeClient(
            server_url=KINGDEE_CONFIG["server_url"],
            acct_id=KINGDEE_CONFIG["acct_id"],
            username=KINGDEE_CONFIG["username"],
            password=KINGDEE_CONFIG["password"],
            auth_type=AuthType.PASSWORD,
            auto_login=True,
            debug=False
        )
        print(f"   - 连接成功: {KINGDEE_CONFIG['server_url']}\n")
    except Exception as e:
        print(f"   - 连接失败: {e}\n")
        return False
    
    # 3. 校验每个子物料编码
    print(f"{'='*70}")
    print("步骤3: 校验子物料编码...")
    print(f"{'='*70}\n")
    
    verified_results = []
    valid_count = 0
    invalid_count = 0
    error_count = 0
    
    for item in items:
        material_code = item['material_code']
        print(f"   [{item['seq']}] 校验: {material_code}...", end=" ")
        
        result = verify_material_code(client, material_code)
        
        if result['exists']:
            print(f"✓ 存在 (名称: {result['name']})")
            valid_count += 1
            item['verified'] = True
            item['material_name'] = result['name']
            item['material_spec'] = result['specification']
        elif 'error' in result:
            print(f"✗ 查询错误: {result['error']}")
            error_count += 1
            item['verified'] = False
            item['error'] = result['error']
        else:
            print(f"✗ 不存在")
            invalid_count += 1
            item['verified'] = False
        
        verified_results.append(item)
    
    # 4. 生成校验报告
    print(f"\n{'='*70}")
    print("步骤4: 生成校验报告...")
    print(f"{'='*70}\n")
    
    # 生成 Markdown 报告
    md_content = f"""# 子物料编码校验结果

> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
> 数据来源: 已提交项目清单.md  
> 校验系统: 金蝶云星空 ({KINGDEE_CONFIG['server_url']})  
> 校验总数: {len(items)} 项  

---

## 校验统计

| 状态 | 数量 | 占比 |
|:---:|:---:|:---:|
| ✓ 存在 | {valid_count} | {valid_count/len(items)*100:.1f}% |
| ✗ 不存在 | {invalid_count} | {invalid_count/len(items)*100:.1f}% |
| ✗ 查询错误 | {error_count} | {error_count/len(items)*100:.1f}% |

---

## 校验详情

### 有效编码（已确认存在）

| 序号 | 产品规格型号 | 子物料编码 | 物料名称 | 规格型号 | 程序说明 |
|:---:|:---|:---|:---|:---|:---|
"""
    
    # 有效编码
    for item in verified_results:
        if item.get('verified'):
            product_spec = item['product_spec'].replace('|', '\\|')[:50]
            material_name = item.get('material_name', '-').replace('|', '\\|')[:30]
            material_spec = item.get('material_spec', '-').replace('|', '\\|')[:30] if item.get('material_spec') else '-'
            program_desc = item['program_desc'].replace('|', '\\|')
            
            md_content += f"| {item['seq']} | {product_spec} | {item['material_code']} | {material_name} | {material_spec} | {program_desc} |\n"
    
    md_content += """
### 无效编码（不存在或查询失败）

| 序号 | 产品规格型号 | 子物料编码 | 程序说明 | 状态 |
|:---:|:---|:---|:---|:---:|
"""
    
    # 无效编码
    for item in verified_results:
        if not item.get('verified'):
            product_spec = item['product_spec'].replace('|', '\\|')[:50]
            program_desc = item['program_desc'].replace('|', '\\|')
            status = item.get('error', '不存在')
            
            md_content += f"| {item['seq']} | {product_spec} | {item['material_code']} | {program_desc} | ✗ {status} |\n"
    
    md_content += "\n---\n\n*此报告由脚本自动生成*\n"
    
    # 写入文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print(f"   - 已生成: {OUTPUT_FILE}\n")
    
    # 5. 显示校验结果摘要
    print(f"{'='*70}")
    print("校验结果摘要")
    print(f"{'='*70}\n")
    
    print(f"   总计校验: {len(items)} 个子物料编码")
    print(f"   ✓ 存在:   {valid_count} 个 ({valid_count/len(items)*100:.1f}%)")
    print(f"   ✗ 不存在: {invalid_count} 个 ({invalid_count/len(items)*100:.1f}%)")
    print(f"   ✗ 错误:   {error_count} 个 ({error_count/len(items)*100:.1f}%)")
    
    if invalid_count > 0 or error_count > 0:
        print(f"\n   ⚠ 发现 {invalid_count + error_count} 个问题，请检查！")
        print(f"\n   问题编码列表:")
        for item in verified_results:
            if not item.get('verified'):
                print(f"      - [{item['seq']}] {item['material_code']}: {item.get('error', '不存在')}")
    else:
        print(f"\n   ✓ 所有子物料编码均有效！")
    
    print(f"\n{'='*70}")
    print(f"校验完成！输出文件: {OUTPUT_FILE}")
    print(f"{'='*70}")
    
    # 6. 尝试登出
    try:
        client.logout()
    except:
        pass
    
    return True

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)