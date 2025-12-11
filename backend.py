import re
import os
import numpy as np
import chardet
import math

class GCodeAnalyzer:
    """
    負責處理 G-code 檔案讀取、解析與數學運算的後端核心。
    v7.6: 支援 5軸 TCP 向量複合距離計算、動態欄位數據結構。
    """
    
    def __init__(self):
        # Regex: 抓軸名 (XYZABC), 向量/圓心 (IJK), 圓弧參數 (R), 進給 (F)
        self.pattern = re.compile(r'([XYZABCIJKFR])([-+]?(?:\d+\.?\d*|\.\d+))', re.IGNORECASE)

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
        支援 G01 TCP 向量模式 (XYZ+IJK) 與標準歐幾里得模式 (XYZABC) 自動切換。
        """
        g01_segments_start = [] 
        g01_segments_end = []
        
        detailed_logs = [] 
        log_lines = [] 
        
        active_axes = set()
        total_g00_dist = 0.0
        
        # 去除註解
        gcode_content = re.sub(r'\([^)]*\)', '', gcode_content)
        lines = gcode_content.strip().split('\n')
        
        # 狀態變數: 包含 XYZABC 和 IJK
        # 順序對應: X, Y, Z, A, B, C, I, J, K (共9個)
        # IJK 預設為 Z 軸方向 (0,0,1)
        current_pos = {
            'X': 0.0, 'Y': 0.0, 'Z': 0.0, 
            'A': 0.0, 'B': 0.0, 'C': 0.0,
            'I': 0.0, 'J': 0.0, 'K': 1.0
        }
        
        current_feed = 0.0
        motion_mode = 'G00' 
        
        # 計算模式路由 flag
        is_tcp_mode = False
        calc_mode_name = "歐幾里得距離計算法"
        
        total_lines = len(lines)
        pattern_findall = self.pattern.findall
        
        for i, line in enumerate(lines):
            line = line.strip()
            line_upper = line.upper()
            
            if i % 2000 == 0 and progress_callback:
                if progress_callback((i / total_lines) * 100, "正在解析與計算"):
                    return None
            
            if not line: continue

            # 1. 更新模態
            if 'G00' in line_upper: motion_mode = 'G00'
            elif 'G01' in line_upper: motion_mode = 'G01'
            elif 'G02' in line_upper: motion_mode = 'G02'
            elif 'G03' in line_upper: motion_mode = 'G03'
            
            # 2. 提取參數
            coords = pattern_findall(line)
            has_coords = False
            
            next_pos = current_pos.copy()
            radius_r = None 
            
            # 暫存本行是否有 I, J, K (用於判斷是否切換 TCP 模式)
            has_ijk_in_line = False
            
            for axis, val_str in coords:
                axis = axis.upper()
                try:
                    val = float(val_str)
                    if axis == 'F':
                        current_feed = val
                    elif axis == 'R':
                        radius_r = val
                    elif axis in current_pos: # X,Y,Z,A,B,C,I,J,K
                        next_pos[axis] = val
                        active_axes.add(axis)
                        has_coords = True
                        if axis in ['I', 'J', 'K']:
                            has_ijk_in_line = True
                except ValueError:
                    pass

            # [路由邏輯] 自動偵測並切換計算模式
            # 只有在 G01 直線插補且出現 IJK 時，才判定為 TCP 向量控制
            if motion_mode == 'G01' and has_ijk_in_line:
                if not is_tcp_mode:
                    is_tcp_mode = True
                    calc_mode_name = "TCP 向量複合距離法(IJK)"

            # [Log 邏輯] 非座標行
            if not has_coords and not has_ijk_in_line:
                if 'F' in line_upper and current_feed > 0:
                    log_lines.append(f"Line {i+1}: {line} [設定進給]")
                elif 'M' in line_upper:
                    log_lines.append(f"Line {i+1}: {line} [輔助功能 M]")
                elif any(x in line_upper for x in ['S', 'T']):
                    log_lines.append(f"Line {i+1}: {line} [刀具/轉速]")
                elif line_upper.startswith('G'):
                    log_lines.append(f"Line {i+1}: {line} [準備機能 G]")
                elif line_upper.startswith(('%', 'O')):
                    log_lines.append(f"Line {i+1}: {line} [程式頭]")
                else:
                    log_lines.append(f"Line {i+1}: {line} [無座標資訊]")
                continue

            # 3. 計算距離 (核心演算法分流)
            actual_dist = 0.0
            dist_xyz_only = 0.0 # 用於詳細列表顯示 (TCP模式)
            rot_deg_val = 0.0   # 用於詳細列表顯示 (TCP模式)
            
            p_curr_xyz = [current_pos[ax] for ax in 'XYZ']
            p_next_xyz = [next_pos[ax] for ax in 'XYZ']
            
            # --- 模式 A: TCP 向量複合距離法 (G01 + IJK) ---
            if is_tcp_mode and motion_mode == 'G01':
                # A. 計算刀尖 XYZ 歐幾里得距離
                dist_xyz_only = math.sqrt(sum((n - c) ** 2 for n, c in zip(p_next_xyz, p_curr_xyz)))
                
                # B. 計算刀軸向量角度變化
                # 取得 IJK 向量
                v1 = [current_pos[ax] for ax in 'IJK']
                v2 = [next_pos[ax] for ax in 'IJK']
                
                # 正規化向量 (避免 G-code 數值誤差)
                def normalize(v):
                    norm = math.sqrt(sum(x*x for x in v))
                    return [x/norm for x in v] if norm > 0 else v
                
                v1_n = normalize(v1)
                v2_n = normalize(v2)
                
                # 內積求夾角
                dot_prod = sum(a*b for a, b in zip(v1_n, v2_n))
                dot_prod = max(-1.0, min(1.0, dot_prod)) # 限制範圍
                
                theta_rad = math.acos(dot_prod)
                rot_deg_val = math.degrees(theta_rad) # 轉換成角度 (1度 = 1mm 代價)
                
                # C. 複合距離 (不省略任何移動)
                actual_dist = math.sqrt(dist_xyz_only**2 + rot_deg_val**2)
                
            # --- 模式 B: 標準歐幾里得算法 (XYZABC) ---
            else:
                p_curr_all = [current_pos[ax] for ax in 'XYZABC']
                p_next_all = [next_pos[ax] for ax in 'XYZABC']
                actual_dist = math.sqrt(sum((n - c) ** 2 for n, c in zip(p_next_all, p_curr_all)))
                # 在此模式下，dist_xyz_only 和 rot_deg_val 保持 0 或無需顯示

            # G00 處理
            if motion_mode == 'G00':
                dist_g00 = math.sqrt(sum((n - c) ** 2 for n, c in zip(p_next_xyz, p_curr_xyz)))
                actual_dist = dist_g00

            note = ""
            log_suffix = ""
            should_log = True 

            # 4. 根據模式處理 Log 與分類
            full_pos_list_curr = [current_pos[ax] for ax in ['X','Y','Z','A','B','C','I','J','K']]
            full_pos_list_next = [next_pos[ax] for ax in ['X','Y','Z','A','B','C','I','J','K']]

            if motion_mode == 'G00':
                total_g00_dist += actual_dist
                log_suffix = "[快速定位 G00]"
                current_pos = next_pos
            
            elif motion_mode == 'G01':
                if actual_dist > 0.000001:
                    use_feed = current_feed if current_feed > 0 else 1000.0
                    
                    if current_feed <= 0:
                        log_suffix = "[警告: G01 無 F 值]"
                        should_log = True 
                    else:
                        should_log = False # 正常 G01 不記錄
                    
                    # Chart 只需要 XYZ 座標畫路徑
                    g01_segments_start.append(p_curr_xyz)
                    g01_segments_end.append(p_next_xyz)
                    
                    note = f"G01 F{int(use_feed)}"
                    if is_tcp_mode:
                        note += " (TCP)"

                    detailed_logs.append({
                        'line': i+1,
                        'start': full_pos_list_curr, # 存完整 9 軸
                        'end': full_pos_list_next,
                        'dist': actual_dist,
                        'feed': use_feed,
                        'info': note,
                        # 額外欄位供詳細列表使用
                        'dist_xyz': dist_xyz_only,
                        'rot_deg': rot_deg_val,
                        'is_tcp': is_tcp_mode
                    })
                    current_pos = next_pos
                else:
                    log_suffix = "[G01 停滯]"
                    should_log = True
                    current_pos = next_pos

            elif motion_mode in ['G02', 'G03']:
                # G02/G03 圓弧計算維持原樣 (通常 TCP 不用 G02/G03)
                p_c = [current_pos[ax] for ax in 'XYZ']
                p_n = [next_pos[ax] for ax in 'XYZ']
                linear_dist_xyz = math.sqrt(sum((n - c) ** 2 for n, c in zip(p_n, p_c)))

                if linear_dist_xyz > 0.000001:
                    arc_len = linear_dist_xyz
                    
                    if radius_r is not None:
                        try:
                            abs_r = abs(radius_r)
                            if linear_dist_xyz <= 2 * abs_r:
                                theta = 2 * math.asin(linear_dist_xyz / (2 * abs_r))
                                if radius_r < 0: theta = 2 * math.pi - theta 
                                arc_len = abs_r * theta
                                note = f"{motion_mode} R{radius_r} (Arc)"
                                log_suffix = f"[{motion_mode} 圓弧]"
                            else:
                                note = f"{motion_mode} R錯誤"
                                log_suffix = f"[警告: {motion_mode} R錯誤]"
                        except:
                            note = f"{motion_mode} 計算錯誤"
                    elif has_ijk_in_line and not is_tcp_mode:
                         # 這裡的 IJK 是圓心，非向量
                        note = f"{motion_mode} IJK (Arc)"
                        log_suffix = f"[{motion_mode} IJK圓弧]"
                    else:
                        note = f"{motion_mode} (直線近似)"
                        log_suffix = f"[{motion_mode} 無R值近似]"
                    
                    actual_dist = arc_len
                    should_log = True 
                    
                    use_feed = current_feed if current_feed > 0 else 1000.0
                    g01_segments_start.append(p_curr_xyz)
                    g01_segments_end.append(p_next_xyz)
                    
                    detailed_logs.append({
                        'line': i+1,
                        'start': full_pos_list_curr,
                        'end': full_pos_list_next,
                        'dist': actual_dist, 
                        'feed': use_feed,
                        'info': note,
                        'dist_xyz': 0, 'rot_deg': 0, 'is_tcp': False
                    })
                
                current_pos = next_pos
            
            if should_log:
                log_lines.append(f"Line {i+1}: {line} {log_suffix}")

        final_axes = sorted(list(active_axes.union({'X', 'Y', 'Z'})))
        
        return {
            "starts": g01_segments_start,
            "ends": g01_segments_end,
            "skipped": log_lines,
            "axes": final_axes,
            "g00_dist": total_g00_dist,
            "detailed_logs": detailed_logs,
            "calc_mode": calc_mode_name
        }

    def calculate_metrics_and_stats(self, data_dict, bins, fixed_intervals, progress_callback=None):
        detailed_logs = data_dict["detailed_logs"]
        
        if not detailed_logs:
            return [], 0.0, 0.0, [], [], None

        # 1. 拆分數據
        all_distances = []
        all_feeds = []
        
        total_dist = 0.0
        total_time_min = 0.0
        
        total_steps = len(detailed_logs)
        
        for i, log in enumerate(detailed_logs):
            if i % 10000 == 0 and progress_callback:
                 if progress_callback((i / total_steps) * 100, "正在加總數據"):
                    return None, None, None, None, None, None
            
            d = log['dist']
            f = log['feed']
            all_distances.append(d)
            all_feeds.append(f)
            
            total_dist += d
            if f > 0:
                total_time_min += (d / f)
        
        np_dists = np.array(all_distances)
        np_feeds = np.array(all_feeds)

        # 2. 生成 Top N 統計
        bin_indices = np.digitize(np_dists, bins)
        bin_counts = np.bincount(bin_indices, minlength=len(bins)+2)
        bin_feed_sums = np.bincount(bin_indices, weights=np_feeds, minlength=len(bins)+2)

        stats_list = []
        total_count = len(all_distances)
        
        for i, (s, e) in enumerate(fixed_intervals):
            bin_idx = i + 1
            if bin_idx >= len(bin_counts): break
            
            count = bin_counts[bin_idx]
            if count == 0: continue
            
            total_f = bin_feed_sums[bin_idx]
            avg_f = total_f / count if count > 0 else 1000.0
            
            # [單位優化] 轉換邏輯: < 1.0mm 轉 um
            def fmt_val(v):
                if v == float('inf'): return "inf"
                if v < 1.0: return f"{v*1000:.0f}um"
                return f"{v:.3f}mm"

            s_label = fmt_val(s)
            
            if e == float('inf'): 
                label = f"> {s_label}"
            else:
                e_label = fmt_val(e)
                label = f"{s_label} ~ {e_label}"
            
            pct = (count / total_count) * 100
            
            stats_list.append({
                'label': label,
                'count': count,
                'pct': pct,
                'avg_feed': avg_f,
                'min_len': s,
                'max_len': e if e != float('inf') else s * 1.5
            })
            
        stats_list.sort(key=lambda x: x['count'], reverse=True)
        
        top_10 = stats_list[:10]
        top_3 = stats_list[:3] 
        
        # 3. 計算最適合 BPT
        bpt_info = None
        if stats_list:
            top1 = stats_list[0]
            f_avg = top1['avg_feed']
            if f_avg > 0:
                min_bpt = (top1['min_len'] / f_avg) * 60000
                max_bpt = (top1['max_len'] / f_avg) * 60000
                bpt_info = {
                    'range_str': f"{min_bpt:.2f}ms ~ {max_bpt:.2f}ms",
                    'f_avg': f_avg
                }
        
        return all_distances, total_dist, total_time_min, top_10, top_3, bpt_info

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