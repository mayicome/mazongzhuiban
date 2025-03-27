import re
from bs4 import BeautifulSoup
import json

def parse_main_fund(html):
    """解析主力资金数据（适配东方财富2024新版页面）"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # 方案一：从表格数据中解析
    table = soup.find('table', {'class': 'quote-table'})
    if table:
        for row in table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 2 and '主力净流入' in cells[0].text:
                value_text = cells[1].text.strip()
                if '亿' in value_text:
                    return float(value_text.replace('亿', ''))
                elif '万' in value_text:
                    return round(float(value_text.replace('万', '')) / 10000, 4)
    
    # 方案二：从JavaScript数据中解析
    script_data = soup.find('script', string=re.compile(r'var stockInfo'))
    if script_data:
        match = re.search(r'"主力净流入":\s*([+-]?\d+\.?\d*)', script_data.string)
        if match:
            return float(match.group(1))
    
    # 方案三：从隐藏的div数据中解析
    data_div = soup.find('div', {'id': 'fundFlowData'})
    if data_div and 'data-value' in data_div.attrs:
        try:
            json_data = json.loads(data_div['data-value'])
            return json_data.get('主力净流入')
        except:
            pass
    
    return None

# 使用示例
with open('response.txt', 'r', encoding='utf-8') as f:
    html_content = f.read()

fund_value = parse_main_fund(html_content)
print(f"主力资金净流入：{fund_value}亿元" if fund_value else "未找到主力资金数据") 