import os
import zipfile

TARGET_DIR = "./example_data"

def trim_file_physically(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    
    # 1. 针对文本类文件（CSV, TXT），直接硬性提取前 500 行文本
    if ext in ['.csv', '.txt']:
        try:
            # 使用 errors='ignore' 彻底避免编码报错
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [f.readline() for _ in range(500)]
            
            # 过滤掉读取出来的空行（如果文件本身没满500行）
            lines = [line for line in lines if line]
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            print(f"  [成功] 文本文件已物理裁剪至前 500 行")
        except Exception as e:
            print(f"  [失败] 文本文件裁剪异常: {e}")

    # 2. 针对 Excel 文件（XLSX），由于它是压缩包，无法直接切行
    # 最快最稳的方案：直接原地格式化，仅保留一个包含表头的极小空壳文件
    elif ext == '.xlsx':
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=False)
            for sheet in wb.worksheets:
                # 如果表格行数超过 500 行，直接把 501 行往后的全部删除
                if sheet.max_row > 500:
                    sheet.delete_rows(501, sheet.max_row - 500)
            wb.save(file_path)
            wb.close()
            print(f"  [成功] Excel 文件已截断至前 500 行")
        except Exception:
            # 如果本地没有 openpyxl 或者报错，采用备用暴力方案：直接清空，使其变成 0 字节文件
            # 这样既保留了文件名和路径，又彻底把体积降为 0
            with open(file_path, 'w') as f:
                f.truncate(0)
            print(f"  [警告] Excel 解析失败，已直接原地置空（0 KB）以通过 GitHub 限制")

def main():
    print("🚀 开始全格式文件物理瘦身...")
    for root, dirs, files in os.walk(TARGET_DIR):
        for file in files:
            file_path = os.path.join(root, file)
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            
            # 只要文件大于 10MB，不管三七二十一，直接裁剪
            if size_mb > 10:
                print(f"检测到超大文件: {file_path} ({size_mb:.2f} MB)")
                trim_file_physically(file_path)
                print(f"瘦身完成，当前大小: {os.path.getsize(file_path)/(1024*1024):.4f} MB")

if __name__ == "__main__":
    main()