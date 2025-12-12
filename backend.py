# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
# Project:      CAM Analyzer
# File:         backend.py
# Author:       TFC-CRM
# Created:      2025-12-12
# Copyright:    (c) 2025 TFC-CRM. All rights reserved.
# License:      Proprietary / Confidential
# Description:  Core logic for high-performance G-code parsing using Numpy.
#               Implements sparse matrix parsing and vectorized forward fill.
# ------------------------------------------------------------------------------

import re
import os
import numpy as np
import chardet
import math

class GCodeAnalyzer:
    """
    Handles G-code file reading, parsing, and geometric calculations.
    
    Version: 10.6 (Flagship / Numpy Float64 / English Messages)
    """
    
    def __init__(self):
        # Regex: Capture axes (XYZABCIJK), radius (R), and feed (F)
        self.pattern = re.compile(r'([XYZABCIJKFR])([-+]?(?:\d+\.?\d*|\.\d+))', re.IGNORECASE)

    def detect_encoding(self, file_path: str) -> str:
        """
        Detects the file encoding by reading the first 64KB.
        """
        try:
            with open(file_path, 'rb') as f:
                result = chardet.detect(f.read(65536))
            return result['encoding'] or 'utf-8'
        except Exception as e:
            raise RuntimeError(f"Failed to detect file encoding: {str(e)}")

    def read_file_generator(self, file_path: str, chunk_size=1024*1024, progress_callback=None):
        """
        Generator that reads the file in chunks to manage memory usage.
        """
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
                        # [Modified] English Message
                        if processed_bytes % (5 * 1024 * 1024) == 0: 
                            if progress_callback((processed_bytes / file_size) * 100, "Reading File"):
                                return None
                    yield chunk
        except Exception as e:
            raise RuntimeError(f"Failed to read file: {str(e)}")

    def _numpy_ffill(self, arr: np.ndarray) -> np.ndarray:
        """
        Vectorized Forward Fill using Numpy.
        """
        mask = np.isnan(arr)
        # Use [:, None] to broadcast index array (N, 1) against mask (N, Cols)
        idx = np.where(~mask, np.arange(mask.shape[0])[:, None], 0)
        
        # Propagate the last valid index down
        np.maximum.accumulate(idx, axis=0, out=idx)
        
        # Use advanced indexing to construct the filled array
        return arr[idx, np.arange(arr.shape[1])]

    def _numpy_ffill_1d(self, arr: np.ndarray) -> np.ndarray:
        """1D array Forward Fill."""
        mask = np.isnan(arr)
        idx = np.where(~mask, np.arange(mask.shape[0]), 0)
        np.maximum.accumulate(idx, out=idx)
        return arr[idx]

    def parse_and_calculate(self, gcode_content: str, progress_callback=None) -> dict:
        """
        Executes sparse parsing and vectorized geometric calculations.
        """
        # Remove comments
        gcode_content = re.sub(r'\([^)]*\)', '', gcode_content)
        lines = gcode_content.splitlines() 
        total_lines = len(lines)
        
        estimated_tokens = total_lines * 3
        
        # Pre-allocation (Float64)
        buf_rows = np.zeros(estimated_tokens, dtype=np.int32)
        buf_cols = np.zeros(estimated_tokens, dtype=np.int8)
        buf_vals = np.zeros(estimated_tokens, dtype=np.float64) 
        
        # Line Properties
        line_modes = np.full(total_lines + 1, np.nan, dtype=np.float64) 
        line_feeds = np.full(total_lines + 1, np.nan, dtype=np.float64)
        
        # Initial State
        line_modes[0] = 0.0 
        line_feeds[0] = 0.0
        
        axis_map = {
            'X':0, 'Y':1, 'Z':2, 
            'A':3, 'B':4, 'C':5, 
            'I':6, 'J':7, 'K':8
        }
        
        ptr = 0
        skipped_logs = []
        is_tcp_mode = False
        calc_mode_name = "歐幾里得距離計算法"
        
        pattern_findall = self.pattern.findall
        current_mode_val = 0.0 
        
        # === 1. Sparse Parsing Loop ===
        for i, line in enumerate(lines):
            line_idx = i + 1
            if not line: continue
            
            if i % 20000 == 0 and progress_callback:
                # [Modified] English Message
                if progress_callback((i / total_lines) * 50, "Parsing G-code (Sparse)"):
                    return None

            line_upper = line.upper()
            
            # Modal G-code
            if 'G0' in line_upper: 
                if 'G00' in line_upper: current_mode_val = 0.0
                elif 'G01' in line_upper: current_mode_val = 1.0
                elif 'G02' in line_upper or 'G03' in line_upper: current_mode_val = 1.0 
                line_modes[line_idx] = current_mode_val
            
            coords = pattern_findall(line)
            
            has_move = False
            has_ijk = False
            
            for axis_char, val_str in coords:
                axis = axis_char.upper()
                if axis in axis_map:
                    if ptr >= len(buf_rows): 
                        new_size = len(buf_rows) * 2
                        buf_rows.resize(new_size, refcheck=False)
                        buf_cols.resize(new_size, refcheck=False)
                        buf_vals.resize(new_size, refcheck=False)
                    
                    val = float(val_str)
                    buf_rows[ptr] = line_idx
                    buf_cols[ptr] = axis_map[axis]
                    buf_vals[ptr] = val
                    ptr += 1
                    
                    has_move = True
                    if axis in ['I', 'J', 'K']: has_ijk = True
                    
                elif axis == 'F':
                    line_feeds[line_idx] = float(val_str)

            # Auto-detect TCP
            if current_mode_val == 1.0 and has_ijk and not is_tcp_mode:
                is_tcp_mode = True
                calc_mode_name = "TCP 向量複合距離法(IJK)"
            
            # Log non-movement lines
            if not has_move and not has_ijk:
                log_suffix = ""
                should_log = False
                
                if 'M' in line_upper:
                    log_suffix = "[M Code]"
                    should_log = True
                elif any(x in line_upper for x in ['S', 'T']):
                    log_suffix = "[Tool/Speed]"
                    should_log = True
                elif line_upper.startswith('G'):
                    log_suffix = "[G Code Setup]"
                    should_log = True
                elif line_upper.startswith(('%', 'O')):
                    log_suffix = "[Header]"
                    should_log = True
                
                if should_log:
                    skipped_logs.append(f"Line {line_idx}: {line} {log_suffix}")

        # === 2. Matrix Reconstruction ===
        # [Modified] English Message
        if progress_callback: progress_callback(60, "Building Matrix")
        
        buf_rows = buf_rows[:ptr]
        buf_cols = buf_cols[:ptr]
        buf_vals = buf_vals[:ptr]
        
        matrix = np.full((total_lines + 1, 9), np.nan, dtype=np.float64)
        matrix[0] = [0, 0, 0, 0, 0, 0, 0, 0, 1] 
        
        matrix[buf_rows, buf_cols] = buf_vals
        
        # === 3. Vectorized Fill ===
        matrix_filled = self._numpy_ffill(matrix)
        modes_filled = self._numpy_ffill_1d(line_modes)
        feeds_filled = self._numpy_ffill_1d(line_feeds)
        
        # === 4. Vectorized Calculation ===
        # [Modified] English Message
        if progress_callback: progress_callback(80, "Calculating Vectors")
        
        delta = matrix_filled[1:] - matrix_filled[:-1]
        dist_xyz = np.linalg.norm(delta[:, 0:3], axis=1)
        
        # TCP Angle Calculation
        vec_prev = matrix_filled[:-1, 6:9]
        vec_curr = matrix_filled[1:, 6:9]
        
        norm_prev = np.linalg.norm(vec_prev, axis=1, keepdims=True)
        norm_curr = np.linalg.norm(vec_curr, axis=1, keepdims=True)
        norm_prev[norm_prev == 0] = 1.0
        norm_curr[norm_curr == 0] = 1.0
        
        vec_prev_n = vec_prev / norm_prev
        vec_curr_n = vec_curr / norm_curr
        
        dot = np.einsum('ij,ij->i', vec_prev_n, vec_curr_n)
        dot = np.clip(dot, -1.0, 1.0)
        angles = np.degrees(np.arccos(dot))
        
        final_dists = np.zeros_like(dist_xyz)
        is_g00 = (modes_filled[1:] == 0.0)
        is_g01 = ~is_g00
        
        if is_tcp_mode:
            final_dists[is_g01] = np.sqrt(dist_xyz[is_g01]**2 + angles[is_g01]**2)
            final_dists[is_g00] = dist_xyz[is_g00]
        else:
            dist_abc = np.linalg.norm(delta[:, 3:6], axis=1)
            final_dists = np.sqrt(dist_xyz**2 + dist_abc**2)
            
        # === 5. Statistics ===
        total_g00 = np.sum(final_dists[is_g00])
        total_g01 = np.sum(final_dists[is_g01])
        
        safe_feeds = feeds_filled[1:].copy()
        safe_feeds[safe_feeds <= 0] = 1000.0
        time_m = np.sum(final_dists[is_g01] / safe_feeds[is_g01])
        
        used_cols = np.any(matrix_filled != 0, axis=0)
        final_axes = []
        for char, idx in axis_map.items():
            if used_cols[idx]: final_axes.append(char)
        
        line_numbers = np.arange(total_lines + 1, dtype=np.int32)
        
        return {
            "matrix": matrix_filled,
            "dists": final_dists,
            "dists_xyz": dist_xyz,
            "rots_deg": angles,
            "feeds": feeds_filled,
            "modes": modes_filled,
            "lines": line_numbers,
            "skipped": skipped_logs,
            "axes": sorted(final_axes),
            "g00_dist": total_g00,
            "g01_dist": total_g01,
            "time": time_m,
            "calc_mode": calc_mode_name,
            "is_tcp": is_tcp_mode
        }

    def calculate_metrics_and_stats(self, data_dict, bins, fixed_intervals, progress_callback=None):
        """Calculates histograms, Top N stats, and BPT."""
        dists = data_dict['dists']
        feeds = data_dict['feeds'] 
        
        valid_mask = dists > 0.000001
        valid_dists = dists[valid_mask]
        valid_feeds = feeds[1:][valid_mask]
        
        if len(valid_dists) == 0:
            return [], 0, 0, [], [], None

        bin_indices = np.digitize(valid_dists, bins)
        bin_counts = np.bincount(bin_indices, minlength=len(bins)+2)
        bin_feed_sums = np.bincount(bin_indices, weights=valid_feeds, minlength=len(bins)+2)
        
        stats_list = []
        total_count = len(valid_dists)
        
        for i, (s, e) in enumerate(fixed_intervals):
            bin_idx = i + 1
            if bin_idx >= len(bin_counts): break
            count = bin_counts[bin_idx]
            if count == 0: continue
            
            total_f = bin_feed_sums[bin_idx]
            avg_f = total_f / count if count > 0 else 1000.0
            
            pct = (count / total_count) * 100
            
            def fmt_val(v):
                if v == float('inf'): return "inf"
                if v < 1.0: return f"{v*1000:.0f}um"
                return f"{v:.3f}mm"
            
            label = f"{fmt_val(s)} ~ {fmt_val(e)}" if e != float('inf') else f"> {fmt_val(s)}"
            
            stats_list.append({
                'label': label,
                'count': count,
                'pct': pct,
                'avg_feed': avg_f,
                'min_len': s,
                'max_len': e
            })
            
        stats_list.sort(key=lambda x: x['count'], reverse=True)
        top_10 = stats_list[:10]
        top_3 = stats_list[:3]
        
        bpt_info = None
        if top_10:
            top1 = top_10[0]
            f_avg = top1['avg_feed']
            if f_avg > 0:
                min_bpt = (top1['min_len'] / f_avg) * 60000
                m_len = top1['max_len']
                if m_len == float('inf'): m_len = top1['min_len'] * 1.5
                max_bpt = (m_len / f_avg) * 60000
                bpt_info = {'range_str': f"{min_bpt:.2f}ms ~ {max_bpt:.2f}ms", 'f_avg': f_avg}

        return valid_dists, data_dict['g01_dist'], data_dict['time'], top_10, top_3, bpt_info

    def calculate_histogram_data(self, distances, bins):
        hist, bin_edges = np.histogram(distances, bins=bins)
        return hist, bin_edges