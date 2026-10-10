# -*- coding: utf-8 -*-
"""GHOST — GUI-based Hands-free Operation & Surveillance Technology.

비침투형(설비 PC 무설치) GUI 자동화 엔진: 캡처 영상으로 화면을 인식하고 HID 신호로 조작한다.
"""
from __future__ import annotations

from typing import Callable, Optional

from . import config
from .blackbox import Blackbox, NullBlackbox
from .device import Device
from .registry import Registry

__version__ = "0.1.0"


def build_device(cfg: dict, sim: bool = False, world=None,
                 log: Optional[Callable[[str], None]] = None) -> Device:
    if sim:
        from .sim import DemoEquipmentApp, SimHid, SimVideo, SimWorld
        if world is None:
            s = cfg["simulator"]
            world = SimWorld(DemoEquipmentApp(cfg["hardware"]["width"], cfg["hardware"]["height"],
                                              run_duration=s["run_duration"]),
                             offset=tuple(s["offset"]), gain=tuple(s["gain"]), accel=s["accel"],
                             noise=s["noise"])
        return Device(SimVideo(world), SimHid(world), cfg, log=log)
    from .hal.capture import CaptureVideo
    from .hal.relayboard import RelayBoard
    hw = cfg["hardware"]
    video = CaptureVideo(hw["camera"], hw["width"], hw["height"], hw["backend"])
    hid = RelayBoard(hw["port"], hw["baudrate"], log=log)
    return Device(video, hid, cfg, log=log)


def build_runner(cfg: dict, device: Device, log: Optional[Callable[[str], None]] = None):
    from .scenario import Runner
    reg = Registry(config.path(cfg, "objects"))
    bb = Blackbox(config.path(cfg, "runs")) if cfg["blackbox"]["enabled"] else NullBlackbox()
    return Runner(device, reg, cfg, blackbox=bb, log=log)
