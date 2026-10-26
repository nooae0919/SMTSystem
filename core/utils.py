import os
import tempfile
import pandas as pd
from nicegui import ui

def export_to_csv(df: pd.DataFrame, filename: str):
    """
    将 DataFrame 导出为 CSV，存入系统临时文件夹并触发下载，不污染项目根目录
    """
    if not filename.endswith('.csv'):
        filename += '.csv'
        
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, filename)
    
    try:
        df.to_csv(file_path, index=False, encoding='utf-8-sig')
        ui.download(file_path)
        ui.notify(f'{filename} 导出成功', type='positive')
    except Exception as e:
        ui.notify(f'导出失败: {e}', type='negative')
