import re
import os
import numpy as np
import chardet
import math

class GCodeAnalyzer:
    """
    負責處理 G-code 檔案讀取、解析與數學運算的後端核心。
    v3.3: 支援運算分批處理以優化 UI 響應 (暫停/停止功能)
    """
    
    def __init__(self):
        # Regex: 抓軸名 + 數值 (支援 .5 或 -.123)
        self.pattern = re.compile(r'([XYZABC])([-+]?(?:\d+\.?\d*|\.\d+))', re.IGNORECASE)

    def detect_encoding(self, file_path):
        try:
            with open(file_path, 'rb') as f:
                result = chardet.detect(f.read(1024 * 1024))
            return result['encoding'] or 'utf-8'
        except Exception as e:
            raise RuntimeError(f"無法檢測檔案編碼：{str(e)}")

    def read_file_generator(self, file_path, chunk_size=16384, progress_callback=None):
        file_size = os.path.getsize(file_path)
        encoding = self.detect_encoding(file_path)
        processed_bytes = 0
        
        try:
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    processed_bytes += len(chunk.encode(encoding))
                    if progress_callback:
                        if progress_callback((processed_bytes / file_size) * 100, "正在讀取檔案"):
                            return None
                    yield chunk
        except Exception as e:
            raise RuntimeError(f"讀取檔案失敗：{str(e)}")

    def parse_and_calculate(self, gcode_content, progress_callback=None):
        """
        一次性完成解析與初步計算。
        """
        g01_segments_start = [] 
        g01_segments_end = []   
        skipped_lines = []
        active_axes = set()
        
        total_g00_dist = 0.0
        
        # 移除括號註解
        gcode_content = re.sub(r'\([^)]*\)', '', gcode_content)
        lines = gcode_content.strip().split('\n')
        
        # 當前座標
        current_pos = {'X': 0.0, 'Y': 0.0, 'Z': 0.0, 'A': 0.0, 'B': 0.0, 'C': 0.0}
        
        # 狀態標記 (預設 G00)
        motion_mode = 'G00' 
        
        total_lines = len(lines)
        pattern_findall = self.pattern.findall
        
        for i, line in enumerate(lines):
            line = line.strip()
            line_upper = line.upper()
            
            # 定期回報進度，讓 UI 有機會響應暫停/停止
            if i % 2000 == 0 and progress_callback:
                if progress_callback((i / total_lines) * 100, "正在解析與計算"):
                    return None
            
            if not line:
                skipped_lines.append(f"Line {i+1}: (空行)")
                continue

            # 1. 更新模態 (Motion Mode)
            if 'G00' in line_upper:
                motion_mode = 'G00'
            elif 'G01' in line_upper:
                motion_mode = 'G01'
            elif 'G02' in line_upper:
                motion_mode = 'G02'
            elif 'G03' in line_upper:
                motion_mode = 'G03'
            
            # 2. 提取座標
            coords = pattern_findall(line)
            has_coords = len(coords) > 0

            # 如果沒有座標，進行純指令分類記錄
            if not has_coords:
                if 'M' in line_upper:
                    skipped_lines.append(f"Line {i+1}: {line} [輔助功能]")
                elif any(c in line_upper for c in ['F', 'S', 'T']):
                    skipped_lines.append(f"Line {i+1}: {line} [參數設定]")
                elif line_upper.startswith('G'):
                    skipped_lines.append(f"Line {i+1}: {line} [準備機能]")
                elif line_upper.startswith(('%', 'O')):
                    skipped_lines.append(f"Line {i+1}: {line} [程式頭/註解]")
                else:
                    skipped_lines.append(f"Line {i+1}: {line} [無座標資訊]")
                continue

            # 3. 計算潛在的移動
            next_pos = current_pos.copy()
            for axis, val_str in coords:
                axis = axis.upper()
                try:
                    val = float(val_str)
                    next_pos[axis] = val
                    active_axes.add(axis)
                except ValueError:
                    pass

            # 計算這一步的物理距離 (包含所有軸)
            p_curr = [current_pos[ax] for ax in 'XYZABC']
            p_next = [next_pos[ax] for ax in 'XYZABC']
            dist = math.sqrt(sum((n - c) ** 2 for n, c in zip(p_next, p_curr)))
            
            # 4. 根據當前模式決定如何處理
            if motion_mode == 'G00':
                total_g00_dist += dist
                current_pos = next_pos
                skipped_lines.append(f"Line {i+1}: {line} [快速定位 G00]")
            
            elif motion_mode == 'G01':
                if dist > 0.000001: 
                    g01_segments_start.append(p_curr)
                    g01_segments_end.append(p_next)
                    current_pos = next_pos
                else:
                    skipped_lines.append(f"Line {i+1}: {line} [G01 原地停留 (dist=0)]")
                    current_pos = next_pos 

            elif motion_mode in ['G02', 'G03']:
                current_pos = next_pos
                skipped_lines.append(f"Line {i+1}: {line} [圓弧指令 (已更新座標)]")

            else:
                current_pos = next_pos
                skipped_lines.append(f"Line {i+1}: {line} [座標設定]")

        # 整理偵測到的軸
        final_axes = sorted(list(active_axes.union({'X', 'Y', 'Z'})))
        
        return {
            "starts": g01_segments_start,
            "ends": g01_segments_end,
            "skipped": skipped_lines,
            "axes": final_axes,
            "g00_dist": total_g00_dist
        }

    def calculate_g01_metrics(self, data_dict, progress_callback=None):
        """
        使用 NumPy 分批計算 G01 相關數據，解決介面凍結問題。
        """
        starts = data_dict["starts"]
        ends = data_dict["ends"]
        active_axes_list = data_dict["axes"]
        
        if not starts:
            return [], 0.0

        # 轉換為 NumPy 陣列
        np_starts = np.array(starts, dtype=np.float64)
        np_ends = np.array(ends, dtype=np.float64)
        
        # 決定計算軸向索引
        axis_map = {'X':0, 'Y':1, 'Z':2, 'A':3, 'B':4, 'C':5}
        indices = [axis_map[ax] for ax in active_axes_list if ax in axis_map]
        
        # 篩選軸向
        p_s = np_starts[:, indices]
        p_e = np_ends[:, indices]
        
        # 分批計算 (Chunk Processing)
        total_points = p_s.shape[0]
        chunk_size = 10000 # 每次計算 10000 點
        all_distances = []
        total_g01_dist = 0.0
        
        for i in range(0, total_points, chunk_size):
            # 檢查是否需要暫停/停止
            if progress_callback:
                pct = (i / total_points) * 100
                if progress_callback(pct, f"正在計算距離 ({i}/{total_points})"):
                    return None, None
            
            # 取得目前的批次
            chunk_s = p_s[i : i + chunk_size]
            chunk_e = p_e[i : i + chunk_size]
            
            diffs = chunk_e - chunk_s
            dists = np.linalg.norm(diffs, axis=1)
            
            all_distances.extend(dists.tolist())
            total_g01_dist += np.sum(dists)
            
        return all_distances, total_g01_dist

    def calculate_histogram_data(self, distances, bins):
        hist, bin_edges = np.histogram(distances, bins=bins)
        return hist, bin_edges

    def calculate_f_values(self, distances, t_value):
        if not distances: return None, None
        dist_array = np.array(distances)
        max_dist = min(np.max(dist_array), 1.0)
        if max_dist < 0.001: max_dist = 0.001
        
        x_values = np.arange(0.001, max_dist + 0.001, 0.001)
        f_values = (x_values / t_value) * 60000
        return x_values, f_values