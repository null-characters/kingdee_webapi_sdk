#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取"当前流程"为"已提交"的项目，输出产品规格型号、子物料编码、程序说明到 Markdown 文档
"""

import pandas as pd
import os
from datetime import datetime

# 文件路径
EXCEL_FILE = '/Users/fengbing/svn/trunk/software/Code/code_update/产品程序清单.xls'
OUTPUT_MD = '/Users/fengbing/svn/trunk/software/Code/code_update/已提交项目清单.md'

def main():
    print(f"{'='*60}")
    print(f"开始处理: {EXCEL_FILE}")
    print(f"{'='*60}\n")
    
    # 1. 读取 Excel 文件，跳过第一行标题，使用第二行作为列名
    print("步骤1: 读取 Excel 文件...")
    df = pd.read_excel(EXCEL_FILE, sheet_name=0, header=1)
    
    print(f"   - 读取到 {len(df)} 行数据")
    print(f"   - 列名: {df.columns.tolist()}\n")
    
    # 2. 验证必要的列是否存在
    required_columns = ['产品规格型号', '子物料编码', '程序说明', '当前流程']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        print(f"错误: 缺少必要的列: {missing_columns}")
        return False
    
    print("步骤2: 验证列名...")
    print(f"   - 所有必要列都存在 ✓\n")
    
    # 3. 筛选"当前流程"为"已提交"的行
    print("步骤3: 筛选'已提交'项目...")
    
    # 清理数据：去除前后空格，处理 NaN
    df['当前流程'] = df['当前流程'].astype(str).str.strip()
    
    # 筛选已提交的项目
    submitted_df = df[df['当前流程'] == '已提交'].copy()
    
    print(f"   - 找到 {len(submitted_df)} 个'已提交'项目\n")
    
    if len(submitted_df) == 0:
        print("警告: 没有找到'已提交'的项目")
        return False
    
    # 4. 提取需要的列
    print("步骤4: 提取目标列...")
    result_df = submitted_df[['产品规格型号', '子物料编码', '程序说明']].copy()
    
    # 清理数据：去除前后空格
    for col in result_df.columns:
        result_df[col] = result_df[col].astype(str).str.strip()
        # 将 'nan' 字符串替换为空字符串
        result_df[col] = result_df[col].replace('nan', '')
    
    print(f"   - 提取完成\n")
    
    # 5. 生成 Markdown 文档
    print("步骤5: 生成 Markdown 文档...")
    
    md_content = f"""# 已提交项目清单

> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
> 数据来源: 产品程序清单.xls  
> 筛选条件: 当前流程 = "已提交"  
> 总计: {len(result_df)} 项

---

| 序号 | 产品规格型号 | 子物料编码 | 程序说明 |
|:---:|:---|:---|:---|
"""
    
    for idx, (_, row) in enumerate(result_df.iterrows(), 1):
        product_spec = row['产品规格型号'] if row['产品规格型号'] else '-'
        material_code = row['子物料编码'] if row['子物料编码'] else '-'
        program_desc = row['程序说明'] if row['程序说明'] else '-'
        
        # 转义 Markdown 特殊字符
        product_spec = product_spec.replace('|', '\\|')
        material_code = material_code.replace('|', '\\|')
        program_desc = program_desc.replace('|', '\\|')
        
        md_content += f"| {idx} | {product_spec} | {material_code} | {program_desc} |\n"
    
    md_content += "\n---\n\n*此文档由脚本自动生成*\n"
    
    # 写入文件
    with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print(f"   - 已生成: {OUTPUT_MD}\n")
    
    # 6. 校验输出
    print(f"{'='*60}")
    print("步骤6: 校验输出...")
    print(f"{'='*60}\n")
    
    # 读取生成的 Markdown 文件进行校验
    with open(OUTPUT_MD, 'r', encoding='utf-8') as f:
        md_content_verify = f.read()
    
    # 统计表格行数（减去表头和分隔行）
    table_lines = [line for line in md_content_verify.split('\n') if line.startswith('|')]
    header_count = 2  # 表头行和分隔行
    data_rows = len(table_lines) - header_count
    
    print(f"校验结果:")
    print(f"   - 原始筛选项目数: {len(submitted_df)}")
    print(f"   - Markdown 表格数据行数: {data_rows}")
    
    if data_rows == len(submitted_df):
        print(f"   - ✓ 数量一致，校验通过！\n")
    else:
        print(f"   - ✗ 数量不一致，请检查！\n")
        return False
    
    # 7. 显示提取的数据预览
    print(f"{'='*60}")
    print("提取数据预览:")
    print(f"{'='*60}\n")
    
    for idx, (_, row) in enumerate(result_df.iterrows(), 1):
        print(f"[{idx}]")
        print(f"    产品规格型号: {row['产品规格型号'] or '-'}")
        print(f"    子物料编码: {row['子物料编码'] or '-'}")
        print(f"    程序说明: {row['程序说明'] or '-'}")
        print()
    
    print(f"{'='*60}")
    print(f"处理完成！输出文件: {OUTPUT_MD}")
    print(f"{'='*60}")
    
    return True

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)