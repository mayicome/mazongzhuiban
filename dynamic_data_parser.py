import json
from bs4 import BeautifulSoup
import re
import requests
import time

def parse_dynamic_fund_data(html):
    """
    解析动态填充的资金数据
    适用于包含data-field属性的表格结构
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # 查找数据容器（通常包含在script标签中）
    script_data = soup.find('script', string=re.compile(r'var qjdata'))
    if not script_data:
        return None

    # 提取JSON数据
    match = re.search(r'var qjdata\s*=\s*\'(.*?)\';', script_data.string)
    if not match:
        return None

    try:
        # 解析多层嵌套的JSON
        data_str = match.group(1).replace('[[', '[{').replace(']]', '}]')
        data_str = data_str.replace('],[', '},{').replace('",', '","')
        data = json.loads(data_str)
        
        # 在嵌套结构中查找主力资金数据
        for group in data:
            for item in group:
                if item.get('name') == '主力净流入':
                    return {
                        '净额': item.get('f62'),
                        '净占比': item.get('f184')
                    }
        return None
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
        return None

# 使用示例
with open('response.txt', 'r', encoding='utf-8') as f:
    html_content = f.read()

fund_data = parse_dynamic_fund_data(html_content)
if fund_data:
    print(f"主力净流入: {fund_data['净额']} 万元")
    print(f"净占比: {fund_data['净占比']}%")
else:
    print("未找到主力资金数据") 