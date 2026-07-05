# -*- coding: utf-8 -*-
"""클릭 가능한 객체(아이콘) 레지스트리. 템플릿 PNG + objects.json 로 영속화."""
import os, json, cv2

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBJ_DIR = os.path.join(BASE, "objects")
INDEX = os.path.join(OBJ_DIR, "objects.json")

class Registry:
    def __init__(self):
        os.makedirs(OBJ_DIR, exist_ok=True)
        self.objs = {}
        if os.path.exists(INDEX):
            with open(INDEX, encoding="utf-8") as f:
                self.objs = json.load(f)

    def save(self):
        with open(INDEX, "w", encoding="utf-8") as f:
            json.dump(self.objs, f, ensure_ascii=False, indent=2)

    def add(self, name, img, meta=None):
        fn = f"{name}.png"
        cv2.imwrite(os.path.join(OBJ_DIR, fn), img)
        h, w = img.shape[:2]
        rec = {"file": fn, "w": int(w), "h": int(h)}
        if meta:
            rec.update(meta)
        self.objs[name] = rec
        self.save()
        return rec

    def template(self, name):
        rec = self.objs.get(name)
        if not rec:
            return None
        p = os.path.join(OBJ_DIR, rec["file"])
        return cv2.imread(p) if os.path.exists(p) else None

    def names(self):
        return list(self.objs.keys())
