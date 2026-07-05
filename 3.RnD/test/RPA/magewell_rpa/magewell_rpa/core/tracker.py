import cv2
import numpy as np

class TrackingEngine:
    def __init__(self):
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=25, detectShadows=True)
        
    def match_templates(self, frame, templates, threshold):
        """
        다중 템플릿 매칭 수행
        """
        results = []
        if not templates:
            return results
            
        for template in templates:
            t_h, t_w = template['h'], template['w']
            f_h, f_w = frame.shape[:2]
            
            # 템플릿이 프레임보다 크면 스킵
            if t_h > f_h or t_w > f_w: continue

            res = cv2.matchTemplate(frame, template['image'], cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            
            if max_val >= threshold:
                top_left = max_loc
                w, h = template['w'], template['h']
                x, y = top_left
                color = template.get('color', (0, 0, 255))
                
                results.append(((x, y, w, h), template['name'], max_val, color))
                
        return results

    def detect_motion(self, frame, roi_rect, min_area=500):
        """
        ROI 영역 내 모션 감지
        """
        if not roi_rect:
            return False, []
            
        x, y, w, h = roi_rect
        img_h, img_w = frame.shape[:2]
        
        # ROI 유효성 검사
        x = max(0, x); y = max(0, y)
        w = min(w, img_w - x); h = min(h, img_h - y)
        
        if w <= 0 or h <= 0:
            return False, []

        roi_frame = frame[y:y+h, x:x+w]
        fg_mask = self.bg_subtractor.apply(roi_frame)
        _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        motion_rects = []
        motion_detected = False
        
        for contour in contours:
            if cv2.contourArea(contour) > min_area:
                motion_detected = True
                cx, cy, cw, ch = cv2.boundingRect(contour)
                motion_rects.append((x+cx, y+cy, cw, ch)) # 전체 프레임 기준 좌표로 변환
                
        return motion_detected, motion_rects
