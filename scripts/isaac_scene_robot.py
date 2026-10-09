"""Isaac Sim 6.1 UR10 wrist camera, driven by measured PhysX Jacobian IK.

SimulationApp must already exist before ``setup_robot`` is called. The caller
owns physics/render stepping. No camera or joint-state teleport is used.
"""
from __future__ import annotations

from typing import Any, Callable
import math

import numpy as np


def _array(value: Any) -> np.ndarray:
    return np.asarray(value.numpy() if hasattr(value, "numpy") else value, dtype=float)


def _quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array([aw*bw-ax*bx-ay*by-az*bz,
                     aw*bx+ax*bw+ay*bz-az*by,
                     aw*by-ax*bz+ay*bw+az*bx,
                     aw*bz+ax*by-ay*bx+az*bw])


def _rotation(q: np.ndarray) -> np.ndarray:
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])


def _rotation_error(target: np.ndarray, actual: np.ndarray) -> np.ndarray:
    # 짧은 회전 방향의 world-frame 회전벡터. 180도에서도 0으로 사라지지 않는다.
    delta = _quat_mul(target, actual * np.array([1, -1, -1, -1]))
    delta /= np.linalg.norm(delta)
    if delta[0] < 0:
        delta = -delta
    length = float(np.linalg.norm(delta[1:]))
    if length < 1e-9:
        return 2 * delta[1:]
    return delta[1:] / length * (2 * math.atan2(length, float(delta[0])))


def _look_quaternion(position: np.ndarray, target: np.ndarray) -> np.ndarray:
    from pxr import Gf
    if np.linalg.norm(target-position) < 1e-6:
        raise ValueError("카메라 위치와 바라볼 위치가 같습니다")
    matrix = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*position), Gf.Vec3d(*target),
                                   Gf.Vec3d(0, 0, 1)).GetInverse()
    q = matrix.ExtractRotationQuat()
    return np.array([q.GetReal(), *q.GetImaginary()], dtype=float)


class WristRobotController:
    """Fixed-base UR10 motor targets with closed-loop damped least-squares IK."""

    def __init__(self, world: Any, stage: Any, config: dict[str, Any]) -> None:
        print("ROBOT_IMPORT_BEGIN", flush=True)
        from pxr import Gf, Usd, UsdGeom, UsdPhysics
        from isaacsim.core.experimental.prims import Articulation
        from isaacsim.storage.native import get_assets_root_path

        self.world, self.stage, self.config = world, stage, config
        cfg = config.get("robot", {})
        self.robot_prim_path = cfg.get("prim_path", "/World/UR10")
        print("ROBOT_ASSET_ROOT_BEGIN", flush=True)
        self.asset_path = cfg.get("asset_path") or (
            str(get_assets_root_path()).rstrip("/")
            + "/Isaac/Robots/UniversalRobots/ur10/ur10.usd")
        root = UsdGeom.Xform.Define(stage, self.robot_prim_path)
        print("ROBOT_ASSET_LOAD " + self.asset_path, flush=True)
        if not root.GetPrim().GetReferences().AddReference(self.asset_path):
            raise RuntimeError("UR10 USD 자산 참조를 추가하지 못했습니다: " + self.asset_path)
        base = _array(cfg.get("base_position", [0.0, 0.0, 0.0]))
        UsdGeom.Xformable(root).ClearXformOpOrder()
        root.AddTranslateOp().Set(Gf.Vec3d(*base))

        # ee_link는 fixed-joint 병합으로 PhysX link에서 생략될 수 있어 실제 wrist link를 쓴다.
        matches = [p for p in Usd.PrimRange(root.GetPrim())
                   if p.GetName() == cfg.get("wrist_link_name", "wrist_3_link")]
        if len(matches) != 1 or not matches[0].HasAPI(UsdPhysics.RigidBodyAPI):
            raise RuntimeError("UR10의 물리 wrist_3_link를 유일하게 확인하지 못했습니다")
        self.ee_prim_path = str(matches[0].GetPath())
        print("ROBOT_WRIST_FOUND " + self.ee_prim_path, flush=True)
        self.camera_prim_path = self.ee_prim_path + "/WristCamera"
        # 카메라는 손목 중심축 옆에 둬 손목/토치 자체가 광학축을 막지 않게 한다.
        self.camera_local_translation = _array(cfg.get("camera_mount_translation", [0.14, 0, 0.12]))
        if self.camera_local_translation.shape != (3,) or not np.isfinite(self.camera_local_translation).all():
            raise ValueError("camera_mount_translation은 유한한 xyz 값이어야 합니다")
        camera = UsdGeom.Camera.Define(stage, self.camera_prim_path)
        camera.AddTranslateOp().Set(Gf.Vec3d(*self.camera_local_translation))
        camera.AddOrientOp().Set(Gf.Quatf(1, 0, 0, 0))
        # 하우징/렌즈는 카메라 광학면 뒤(+Z)에만 둬 자신의 영상을 가리지 않는다.
        self.camera_housing_prim_path = self.ee_prim_path + "/CameraHousing"
        housing = UsdGeom.Cube.Define(stage, self.camera_housing_prim_path)
        housing.CreateSizeAttr(1)
        housing.AddTranslateOp().Set(Gf.Vec3d(*(self.camera_local_translation + [0, 0, 0.04])))
        housing.AddScaleOp().Set(Gf.Vec3f(0.055, 0.045, 0.05))
        housing.CreateDisplayColorAttr([Gf.Vec3f(0.018, 0.020, 0.024)])
        lens = UsdGeom.Cylinder.Define(stage, self.ee_prim_path + "/CameraLens")
        lens.CreateAxisAttr("Z")
        lens.CreateRadiusAttr(0.013)
        lens.CreateHeightAttr(0.01)
        lens.AddTranslateOp().Set(Gf.Vec3d(*(self.camera_local_translation + [0, 0, 0.008])))
        lens.CreateDisplayColorAttr([Gf.Vec3f(0.045, 0.065, 0.09)])
        # 광학축 옆의 토치와 브래킷은 시각 모델이며 용접/충돌/제어 능력을 주장하지 않는다.
        self.torch_prim_path = self.ee_prim_path + "/DemoTorch"
        torch = UsdGeom.Cylinder.Define(stage, self.torch_prim_path)
        torch.CreateAxisAttr("Z")
        torch.CreateRadiusAttr(0.016)
        torch.CreateHeightAttr(0.18)
        torch.AddTranslateOp().Set(Gf.Vec3d(-0.08, 0.0, -0.025))
        torch.CreateDisplayColorAttr([Gf.Vec3f(0.12, 0.14, 0.16)])
        nozzle = UsdGeom.Cone.Define(stage, self.torch_prim_path + "/Nozzle")
        nozzle.CreateAxisAttr("Z")
        nozzle.CreateRadiusAttr(0.014)
        nozzle.CreateHeightAttr(0.065)
        nozzle.AddTranslateOp().Set(Gf.Vec3d(0, 0, -0.115))
        nozzle.AddRotateXOp().Set(180)
        nozzle.CreateDisplayColorAttr([Gf.Vec3f(0.55, 0.28, 0.09)])
        bracket = UsdGeom.Cube.Define(stage, self.ee_prim_path + "/CameraBracket")
        bracket.CreateSizeAttr(1)
        bracket.AddTranslateOp().Set(Gf.Vec3d(float(self.camera_local_translation[0])/2, 0, 0.16))
        bracket.AddScaleOp().Set(Gf.Vec3f(abs(float(self.camera_local_translation[0]))+0.05, 0.025, 0.018))
        bracket.CreateDisplayColorAttr([Gf.Vec3f(0.16, 0.18, 0.20)])

        anchor = UsdGeom.Cube.Define(stage, self.ee_prim_path + '/BracketAnchor')
        anchor.CreateSizeAttr(1)
        anchor.AddTranslateOp().Set(Gf.Vec3d(0,0,.075))
        anchor.AddScaleOp().Set(Gf.Vec3f(.025,.025,.15))
        anchor.CreateDisplayColorAttr([Gf.Vec3f(.16,.18,.20)])
        # 지지대는 광학면 뒤에서 하우징으로 이어지며 이미지 앞에 걸치지 않는다.
        support = UsdGeom.Cube.Define(stage, self.ee_prim_path + "/CameraSupport")
        support.CreateSizeAttr(1)
        mount_z = float(self.camera_local_translation[2]) + 0.05
        support.AddTranslateOp().Set(Gf.Vec3d(float(self.camera_local_translation[0]), 0,
                                            (0.16 + mount_z) / 2))
        support.AddScaleOp().Set(Gf.Vec3f(0.018, 0.025, max(abs(0.16 - mount_z), 0.02)))
        support.CreateDisplayColorAttr([Gf.Vec3f(0.16, 0.18, 0.20)])

        self.articulation = Articulation(self.robot_prim_path, reset_xform_op_properties=False)
        print("ROBOT_ARTICULATION_CREATED", flush=True)
        self._initialized = False
        self._view: str | None = None
        self._target_position: np.ndarray | None = None
        self._target_quaternion: np.ndarray | None = None
        self._moves: list[dict[str, Any]] = []
        self._iterations = 0
        self._position_tolerance = float(cfg.get("position_tolerance_m", 0.004))
        self._rotation_tolerance = float(cfg.get("rotation_tolerance_rad", 0.018))
        self._ik_damping = float(cfg.get("ik_damping", 0.025))
        self._max_joint_step = float(cfg.get("max_joint_target_step_rad", 0.12))

    def initialize(self) -> None:
        """Call after world.reset(), when the physics tensor view is available."""
        from isaacsim.core.experimental.prims import RigidPrim
        if not self.articulation.is_physics_tensor_entity_valid():
            raise RuntimeError("world.reset() 후 UR10 PhysX articulation을 초기화해야 합니다")
        names = list(self.articulation.dof_names)
        if len(names) != 6:
            raise RuntimeError(f"UR10의 6개 관절을 기대했습니다: {names}")
        self._dof_names = names
        self._link_paths = list(self.articulation.link_paths[0])
        if self.ee_prim_path not in self._link_paths:
            raise RuntimeError("선택한 wrist link가 실제 PhysX articulation에 없습니다")
        self._ee_index = self._link_paths.index(self.ee_prim_path)
        self._links = RigidPrim(self._link_paths, reset_xform_op_properties=False)
        # 6.1 API는 (lower[N,D], upper[N,D]) tuple을 반환한다.
        lower, upper = self.articulation.get_dof_limits()
        self._limits = np.stack([_array(lower)[0], _array(upper)[0]], axis=-1)
        if self._limits.shape != (len(names), 2) or np.any(self._limits[:, 0] >= self._limits[:, 1]):
            raise RuntimeError("UR10 관절 한계의 shape/순서가 올바르지 않습니다")
        shape = tuple(self.articulation.jacobian_matrix_shape)
        if shape != (len(self._link_paths)-1, 6, len(names)):
            raise RuntimeError(f"고정 base UR10 Jacobian을 기대했습니다: {shape}")
        self._jacobian_index = self._ee_index - 1
        if self._jacobian_index < 0:
            raise RuntimeError("UR10 root link를 end effector로 사용할 수 없습니다")
        cfg = self.config.get("robot", {})
        self.articulation.set_dof_gains(stiffnesses=float(cfg.get("drive_stiffness", 16000)),
                                       dampings=float(cfg.get("drive_damping", 800)))
        self.articulation.set_dof_max_velocities(float(cfg.get("max_joint_velocity_rad_s", 1.4)))
        # 초기 singular 자세는 실제 모터 목표를 보내 벗어난다. 상태를 직접 덮어쓰지 않는다.
        seed_by_name = dict(zip(["shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint",
                                 "wrist_1_joint", "wrist_2_joint", "wrist_3_joint"],
                                [0.0, -1.2, 1.6, -1.8, -1.57, 0.0]))
        if all(n in seed_by_name for n in names):
            seed = np.array([seed_by_name[n] for n in names])
            self.articulation.set_dof_position_targets(seed[None, :])
        else:
            raise RuntimeError(f"UR10 관절 이름과 순서를 확인할 수 없습니다: {names}")
        self._initialized = True
        print("ROBOT_PHYSICS_INITIALIZED " + str(names), flush=True)
        print("ROBOT_LIMITS " + str(self._limits.tolist()), flush=True)

    def set_view(self, view: str) -> dict[str, Any]:
        if not self._initialized:
            raise RuntimeError("initialize()를 먼저 호출해야 합니다")
        item = self.config["views"][view]
        position = _array(item["camera_position"])
        quaternion = _look_quaternion(position, _array(item["look_at"]))
        self._view, self._target_position, self._target_quaternion = view, position, quaternion
        self._target_ee_position = position - _rotation(quaternion) @ self.camera_local_translation
        self._iterations = 0
        return {"view": view, "requested_camera_position": position.tolist(),
                "requested_camera_quaternion_usd_wxyz": quaternion.tolist(),
                "requested_wrist_position": self._target_ee_position.tolist()}

    def _poses(self) -> tuple[np.ndarray, np.ndarray]:
        if not self._links.is_physics_tensor_entity_valid():
            raise RuntimeError("실제 PhysX link pose를 읽을 수 없어 USD 값으로 대체하지 않습니다")
        positions, quaternions = self._links.get_world_poses()
        return _array(positions), _array(quaternions)

    def step(self) -> None:
        """Apply a motor target; the caller performs the following physics step."""
        if self._target_position is None:
            raise RuntimeError("set_view()를 먼저 호출해야 합니다")
        positions, quaternions = self._poses()
        error = np.concatenate([self._target_ee_position - positions[self._ee_index],
                                _rotation_error(self._target_quaternion, quaternions[self._ee_index])])
        jacobian = _array(self.articulation.get_jacobian_matrices())[0, self._jacobian_index]
        # m/rad 차이를 완화하되 회전/병진 목표를 모두 실제 Jacobian으로 푼다.
        weight = np.array([1, 1, 1, 0.35, 0.35, 0.35])
        weighted_j = weight[:, None] * jacobian
        rhs = weight * error
        delta = weighted_j.T @ np.linalg.solve(
            weighted_j @ weighted_j.T + self._ik_damping**2 * np.eye(6), rhs)
        delta *= min(0.6, self._max_joint_step / max(float(np.max(np.abs(delta))), 1e-12))
        positions_now = _array(self.articulation.get_dof_positions())[0]
        desired = np.clip(positions_now + delta, self._limits[:, 0], self._limits[:, 1])
        if not np.isfinite(desired).all():
            raise RuntimeError("UR10 IK가 유한하지 않은 관절 목표를 생성했습니다")
        self.articulation.set_dof_position_targets(desired[None, :])
        self._iterations += 1

    def move_to_view(self, view: str, step_callback: Callable[[int], None], move_steps: int = 120) -> dict[str, Any]:
        """Run bounded closed-loop IK with the caller's real simulation stepping."""
        plan = self.set_view(view)
        start = _array(self.articulation.get_dof_positions())[0].tolist()
        budget = max(int(move_steps), int(self.config.get("robot", {}).get("ik_max_steps", 600)))
        stable = 0
        for iteration in range(budget):
            self.step()
            step_callback(1)
            snapshot = self.snapshot()
            if iteration % 60 == 0:
                print("ROBOT_IK " + str({"view": view, "step": iteration + 1,
                      "position_error_m": snapshot["camera_position_error_m"],
                      "orientation_error_rad": snapshot["camera_orientation_error_rad"]}), flush=True)
            stable = stable + 1 if snapshot["ik_converged"] else 0
            if stable >= 8 and iteration + 1 >= min(int(move_steps), budget):
                break
        result = {**plan, "joint_positions_before": start, "physics_steps": self._iterations,
                  "result": self.snapshot()}
        self._moves.append(result)
        if not result["result"]["ik_converged"]:
            print("ROBOT_IK_FAILED_STATE " + str(result), flush=True)
            raise RuntimeError("UR10 카메라 목표 미도달: " + str({
                "view": view, "position_error_m": result["result"]["camera_position_error_m"],
                "orientation_error_rad": result["result"]["camera_orientation_error_rad"]}))
        return result

    def snapshot(self) -> dict[str, Any]:
        positions, quaternions = self._poses()
        wrist_q = quaternions[self._ee_index]
        camera_position = positions[self._ee_index] + _rotation(wrist_q) @ self.camera_local_translation
        # USD (-Z 전방,+Y 위) → ROS optical (+Z 전방,-Y 위): local X축 180도.
        optical_q = _quat_mul(wrist_q, np.array([0.0, 1.0, 0.0, 0.0]))
        position_error = (float(np.linalg.norm(self._target_position-camera_position))
                          if self._target_position is not None else None)
        orientation_error = (float(np.linalg.norm(_rotation_error(self._target_quaternion, wrist_q)))
                             if self._target_quaternion is not None else None)
        return {"camera_world_position": camera_position.tolist(),
                "camera_world_quaternion_wxyz": optical_q.tolist(),
                "camera_world_quaternion_usd_wxyz": wrist_q.tolist(),
                "camera_pose_convention": "ros_optical", "world_frame_convention": "usd_z_up",
                "camera_pose_source": "PhysX wrist link pose composed with fixed USD child transform",
                "camera_position_error_m": position_error,
                "camera_orientation_error_rad": orientation_error,
                "ik_converged": position_error is not None and position_error <= self._position_tolerance
                                  and orientation_error <= self._rotation_tolerance,
                "joint_names": self._dof_names,
                "joint_positions": _array(self.articulation.get_dof_positions())[0].tolist(),
                "robot_link_positions": {p.rsplit("/", 1)[-1]: positions[i].tolist()
                                         for i, p in enumerate(self._link_paths)},
                "ee_prim_path": self.ee_prim_path, "camera_prim_path": self.camera_prim_path,
                "camera_transform_check": self._camera_transform_check(camera_position, wrist_q)}

    def _camera_transform_check(self, physics_position: np.ndarray, physics_quaternion: np.ndarray) -> dict[str, Any]:
        """Record authored/USD writeback transforms separately from measured physics."""
        from pxr import Gf, Usd, UsdGeom

        camera = UsdGeom.Xformable(self.stage.GetPrimAtPath(self.camera_prim_path))
        wrist = UsdGeom.Xformable(self.stage.GetPrimAtPath(self.ee_prim_path))
        local = camera.GetLocalTransformation()
        world = camera.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        wrist_world = wrist.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        local_transform, world_transform = Gf.Transform(local), Gf.Transform(world)
        local_q = local_transform.GetRotation().GetQuat()
        world_q = world_transform.GetRotation().GetQuat()
        local_position = _array(local_transform.GetTranslation())
        world_position = _array(world_transform.GetTranslation())
        local_quaternion = np.array([local_q.GetReal(), *local_q.GetImaginary()])
        world_quaternion = np.array([world_q.GetReal(), *world_q.GetImaginary()])
        position_delta = float(np.linalg.norm(world_position-physics_position))
        rotation_delta = float(np.linalg.norm(_rotation_error(world_quaternion, physics_quaternion)))
        # USD writeback와 PhysX를 별도 보존한다. Fabric 렌더 자세라고 임의 단정하지 않는다.
        return {"source": "UsdGeom.ComputeLocalToWorldTransform / authored local xform",
                "usd_world_position": world_position.tolist(),
                "usd_world_quaternion_wxyz": world_quaternion.tolist(),
                "usd_world_scale": list(world_transform.GetScale()),
                "parent_usd_world_scale": list(Gf.Transform(wrist_world).GetScale()),
                "local_position": local_position.tolist(),
                "local_quaternion_wxyz": local_quaternion.tolist(),
                "local_scale": list(local_transform.GetScale()),
                "local_reset_xform_stack": camera.GetResetXformStack(),
                "local_xform_ops": [op.GetOpName() for op in camera.GetOrderedXformOps()],
                "fixed_mount_verified": bool(np.allclose(local_position, self.camera_local_translation, atol=1e-7)
                                             and np.linalg.norm(_rotation_error(local_quaternion, np.array([1.,0,0,0]))) < 1e-7
                                             and np.allclose(local_transform.GetScale(), [1,1,1], atol=1e-7)
                                             and not camera.GetResetXformStack()),
                "usd_to_physics_position_delta_m": position_delta,
                "usd_to_physics_rotation_delta_rad": rotation_delta,
                "usd_writeback_matches_physics": position_delta < 1e-4 and rotation_delta < 1e-4}

    def metadata(self) -> dict[str, Any]:
        return {"asset_path": self.asset_path, "robot_prim_path": self.robot_prim_path,
                "ee_prim_path": self.ee_prim_path, "camera_prim_path": self.camera_prim_path,
                "camera_fixed_mount_translation": self.camera_local_translation.tolist(),
                "camera_fixed_mount_quaternion_usd_wxyz": [1, 0, 0, 0],
                "camera_housing_prim_path": self.camera_housing_prim_path,
                "torch_prim_path": self.torch_prim_path, "torch_scope": "visual geometry only",
                "motion_method": "PhysX measured Jacobian damped-least-squares IK and motor position targets",
                "joint_state_teleport_used": False, "camera_teleport_used": False,
                "collision_free_path_validated": False, "execution_authorized": False,
                "position_tolerance_m": self._position_tolerance,
                "orientation_tolerance_rad": self._rotation_tolerance,
                "moves": self._moves}


def setup_robot(world: Any, stage: Any, config: dict[str, Any]) -> WristRobotController:
    """Create UR10 and its fixed wrist camera before the caller resets the world."""
    return WristRobotController(world, stage, config)


def setup(stage: Any, config: dict[str, Any]) -> WristRobotController:
    """Convenience alias for callers that keep the World solely outside this helper."""
    return setup_robot(None, stage, config)
