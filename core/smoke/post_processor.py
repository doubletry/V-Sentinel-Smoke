"""
烟雾火焰检测后处理模块。

通过时序跟踪、置信度滤波、区域分析等多种策略，
减少实时检测中的误报和漏报。
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Sequence

import cv2
import numpy as np


class DetectionClass(Enum):
    """检测类别。"""
    SMOKE = 0
    FIRE = 1


@dataclass(frozen=True)
class Detection:
    """单个检测框。"""
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    cls: DetectionClass
    frame_id: int = 0
    timestamp: float = 0.0

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def aspect_ratio(self) -> float:
        if self.height == 0:
            return float("inf")
        return self.width / self.height


@dataclass
class TrackedObject:
    """被跟踪的目标，记录连续出现的检测。"""
    detections: list[Detection] = field(default_factory=list)
    smoke_feature_history: list[SmokeCandidateFeatures] = field(default_factory=list)
    first_seen: float = 0.0
    last_seen: float = 0.0
    hit_count: int = 0
    miss_count: int = 0
    confirmed: bool = False

    @property
    def duration(self) -> float:
        return self.last_seen - self.first_seen

    @property
    def avg_confidence(self) -> float:
        if not self.detections:
            return 0.0
        return sum(d.confidence for d in self.detections) / len(self.detections)

    @property
    def last_detection(self) -> Detection | None:
        return self.detections[-1] if self.detections else None


@dataclass(frozen=True)
class SmokeCandidateFeatures:
    """单个烟雾候选框的图像证据。

    smoke_likelihood 不是模型置信度，而是基于 ROI 软边界、过曝、
    相对边缘、运动能量等信息得到的后处理分数。边缘只作为弱证据，
    避免把带背景纹理/背景边缘的真实烟雾直接误杀。
    """
    smoke_likelihood: float
    mean_saturation: float
    mean_value: float
    white_ratio: float
    overexposed_ratio: float
    roi_edge_density: float
    ring_edge_density: float
    boundary_edge_density: float
    laplacian_variance: float
    motion_energy: float
    rejection_reasons: tuple[str, ...] = ()


def compute_iou(det_a: Detection, det_b: Detection) -> float:
    """计算两个检测框的 IoU。"""
    inter_x1 = max(det_a.x1, det_b.x1)
    inter_y1 = max(det_a.y1, det_b.y1)
    inter_x2 = min(det_a.x2, det_b.x2)
    inter_y2 = min(det_a.y2, det_b.y2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = det_a.area
    area_b = det_b.area
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0
    return inter_area / union_area


@dataclass
class PostProcessorConfig:
    """后处理配置参数。

    --- 置信度滤波 ---
    min_confidence_smoke: float
        烟雾检测最低置信度阈值。低于此值直接丢弃。
    min_confidence_fire: float
        火焰检测最低置信度阈值。

    --- 时序确认（抗误报核心） ---
    temporal_confirm_frames: int
        在时间窗口内需出现的最少帧数才确认为真实检测。
    temporal_confirm_window: float
        时间窗口大小（秒）。
    max_miss_frames: int
        允许连续丢失的最多帧数，超过则认为目标消失。

    --- 几何过滤（应对反光/过曝） ---
    min_bbox_area_ratio: float
        检测框占图像面积的最小比例，过小的可能是噪声。
    max_bbox_area_ratio: float
        检测框占图像面积的最大比例，过大的可能是全局过曝。
    smoke_min_aspect_ratio: float
        烟雾检测框的最小宽高比。
    smoke_max_aspect_ratio: float
        烟雾检测框的最大宽高比。

    --- 运动一致性分析（应对运动模糊） ---
    motion_blur_max_speed: float
        检测框中心的最大帧间移动像素，超过此值可能是运动模糊误检。
    motion_blur_min_confidence: float
        高速移动检测框需要的最低置信度。

    --- 烟雾外观分析（应对白色物体/反光/硬边运动） ---
    enable_smoke_appearance_filter: bool
        是否启用基于图像内容的烟雾候选过滤。
    smoke_appearance_min_score: float
        烟雾候选的最低外观分数。分数越高越像软边、非过曝、非刚体的烟雾。
    smoke_appearance_min_history: int
        至少累积多少帧图像证据后才用外观分数过滤，避免单帧误杀。
    smoke_appearance_high_confidence_bypass: float
        高于该 YOLO 置信度时，除强反光/硬边证据外不因外观分数丢弃。

    --- IoU 跟踪 ---
    iou_threshold: float
        同一目标匹配的最低 IoU 阈值。

    --- 图像尺寸（像素） ---
    image_width: int
        输入图像宽度。
    image_height: int
        输入图像高度。

    --- 漏报补偿 ---
    alarm_hold_time: float
        确认报警后的持续保持时间（秒），即使后续帧未检测到也维持报警。
    """
    # 置信度
    min_confidence_smoke: float = 0.35
    min_confidence_fire: float = 0.40

    # 时序确认
    temporal_confirm_frames: int = 3
    temporal_confirm_window: float = 2.0
    max_miss_frames: int = 5

    # 几何过滤
    min_bbox_area_ratio: float = 0.0005
    max_bbox_area_ratio: float = 0.60
    smoke_min_aspect_ratio: float = 0.2
    smoke_max_aspect_ratio: float = 8.0

    # 运动模糊
    motion_blur_max_speed: float = 100.0
    motion_blur_min_confidence: float = 0.65

    # 烟雾外观分析
    enable_smoke_appearance_filter: bool = True
    smoke_appearance_min_score: float = 0.42
    smoke_appearance_min_history: int = 2
    smoke_appearance_high_confidence_bypass: float = 0.82
    smoke_overexposed_ratio_threshold: float = 0.18
    smoke_white_object_ratio_threshold: float = 0.62
    smoke_hard_boundary_density_threshold: float = 0.14
    smoke_hard_laplacian_threshold: float = 520.0
    smoke_fast_motion_energy_threshold: float = 0.16
    smoke_static_confirm_frames: int = 5
    smoke_static_max_center_shift: float = 10.0
    smoke_static_max_area_change_ratio: float = 0.08

    # IoU 跟踪
    iou_threshold: float = 0.3

    # 图像尺寸
    image_width: int = 1920
    image_height: int = 1080

    # 漏报补偿
    alarm_hold_time: float = 3.0


@dataclass
class AlarmState:
    """报警状态。"""
    is_active: bool = False
    activated_at: float = 0.0
    last_trigger_time: float = 0.0
    trigger_class: DetectionClass | None = None
    trigger_confidence: float = 0.0


class SmokeFirePostProcessor:
    """烟雾火焰检测后处理器。

    解决的问题：
    ─────────────────────────────────────────────
    误报场景：
    1. 地面反光/过曝 → 白色区域被识别为烟雾
       对策：几何过滤 + 时序确认
    2. 运动模糊 → 人快速移动时白色衣物被稀释成半透明白色
       对策：运动一致性分析 + 帧间速度检测
    3. 蒸汽/水汽 → 厨房蒸汽、浴室水汽
       对策：时序确认（蒸汽通常短暂且形状快速变化）
    4. 光线变化 → 窗帘透光、灯光闪烁
       对策：时序确认 + 几何约束
    5. 白色/灰色物体 → 白色窗帘、灰色墙面
       对策：时序确认（静态物体每帧都检出但不应报警，
             但真正的烟雾形状会持续变化）
    6. 屏幕/电视画面中的火焰 → 电视播放火灾新闻
       对策：几何约束（检测框形状较规则）+ 位置先验

    漏报场景：
    1. 早期烟雾浓度低 → 模型置信度低
       对策：降低阈值 + 时序累积确认
    2. 遮挡导致间歇性检测 → 人走过遮挡
       对策：报警保持机制（alarm_hold_time）
    3. 烟雾颜色与背景接近 → 灰色烟雾在灰色背景下
       对策：适当降低阈值 + 依赖时序确认
    ─────────────────────────────────────────────
    """

    def __init__(self, config: PostProcessorConfig | None = None) -> None:
        self.config = config or PostProcessorConfig()
        self._tracked_objects: dict[int, TrackedObject] = {}
        self._next_track_id: int = 0
        self._alarm_states: dict[DetectionClass, AlarmState] = {
            DetectionClass.SMOKE: AlarmState(),
            DetectionClass.FIRE: AlarmState(),
        }
        self._frame_count: int = 0
        self._previous_gray_frame: np.ndarray | None = None

    def reset(self) -> None:
        """重置所有状态。"""
        self._tracked_objects.clear()
        self._next_track_id = 0
        self._alarm_states = {
            DetectionClass.SMOKE: AlarmState(),
            DetectionClass.FIRE: AlarmState(),
        }
        self._frame_count = 0
        self._previous_gray_frame = None

    def process_frame(
        self,
        detections: Sequence[Detection],
        timestamp: float | None = None,
        frame: np.ndarray | None = None,
    ) -> PostProcessResult:
        """处理一帧的检测结果。

        Args:
            detections: 当前帧的原始检测结果列表。
            timestamp: 当前帧的时间戳（秒）。如果为 None 则使用 time.monotonic()。
            frame: 当前 BGR 图像帧。提供后会启用烟雾外观分析；不提供则沿用纯检测框后处理。

        Returns:
            后处理结果，包含过滤后的检测和报警状态。
        """
        if timestamp is None:
            timestamp = time.monotonic()

        self._frame_count += 1
        cfg = self.config

        if frame is not None:
            cfg.image_height, cfg.image_width = frame.shape[:2]

        # 第1步：置信度过滤
        filtered = self._filter_by_confidence(detections)

        # 第2步：几何过滤（面积、宽高比）
        filtered = self._filter_by_geometry(filtered)

        # 第3步：关联匹配，更新跟踪器
        self._update_tracks(filtered, timestamp)

        # 第4步：运动模糊过滤
        self._filter_motion_blur()

        # 第5步：烟雾外观分析（软边界、反光、白物体、硬边运动）
        self._update_smoke_appearance(frame)

        # 第6步：时序确认
        confirmed = self._get_confirmed_detections(timestamp)

        if frame is not None:
            self._previous_gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # 第7步：更新报警状态
        alarms = self._update_alarms(confirmed, timestamp)

        return PostProcessResult(
            filtered_detections=confirmed,
            smoke_alarm=alarms[DetectionClass.SMOKE],
            fire_alarm=alarms[DetectionClass.FIRE],
            active_tracks=len(self._tracked_objects),
            frame_id=self._frame_count,
        )

    def _filter_by_confidence(
        self, detections: Sequence[Detection]
    ) -> list[Detection]:
        """根据置信度阈值过滤检测结果。"""
        cfg = self.config
        result = []
        for det in detections:
            if det.cls == DetectionClass.SMOKE:
                if det.confidence >= cfg.min_confidence_smoke:
                    result.append(det)
            elif det.cls == DetectionClass.FIRE:
                if det.confidence >= cfg.min_confidence_fire:
                    result.append(det)
        return result

    def _filter_by_geometry(
        self, detections: list[Detection]
    ) -> list[Detection]:
        """根据几何特征过滤，排除过大/过小/异常宽高比的检测。"""
        cfg = self.config
        image_area = cfg.image_width * cfg.image_height
        if image_area <= 0:
            return detections

        result = []
        for det in detections:
            area_ratio = det.area / image_area

            # 过小或过大的检测框
            if area_ratio < cfg.min_bbox_area_ratio:
                continue
            if area_ratio > cfg.max_bbox_area_ratio:
                continue

            # 烟雾的宽高比约束
            if det.cls == DetectionClass.SMOKE:
                ar = det.aspect_ratio
                if ar < cfg.smoke_min_aspect_ratio or ar > cfg.smoke_max_aspect_ratio:
                    continue

            result.append(det)
        return result

    def _update_tracks(
        self, detections: list[Detection], timestamp: float
    ) -> None:
        """使用 IoU 匹配更新目标跟踪。"""
        cfg = self.config
        matched_track_ids: set[int] = set()
        matched_det_indices: set[int] = set()

        # 贪心 IoU 匹配
        matches: list[tuple[float, int, int]] = []
        for track_id, track in self._tracked_objects.items():
            last_det = track.last_detection
            if last_det is None:
                continue
            for det_index, det in enumerate(detections):
                if det.cls != last_det.cls:
                    continue
                iou = compute_iou(last_det, det)
                if iou >= cfg.iou_threshold:
                    matches.append((iou, track_id, det_index))

        # 按 IoU 降序排列，贪心匹配
        matches.sort(key=lambda x: x[0], reverse=True)
        for iou_val, track_id, det_idx in matches:
            if track_id in matched_track_ids or det_idx in matched_det_indices:
                continue
            matched_track_ids.add(track_id)
            matched_det_indices.add(det_idx)

            track = self._tracked_objects[track_id]
            track.detections.append(detections[det_idx])
            track.last_seen = timestamp
            track.hit_count += 1
            track.miss_count = 0

        # 未匹配的检测 → 新建跟踪
        new_track_ids: set[int] = set()
        for det_index, det in enumerate(detections):
            if det_index not in matched_det_indices:
                track_id = self._next_track_id
                self._tracked_objects[track_id] = TrackedObject(
                    detections=[det],
                    first_seen=timestamp,
                    last_seen=timestamp,
                    hit_count=1,
                    miss_count=0,
                )
                new_track_ids.add(track_id)
                self._next_track_id += 1

        # 未匹配的跟踪 → 增加 miss，超过阈值则删除（排除刚创建的）
        to_remove = []
        for track_id, track in self._tracked_objects.items():
            if track_id not in matched_track_ids and track_id not in new_track_ids:
                track.miss_count += 1
                if track.miss_count > cfg.max_miss_frames:
                    to_remove.append(track_id)
        for track_id in to_remove:
            del self._tracked_objects[track_id]

    def _filter_motion_blur(self) -> None:
        """过滤可能由运动模糊导致的误检。

        如果跟踪目标的帧间中心点移动速度过快，且置信度不够高，
        有很大概率是人/物体快速移动带来的运动模糊。
        """
        cfg = self.config
        to_remove = []
        for track_id, track in self._tracked_objects.items():
            if len(track.detections) < 2:
                continue

            last = track.detections[-1]
            prev = track.detections[-2]

            dx = abs(last.center_x - prev.center_x)
            dy = abs(last.center_y - prev.center_y)
            speed = (dx ** 2 + dy ** 2) ** 0.5

            if speed > cfg.motion_blur_max_speed:
                if last.confidence < cfg.motion_blur_min_confidence:
                    # 高速移动 + 低置信度 → 很可能是运动模糊
                    to_remove.append(track_id)

        for track_id in to_remove:
            del self._tracked_objects[track_id]

    def _update_smoke_appearance(self, frame: np.ndarray | None) -> None:
        """更新当前帧烟雾候选的图像外观证据。"""
        if frame is None or not self.config.enable_smoke_appearance_filter:
            return

        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        for track in self._tracked_objects.values():
            if track.miss_count > 0:
                continue
            detection = track.last_detection
            if detection is None or detection.cls != DetectionClass.SMOKE:
                continue

            features = self._analyze_smoke_candidate(
                detection=detection,
                frame=frame,
                gray_frame=gray_frame,
                hsv_frame=hsv_frame,
            )
            if features is not None:
                track.smoke_feature_history.append(features)

    def _analyze_smoke_candidate(
        self,
        detection: Detection,
        frame: np.ndarray,
        gray_frame: np.ndarray,
        hsv_frame: np.ndarray,
    ) -> SmokeCandidateFeatures | None:
        """提取烟雾候选区域的软边、反光、纹理和运动证据。"""
        bbox = self._clip_bbox(detection, frame.shape)
        if bbox is None:
            return None

        left, top, right, bottom = bbox
        gray_roi = gray_frame[top:bottom, left:right]
        hsv_roi = hsv_frame[top:bottom, left:right]
        if gray_roi.size == 0 or hsv_roi.size == 0:
            return None

        saturation_channel = hsv_roi[:, :, 1]
        value_channel = hsv_roi[:, :, 2]
        mean_saturation = float(np.mean(saturation_channel))
        mean_value = float(np.mean(value_channel))
        white_ratio = float(np.mean((saturation_channel < 45) & (value_channel > 165)))
        overexposed_ratio = float(np.mean(value_channel > 242))

        roi_edges = self._canny_edges(gray_roi)
        roi_edge_density = float(np.mean(roi_edges > 0))
        boundary_edge_density = self._boundary_edge_density(roi_edges)
        ring_edge_density = self._ring_edge_density(gray_frame, bbox)
        laplacian_variance = float(cv2.Laplacian(gray_roi, cv2.CV_64F).var())
        motion_energy = self._motion_energy(gray_roi, bbox)

        score = self._score_smoke_candidate(
            mean_saturation=mean_saturation,
            mean_value=mean_value,
            overexposed_ratio=overexposed_ratio,
            roi_edge_density=roi_edge_density,
            ring_edge_density=ring_edge_density,
            boundary_edge_density=boundary_edge_density,
            laplacian_variance=laplacian_variance,
            motion_energy=motion_energy,
        )
        reasons = self._strong_false_positive_reasons(
            white_ratio=white_ratio,
            overexposed_ratio=overexposed_ratio,
            roi_edge_density=roi_edge_density,
            boundary_edge_density=boundary_edge_density,
            laplacian_variance=laplacian_variance,
            motion_energy=motion_energy,
        )

        return SmokeCandidateFeatures(
            smoke_likelihood=score,
            mean_saturation=mean_saturation,
            mean_value=mean_value,
            white_ratio=white_ratio,
            overexposed_ratio=overexposed_ratio,
            roi_edge_density=roi_edge_density,
            ring_edge_density=ring_edge_density,
            boundary_edge_density=boundary_edge_density,
            laplacian_variance=laplacian_variance,
            motion_energy=motion_energy,
            rejection_reasons=tuple(reasons),
        )

    def _clip_bbox(
        self,
        detection: Detection,
        frame_shape: tuple[int, ...],
    ) -> tuple[int, int, int, int] | None:
        """将检测框裁剪到图像边界内。"""
        frame_height, frame_width = frame_shape[:2]
        left = max(0, min(frame_width - 1, int(round(detection.x1))))
        top = max(0, min(frame_height - 1, int(round(detection.y1))))
        right = max(0, min(frame_width, int(round(detection.x2))))
        bottom = max(0, min(frame_height, int(round(detection.y2))))

        if right - left < 4 or bottom - top < 4:
            return None
        return left, top, right, bottom

    def _canny_edges(self, gray_roi: np.ndarray) -> np.ndarray:
        """使用自适应阈值计算 Canny 边缘。"""
        median_value = float(np.median(gray_roi))
        lower = int(max(0, 0.66 * median_value))
        upper = int(min(255, 1.33 * median_value))
        if upper <= lower:
            lower, upper = 40, 120
        return cv2.Canny(gray_roi, lower, upper)

    def _boundary_edge_density(self, edge_roi: np.ndarray) -> float:
        """计算检测框边界附近的边缘密度，硬边白物体通常较高。"""
        roi_height, roi_width = edge_roi.shape[:2]
        band_width = max(2, int(round(min(roi_height, roi_width) * 0.08)))
        boundary_mask = np.zeros(edge_roi.shape, dtype=bool)
        boundary_mask[:band_width, :] = True
        boundary_mask[-band_width:, :] = True
        boundary_mask[:, :band_width] = True
        boundary_mask[:, -band_width:] = True
        return float(np.mean(edge_roi[boundary_mask] > 0))

    def _ring_edge_density(
        self,
        gray_frame: np.ndarray,
        bbox: tuple[int, int, int, int],
    ) -> float:
        """计算候选框周边背景边缘密度，用来抵消背景纹理带来的误判。"""
        left, top, right, bottom = bbox
        frame_height, frame_width = gray_frame.shape[:2]
        bbox_width = right - left
        bbox_height = bottom - top
        pad = max(6, int(round(max(bbox_width, bbox_height) * 0.18)))
        outer_left = max(0, left - pad)
        outer_top = max(0, top - pad)
        outer_right = min(frame_width, right + pad)
        outer_bottom = min(frame_height, bottom + pad)

        outer_gray = gray_frame[outer_top:outer_bottom, outer_left:outer_right]
        if outer_gray.size == 0:
            return 0.0

        outer_edges = self._canny_edges(outer_gray)
        ring_mask = np.ones(outer_edges.shape, dtype=bool)
        inner_left = left - outer_left
        inner_top = top - outer_top
        inner_right = right - outer_left
        inner_bottom = bottom - outer_top
        ring_mask[inner_top:inner_bottom, inner_left:inner_right] = False
        if not np.any(ring_mask):
            return 0.0
        return float(np.mean(outer_edges[ring_mask] > 0))

    def _motion_energy(
        self,
        gray_roi: np.ndarray,
        bbox: tuple[int, int, int, int],
    ) -> float:
        """计算当前 ROI 与上一帧同位置的平均变化幅度。"""
        if self._previous_gray_frame is None:
            return 0.0
        left, top, right, bottom = bbox
        previous_roi = self._previous_gray_frame[top:bottom, left:right]
        if previous_roi.shape != gray_roi.shape or previous_roi.size == 0:
            return 0.0
        difference = cv2.absdiff(gray_roi, previous_roi)
        return float(np.mean(difference) / 255.0)

    def _score_smoke_candidate(
        self,
        *,
        mean_saturation: float,
        mean_value: float,
        overexposed_ratio: float,
        roi_edge_density: float,
        ring_edge_density: float,
        boundary_edge_density: float,
        laplacian_variance: float,
        motion_energy: float,
    ) -> float:
        """融合多类弱证据得到烟雾外观分数。"""
        color_haze_score = 1.0 - self._clamp01((mean_saturation - 35.0) / 105.0)
        brightness_score = 1.0 - self._clamp01(abs(mean_value - 178.0) / 120.0)
        non_specular_score = 1.0 - self._clamp01(overexposed_ratio / 0.24)
        soft_boundary_score = 1.0 - self._clamp01(boundary_edge_density / 0.22)
        texture_softness_score = 1.0 - self._clamp01(laplacian_variance / 780.0)
        relative_edge_excess = max(0.0, roi_edge_density - ring_edge_density * 1.35)
        relative_edge_score = 1.0 - self._clamp01(relative_edge_excess / 0.18)
        motion_score = 1.0 - self._clamp01(max(0.0, motion_energy - 0.10) / 0.35)

        score = (
            0.18 * color_haze_score
            + 0.12 * brightness_score
            + 0.18 * non_specular_score
            + 0.18 * soft_boundary_score
            + 0.12 * texture_softness_score
            + 0.14 * relative_edge_score
            + 0.08 * motion_score
        )
        return self._clamp01(score)

    def _strong_false_positive_reasons(
        self,
        *,
        white_ratio: float,
        overexposed_ratio: float,
        roi_edge_density: float,
        boundary_edge_density: float,
        laplacian_variance: float,
        motion_energy: float,
    ) -> list[str]:
        """识别高置信误报证据，避免单纯靠低分数过滤真烟雾。"""
        cfg = self.config
        reasons: list[str] = []
        hard_boundary = boundary_edge_density >= cfg.smoke_hard_boundary_density_threshold
        hard_texture = laplacian_variance >= cfg.smoke_hard_laplacian_threshold

        if overexposed_ratio >= cfg.smoke_overexposed_ratio_threshold and hard_boundary:
            reasons.append("specular_hard_highlight")
        if white_ratio >= cfg.smoke_white_object_ratio_threshold and hard_texture:
            reasons.append("hard_white_object")
        if overexposed_ratio >= cfg.smoke_overexposed_ratio_threshold and white_ratio >= cfg.smoke_white_object_ratio_threshold and hard_texture:
            reasons.append("overexposed_white_surface")
        if (
            motion_energy >= cfg.smoke_fast_motion_energy_threshold
            and hard_boundary
            and roi_edge_density >= cfg.smoke_hard_boundary_density_threshold
        ):
            reasons.append("moving_hard_edge")
        return reasons

    def _passes_smoke_appearance(self, track: TrackedObject) -> bool:
        """判断跟踪目标是否通过烟雾外观门控。"""
        cfg = self.config
        detection = track.last_detection
        if (
            not cfg.enable_smoke_appearance_filter
            or detection is None
            or detection.cls != DetectionClass.SMOKE
            or not track.smoke_feature_history
        ):
            return True

        history = track.smoke_feature_history[-max(cfg.smoke_appearance_min_history, 1):]
        if len(history) < cfg.smoke_appearance_min_history:
            return True

        average_score = sum(item.smoke_likelihood for item in history) / len(history)
        strong_reason_count = sum(1 for item in history if item.rejection_reasons)
        high_confidence = detection.confidence >= cfg.smoke_appearance_high_confidence_bypass

        if self._looks_like_static_white_object(track):
            return False
        if strong_reason_count >= cfg.smoke_appearance_min_history:
            return False
        if average_score < cfg.smoke_appearance_min_score and not high_confidence:
            return False
        return True

    def _looks_like_static_white_object(self, track: TrackedObject) -> bool:
        """识别持续稳定、硬边、白色的静态物体误报。"""
        cfg = self.config
        if track.hit_count < cfg.smoke_static_confirm_frames:
            return False
        recent_detections = track.detections[-cfg.smoke_static_confirm_frames:]
        recent_features = track.smoke_feature_history[-cfg.smoke_static_confirm_frames:]
        if len(recent_detections) < cfg.smoke_static_confirm_frames or len(recent_features) < cfg.smoke_static_confirm_frames:
            return False

        first_detection = recent_detections[0]
        last_detection = recent_detections[-1]
        center_shift = (
            (last_detection.center_x - first_detection.center_x) ** 2
            + (last_detection.center_y - first_detection.center_y) ** 2
        ) ** 0.5
        first_area = max(first_detection.area, 1.0)
        area_change_ratio = abs(last_detection.area - first_detection.area) / first_area
        average_white_ratio = sum(item.white_ratio for item in recent_features) / len(recent_features)
        average_boundary_density = sum(item.boundary_edge_density for item in recent_features) / len(recent_features)

        return (
            center_shift <= cfg.smoke_static_max_center_shift
            and area_change_ratio <= cfg.smoke_static_max_area_change_ratio
            and average_white_ratio >= cfg.smoke_white_object_ratio_threshold
            and average_boundary_density >= cfg.smoke_hard_boundary_density_threshold
        )

    def _clamp01(self, value: float) -> float:
        """限制数值到 [0, 1]。"""
        return max(0.0, min(1.0, value))

    def _get_confirmed_detections(
        self, timestamp: float
    ) -> list[Detection]:
        """获取经过时序确认的检测结果。

        只返回当前帧有命中（miss_count == 0）且累积命中次数
        达到确认阈值的跟踪目标。
        """
        cfg = self.config
        confirmed: list[Detection] = []

        for track in self._tracked_objects.values():
            # 当前帧未命中的跟踪不报告
            if track.miss_count > 0:
                continue

            window_start = timestamp - cfg.temporal_confirm_window
            recent_hits = sum(
                1 for d in track.detections if d.timestamp >= window_start
            )

            # 时间窗口内的命中次数或总命中次数达标
            if (
                recent_hits >= cfg.temporal_confirm_frames
                or track.hit_count >= cfg.temporal_confirm_frames
            ):
                track.confirmed = True
                if track.last_detection is not None:
                    if not self._passes_smoke_appearance(track):
                        continue
                    confirmed.append(track.last_detection)

        return confirmed

    def _update_alarms(
        self,
        confirmed: list[Detection],
        timestamp: float,
    ) -> dict[DetectionClass, AlarmState]:
        """更新报警状态，包含报警保持机制。"""
        cfg = self.config

        # 按类别分组
        by_class: dict[DetectionClass, list[Detection]] = defaultdict(list)
        for det in confirmed:
            by_class[det.cls].append(det)

        for cls in DetectionClass:
            state = self._alarm_states[cls]
            cls_detections = by_class.get(cls, [])

            if cls_detections:
                best = max(cls_detections, key=lambda d: d.confidence)
                state.last_trigger_time = timestamp
                state.trigger_class = cls
                state.trigger_confidence = best.confidence

                if not state.is_active:
                    state.is_active = True
                    state.activated_at = timestamp
            else:
                # 报警保持：即使当前帧无检测，如果还在保持时间内，维持报警
                if state.is_active:
                    elapsed = timestamp - state.last_trigger_time
                    if elapsed > cfg.alarm_hold_time:
                        state.is_active = False

        return dict(self._alarm_states)

    @property
    def alarm_states(self) -> dict[DetectionClass, AlarmState]:
        """当前报警状态。"""
        return dict(self._alarm_states)

    @property
    def tracked_objects(self) -> dict[int, TrackedObject]:
        """当前跟踪的目标。"""
        return dict(self._tracked_objects)


@dataclass
class PostProcessResult:
    """后处理结果。"""
    filtered_detections: list[Detection]
    smoke_alarm: AlarmState
    fire_alarm: AlarmState
    active_tracks: int
    frame_id: int

    @property
    def has_alarm(self) -> bool:
        return self.smoke_alarm.is_active or self.fire_alarm.is_active
