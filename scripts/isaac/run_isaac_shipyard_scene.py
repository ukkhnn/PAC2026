#!/usr/bin/env python3
"""Render the Isaac Sim shipyard panel scene: vertical steel jig, hand-drawn memo, fixed worklight glare, UR10 wrist camera A/B.

Run with the Isaac Sim 6.1 Python environment. A/B are scheduled presentation poses
(``capture_mode=pre_captured``), not recognition-triggered recapture. Rendered RGB is never
composited or retouched; A and B share geometry, marking, light, material and exposure.

Modes
  --predict  no Isaac: predicted specular highlight for A/B and a reach estimate from the config
  --draft    start Isaac, render warm-up frames from both cameras, save them and exit (no arm motion)
  default    full A/B pair; add --live to keep cycling A/B and streaming the latest RGB

The runner refuses any output directory that already contains files, even without a manifest.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import time

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from isaac_shipyard_marking import generate_panel_textures  # noqa: E402

UR10_SHOULDER_HEIGHT = 0.1273
UR10_SHOULDER_TO_WRIST1_MAX = 0.612 + 0.5723
UR10_ASSET = "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.1/Isaac/Robots/UniversalRobots/ur10/ur10.usd"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value) -> None:
    path = Path(path)
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def look_rotation(position, target):
    """Rotation matrix (columns = camera x,y,z axes) for a USD camera (-z forward, +y up) looking at target."""
    position, target = np.asarray(position, float), np.asarray(target, float)
    forward = target - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.array([0.0, 0.0, 1.0]))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return np.stack([right, up, -forward], axis=1)


def predict_highlights(cfg: dict) -> dict:
    """Mirror-reflection geometry of the fixed worklight in the centre panel for each view."""
    center = cfg["panels"]["center"]
    xp = float(center["front_x"])
    lamp = np.asarray(cfg["worklight"]["position"], float)
    mirrored = lamp.copy()
    mirrored[0] = 2 * xp - lamp[0]
    text_c = np.array([xp, *cfg["marking"]["text_center_yz"]], float)
    label_c = np.array([xp, *cfg["marking"]["label_center_yz"]], float)
    lamp_half = (float(cfg["worklight"]["width"]) + float(cfg["worklight"]["height"])) / 4
    roughness = float(cfg["metal"]["roughness"])
    mount = np.asarray(cfg["robot"]["camera_mount_translation"], float)
    shoulder = np.asarray(cfg["robot"]["base_position"], float) + np.array([0, 0, UR10_SHOULDER_HEIGHT])
    text_half_w = float(cfg["marking"]["text_height_m"]) * 0.75 * len(cfg["marking"]["text"]) / 2
    text_half_h = float(cfg["marking"]["text_height_m"]) / 2
    result = {"panel_front_x": xp, "worklight_position": lamp.tolist(), "mirrored_worklight": mirrored.tolist(),
              "text_center_yz": text_c[1:].tolist(), "text_half_extent_yz_estimate": [text_half_w, text_half_h], "views": {}}
    for view, item in cfg["views"].items():
        cam = np.asarray(item["camera_position"], float)
        t = (xp - cam[0]) / (mirrored[0] - cam[0])
        point = cam + t * (mirrored - cam)
        cam_dist = float(np.linalg.norm(point - cam))
        radius = lamp_half * t + cam_dist * roughness * 0.5
        offset = point[1:] - text_c[1:]
        overlaps_text = bool(abs(offset[0]) < text_half_w + radius and abs(offset[1]) < text_half_h + radius)
        wrist = cam - look_rotation(cam, item["look_at"]) @ mount
        reach = float(np.linalg.norm(wrist - shoulder))
        view_dir = np.asarray(item["look_at"], float) - cam
        result["views"][view] = {
            "camera_position": cam.tolist(),
            "highlight_point_on_panel": point.tolist(),
            "highlight_offset_from_text_center_yz": offset.tolist(),
            "highlight_offset_from_label_center_yz": (point[1:] - label_c[1:]).tolist(),
            "highlight_radius_estimate_m": radius,
            "overlaps_text_estimate": overlaps_text,
            "camera_to_highlight_m": cam_dist,
            "camera_to_text_m": float(np.linalg.norm(text_c - cam)),
            "reflection_angle_from_normal_deg": math.degrees(math.acos(min(1.0, (point[0] - cam[0]) / cam_dist))),
            "view_yaw_deg": math.degrees(math.atan2(-view_dir[1], view_dir[0])),
            "view_pitch_deg": math.degrees(math.atan2(view_dir[2], math.hypot(view_dir[0], view_dir[1]))),
            "wrist_position_estimate": wrist.tolist(),
            "shoulder_to_wrist_m": reach,
            "reach_fraction_of_ur10_max": reach / UR10_SHOULDER_TO_WRIST1_MAX,
        }
    return result


def prepare_output(out: Path, cfg: dict, config_path: Path) -> dict:
    if out.exists() and any(out.iterdir()):
        entries = sorted(p.name for p in out.iterdir())[:8]
        raise RuntimeError("Output directory is not empty; use a new one to preserve previous runs (and keep logs/pid files "
                           f"outside the output directory): {out} contains {entries}")
    for folder in ["assets", "frames", "stream", "source"]:
        (out / folder).mkdir(parents=True, exist_ok=True)
    atomic_json(out / "config.json", cfg)
    source_hashes = {}
    for script in [Path(__file__).resolve(), SCRIPT_DIR / "isaac_scene_robot.py", SCRIPT_DIR / "isaac_shipyard_marking.py"]:
        content = script.read_bytes()
        (out / "source" / script.name).write_bytes(content)
        source_hashes["source/" + script.name] = hashlib.sha256(content).hexdigest()
    return {"config_path": str(config_path), "config_sha256": sha256_file(out / "config.json"), "source_hashes": source_hashes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path("configs/isaac_scene/shipyard_handwriting.json"))
    parser.add_argument("--output", type=Path, help="New, empty output directory (required unless --predict)")
    parser.add_argument("--predict", action="store_true", help="Print highlight/reach predictions and exit (no Isaac)")
    parser.add_argument("--draft", action="store_true", help="Render warm-up frames only, then exit")
    parser.add_argument("--live", action="store_true", help="Keep the scheduled A/B presentation running")
    parser.add_argument("--kit-http-port", type=int, help="Kit internal HTTP port (default from config, 8031)")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    prediction = predict_highlights(cfg)
    if args.predict:
        print(json.dumps(prediction, ensure_ascii=False, indent=2))
        return 0
    if args.output is None:
        parser.error("--output is required unless --predict is used")
    out = args.output.resolve()
    repo_root = SCRIPT_DIR.parents[1]
    try:
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=repo_root).strip()
        git_dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True, cwd=repo_root).strip())
    except (OSError, subprocess.CalledProcessError) as exc:
        print("GIT_METADATA_UNAVAILABLE " + str(exc), flush=True)
        git_commit, git_dirty = None, None
    run_meta = prepare_output(out, cfg, args.config)
    run_meta["config_source_sha256"] = sha256_file(args.config)
    atomic_json(out / "prediction.json", prediction)
    marking_meta = generate_panel_textures(cfg["marking"], cfg["panels"], out / "assets")
    print("MARKING_GENERATED " + json.dumps(marking_meta["files"]), flush=True)
    port = args.kit_http_port or int(cfg.get("kit_http_port", 8031))

    import faulthandler
    faulthandler.dump_traceback_later(120, repeat=True)
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "renderer": cfg["render"]["renderer"], "width": 1280, "height": 720,
                         "anti_aliasing": 3, "disable_viewport_updates": True, "create_new_stage": False, "multi_gpu": False,
                         "samples_per_pixel_per_frame": cfg["render"]["samples_per_pixel"],
                         "extra_args": ["--/app/window/enabled=false", f"--/exts/omni.services.transport.server.http/port={port}"]})
    print("APP_INITIALIZED", flush=True)
    import carb
    import omni.usd
    from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdShade
    from PIL import Image
    import isaacsim.core.experimental.utils.app as app_utils
    try:
        from isaacsim.core.api import World
    except ModuleNotFoundError:
        app_utils.enable_extension("isaacsim.core.api")
        app.update()
        from isaacsim.core.api import World
    from isaacsim.sensors.experimental.rtx import RtxCamera, CameraSensor
    from isaac_scene_robot import setup_robot

    running = True

    class StopRequested(Exception):
        """Raised from step() once SIGTERM/SIGINT arrived, so IK loops never spin without physics."""

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    settings = carb.settings.get_settings()
    fixed = cfg["render"]["fixed_exposure"]
    settings.set("/rtx/post/histogram/enabled", False)
    settings.set("/rtx/post/tonemap/filmIso", fixed["film_iso"])
    settings.set("/rtx/post/tonemap/cameraShutter", fixed["shutter"])
    settings.set("/rtx/post/tonemap/fNumber", fixed["f_number"])
    settings.set("/rtx/pathtracing/spp", cfg["render"]["samples_per_pixel"])
    print("MODULES_IMPORTED", flush=True)
    world = World(stage_units_in_meters=1.0, physics_dt=1 / 60, rendering_dt=1 / 60)
    print("WORLD_CREATED", flush=True)
    stage = omni.usd.get_context().get_stage()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    UsdGeom.Xform.Define(stage, "/World/Workshop")
    UsdGeom.Xform.Define(stage, "/World/Lights")

    # ---------------------------------------------------------------- materials
    def material(name, color, metal=0.0, rough=0.5, coat=0.0, coat_rough=0.1, texture=None):
        m = UsdShade.Material.Define(stage, "/World/Materials/" + name)
        s = UsdShade.Shader.Define(stage, m.GetPath().AppendChild("Surface"))
        s.CreateIdAttr("UsdPreviewSurface")
        for key, val in [("metallic", metal), ("roughness", rough), ("clearcoat", coat), ("clearcoatRoughness", coat_rough)]:
            s.CreateInput(key, Sdf.ValueTypeNames.Float).Set(float(val))
        s.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
        if texture:
            uv = UsdShade.Shader.Define(stage, m.GetPath().AppendChild("UV"))
            uv.CreateIdAttr("UsdPrimvarReader_float2")
            uv.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
            tex = UsdShade.Shader.Define(stage, m.GetPath().AppendChild("Texture"))
            tex.CreateIdAttr("UsdUVTexture")
            tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(texture))
            tex.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
            tex.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
            tex.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
            tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(uv.ConnectableAPI(), "result")
            tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
            s.GetInput("diffuseColor").ConnectToSource(tex.ConnectableAPI(), "rgb")
        m.CreateSurfaceOutput().ConnectToSource(s.ConnectableAPI(), "surface")
        return m

    metal = cfg["metal"]
    mats = {
        "floor": material("Concrete", (0.075, 0.085, 0.095), rough=0.92),
        "floor_dark": material("ConcreteStain", (0.05, 0.055, 0.06), rough=0.95),
        "primer": material("ShopPrimerSteel", (0.19, 0.21, 0.19), metal=0.55, rough=0.42),
        "dark_steel": material("DarkSteel", (0.09, 0.10, 0.11), metal=0.7, rough=0.38),
        "rust": material("RustySteel", (0.26, 0.13, 0.07), metal=0.2, rough=0.75),
        "weld": material("WeldBead", (0.16, 0.13, 0.10), metal=0.5, rough=0.55),
        "yellow": material("SafetyYellow", (0.62, 0.36, 0.03), rough=0.55),
        "yellow_faded": material("FadedFloorPaint", (0.34, 0.24, 0.05), rough=0.85),
        "machine": material("MachineGray", (0.13, 0.15, 0.17), metal=0.3, rough=0.45),
        "orange": material("MachineOrange", (0.55, 0.16, 0.03), rough=0.5),
        "blue": material("HoseBlue", (0.04, 0.08, 0.15), rough=0.65),
        "rubber": material("CableRubber", (0.012, 0.013, 0.016), rough=0.72),
        "wood": material("Dunnage", (0.26, 0.17, 0.09), rough=0.9),
        "cylinder": material("GasCylinder", (0.10, 0.16, 0.12), metal=0.3, rough=0.4),
        "far": material("FarStructure", (0.05, 0.055, 0.065), metal=0.3, rough=0.7),
        "lamp": material("LampHousing", (0.015, 0.016, 0.018), rough=0.5),
        "lamp_yellow": material("LampYellow", (0.6, 0.38, 0.04), rough=0.5),
    }
    mats["panel_center"] = material("PanelCenterMarked", (0.3, 0.33, 0.3), metal=metal["metallic"], rough=metal["roughness"],
                                    coat=metal["clearcoat"], coat_rough=metal["clearcoat_roughness"], texture=out / "assets/panel_center_albedo.png")
    mats["panel_side"] = material("PanelSide", (0.3, 0.33, 0.3), metal=metal["metallic"], rough=metal["roughness"],
                                  coat=metal["clearcoat"], coat_rough=metal["clearcoat_roughness"], texture=out / "assets/panel_side_albedo.png")

    # ---------------------------------------------------------------- geometry helpers
    def box(path, pos, size, mat, rot_z=0.0, rot_y=0.0):
        p = UsdGeom.Cube.Define(stage, path)
        p.CreateSizeAttr(1)
        p.AddTranslateOp().Set(Gf.Vec3d(*pos))
        if rot_z:
            p.AddRotateZOp().Set(float(rot_z))
        if rot_y:
            p.AddRotateYOp().Set(float(rot_y))
        p.AddScaleOp().Set(Gf.Vec3f(*size))
        UsdShade.MaterialBindingAPI.Apply(p.GetPrim()).Bind(mats[mat])
        return p

    def cylinder(path, pos, radius, height, mat, axis="Z"):
        c = UsdGeom.Cylinder.Define(stage, path)
        c.CreateAxisAttr(axis)
        c.CreateRadiusAttr(float(radius))
        c.CreateHeightAttr(float(height))
        c.AddTranslateOp().Set(Gf.Vec3d(*pos))
        UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(mats[mat])
        return c

    def segment(path, p0, p1, radius, mat):
        p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
        d = p1 - p0
        length = float(np.linalg.norm(d))
        c = UsdGeom.Cylinder.Define(stage, path)
        c.CreateAxisAttr("Z")
        c.CreateRadiusAttr(float(radius))
        c.CreateHeightAttr(length)
        c.AddTranslateOp().Set(Gf.Vec3d(*((p0 + p1) / 2)))
        rotation = Gf.Rotation(Gf.Vec3d(0, 0, 1), Gf.Vec3d(*(d / length)))
        c.AddOrientOp().Set(Gf.Quatf(rotation.GetQuat()))
        UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(mats[mat])
        return c

    def quad(path, points, uvs, normal, mat):
        mesh = UsdGeom.Mesh.Define(stage, path)
        mesh.CreatePointsAttr([Gf.Vec3f(*p) for p in points])
        mesh.CreateFaceVertexCountsAttr([4])
        mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
        mesh.CreateSubdivisionSchemeAttr("none")
        mesh.CreateNormalsAttr([Gf.Vec3f(*normal)] * 4)
        mesh.SetNormalsInterpolation("vertex")
        mesh.CreateDoubleSidedAttr(True)
        st = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
        st.Set([Gf.Vec2f(*uv) for uv in uvs])
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(mats[mat])
        return mesh

    def look_quat(position, target):
        matrix = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*position), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1)).GetInverse()
        return matrix.ExtractRotationQuat()

    # ---------------------------------------------------------------- hall and floor
    W = "/World/Workshop/"
    box(W + "Floor", (3, 0, -0.06), (36, 36, 0.12), "floor")
    for i, (x, y, sx, sy) in enumerate([(4.5, -3.5, 7, 3), (-3, 5, 5, 4), (9, 4, 6, 6)]):
        box(W + f"FloorStain{i}", (x, y, 0.0005), (sx, sy, 0.001), "floor_dark")
    box(W + "FarWall", (16, 0, 4), (0.3, 36, 8), "far")
    box(W + "Ceiling", (3, 0, 9.15), (36, 36, 0.3), "far")
    box(W + "RightWall", (3, -14, 4), (36, 0.3, 8), "far")
    for i, (x, y) in enumerate([(-6, -6), (-6, 6), (6, -6), (6, 6), (6, 12), (-6, 12), (14, -6), (14, 6)]):
        box(W + f"Column{i}", (x, y, 3.5), (0.4, 0.4, 7), "far")
    for i, y in enumerate([-6, 6]):
        box(W + f"CraneRail{i}", (4, y, 6.6), (24, 0.5, 0.6), "far")
    box(W + "CraneGirder", (5.5, 0, 7.1), (0.7, 12.6, 0.8), "far")
    box(W + "FarBlock", (8.5, 7.5, 1.4), (5.5, 3.2, 2.8), "far")
    box(W + "FarBlockStiffener", (5.7, 7.5, 1.4), (0.1, 3.0, 2.6), "far")
    for i, (x, y, rot) in enumerate([(-0.6, 4.0, 8), (1.7, 4.6, -5)]):
        for j in range(2):
            box(W + f"Dunnage{i}_{j}", (x + (j - 0.5) * 1.2, y, 0.05), (0.14, 1.1, 0.1), "wood", rot_z=rot)
        for j in range(5):
            box(W + f"StockPlate{i}_{j}", (x, y, 0.1 + 0.011 + j * 0.022), (2.2, 1.0, 0.02), "primer" if j % 2 else "rust", rot_z=rot)
    box(W + "HBeam", (3.8, -4.2, 0.15), (6.0, 0.3, 0.3), "rust", rot_z=12)
    box(W + "HBeam2", (3.9, -4.65, 0.15), (6.0, 0.3, 0.3), "primer", rot_z=12)
    for i, (pos, size) in enumerate([((-2.3, 0.3, 0.0015), (0.08, 5.0, 0.003)), ((-0.3, -2.5, 0.0015), (4.2, 0.08, 0.003)),
                                     ((-0.3, 3.0, 0.0015), (4.2, 0.08, 0.003))]):
        box(W + f"FloorLine{i}", pos, size, "yellow_faded")

    # ---------------------------------------------------------------- centre panel with seam, strongbacks and stiffeners
    center = cfg["panels"]["center"]
    xf, pw, ph, pt, z0 = (float(center[k]) for k in ("front_x", "width", "height", "thickness", "bottom_z"))
    z1 = z0 + ph
    seam, gap = float(center["seam_y"]), float(center["seam_gap"])
    left_edge, right_edge = pw / 2, -pw / 2
    body_x = xf + pt / 2
    for name, ya, yb in [("Left", left_edge, seam + gap / 2), ("Right", seam - gap / 2, right_edge)]:
        box(W + f"CenterPlate{name}", (body_x, (ya + yb) / 2, (z0 + z1) / 2), (pt, abs(ya - yb), ph), "primer")
    box(W + "SeamBacking", (xf + pt + 0.004, seam, (z0 + z1) / 2), (0.006, gap + 0.03, ph), "rubber")
    face_x = xf - 0.0005

    def u_of(y):
        return (pw / 2 - y) / pw

    for name, ya, yb in [("Left", left_edge, seam + gap / 2), ("Right", seam - gap / 2, right_edge)]:
        quad(W + f"CenterFace{name}",
             [(face_x, ya, z0), (face_x, yb, z0), (face_x, yb, z1), (face_x, ya, z1)],
             [(u_of(ya), 0), (u_of(yb), 0), (u_of(yb), 1), (u_of(ya), 1)], (-1, 0, 0), "panel_center")
    for i, y in enumerate(center["front_stiffener_y"]):
        box(W + f"CenterFrontStiffener{i}", (xf - 0.05, float(y), (z0 + z1) / 2), (0.10, 0.012, ph - 0.06), "primer")
    for i, z in enumerate(center["back_stiffener_z"]):
        box(W + f"CenterBackStiffener{i}", (xf + pt + 0.05, 0, float(z)), (0.10, pw - 0.1, 0.012), "primer")
    for i, z in enumerate(center["strongback_z"]):
        box(W + f"Strongback{i}", (xf - 0.022, seam, float(z)), (0.034, 0.28, 0.05), "dark_steel")
        for j, dy in enumerate((-0.1, 0.1)):
            box(W + f"StrongbackWedge{i}_{j}", (xf - 0.006, seam + dy, float(z)), (0.012, 0.03, 0.04), "rust")
            cylinder(W + f"StrongbackTack{i}_{j}", (xf - 0.004, seam + dy * 1.3, float(z) - 0.03), 0.006, 0.02, "weld")
    for i, z in enumerate(center["tack_weld_z"]):
        cylinder(W + f"TackWeld{i}", (xf - 0.002, seam, float(z)), 0.007, 0.035, "weld")
    for i, y in enumerate(center["top_clamp_y"]):
        box(W + f"TopClamp{i}", (body_x, float(y), z1 - 0.035), (0.075, 0.05, 0.13), "dark_steel")
        cylinder(W + f"TopClampScrew{i}", (xf - 0.045, float(y), z1 - 0.06), 0.009, 0.05, "dark_steel", axis="X")
    for i, y in enumerate((0.75, -0.8)):
        box(W + f"CenterDunnage{i}", (body_x, y, z0 / 2), (0.3, 0.16, z0), "wood")
    for i, y in enumerate((0.95, -0.95)):
        box(W + f"CenterStandBase{i}", (xf - 0.26, y, 0.012), (0.52, 0.14, 0.024), "dark_steel")
        box(W + f"CenterStandPost{i}", (xf - 0.115, y, 0.25), (0.04, 0.14, 0.5), "dark_steel")
        box(W + f"CenterStandBrace{i}", (xf - 0.3, y, 0.27), (0.04, 0.12, 0.62), "dark_steel", rot_y=38)

    # ---------------------------------------------------------------- side wings hinged at the centre panel edges
    sides = cfg["panels"]["sides"]
    sw, sh, st_, angle = float(sides["width"]), float(sides["height"]), float(sides["thickness"]), float(sides["angle_deg"])
    for name, sign in (("Left", 1.0), ("Right", -1.0)):
        root = UsdGeom.Xform.Define(stage, W + f"Wing{name}")
        root.AddTranslateOp().Set(Gf.Vec3d(body_x, sign * pw / 2, 0))
        root.AddRotateZOp().Set(sign * angle)
        base = W + f"Wing{name}/"
        box(base + "Plate", (0, sign * sw / 2, (z0 + z1) / 2), (st_, sw, sh), "primer")
        fx = -st_ / 2 - 0.0005
        ya, yb = (0.0, sign * sw) if sign > 0 else (sign * sw, 0.0)
        # p0->p1 runs toward -y so the right-hand winding matches the authored -x normal (same as the centre faces).
        quad(base + "Face", [(fx, yb, z0), (fx, ya, z0), (fx, ya, z1), (fx, yb, z1)], [(0, 0), (1, 0), (1, 1), (0, 1)], (-1, 0, 0), "panel_side")
        for i, f in enumerate(sides["front_stiffener_fraction"]):
            box(base + f"Stiffener{i}", (-st_ / 2 - 0.05, sign * sw * float(f), (z0 + z1) / 2), (0.10, 0.012, sh - 0.06), "primer")
        box(base + "Dunnage", (0, sign * sw * 0.5, z0 / 2), (0.3, 0.16, z0), "wood")
        box(base + "StandBase", (-st_ / 2 - 0.25, sign * sw * 0.82, 0.012), (0.5, 0.14, 0.024), "dark_steel")
        box(base + "StandPost", (-st_ / 2 - 0.11, sign * sw * 0.82, 0.25), (0.04, 0.14, 0.5), "dark_steel")
        box(base + "HingeBracket", (-st_ / 2 - 0.03, sign * 0.03, z1 - 0.1), (0.06, 0.1, 0.12), "dark_steel")

    # ---------------------------------------------------------------- robot pedestal, welding set, cables, lamp
    base = cfg["robot"]["base_position"]
    psx, psy = cfg["robot"].get("pedestal_size", [0.42, 0.42])
    box(W + "RobotPedestal", (base[0], base[1], base[2] / 2), (psx, psy, base[2]), "dark_steel")
    box(W + "RobotPedestalPlate", (base[0], base[1], 0.0125), (psx + 0.35, psy + 0.35, 0.025), "dark_steel")
    box(W + "PedestalJunctionBox", (base[0] - psx / 2 - 0.06, base[1] + 0.05, 0.55), (0.12, 0.22, 0.16), "machine")
    box(W + "PowerSupply", (-1.35, -0.95, 0.425), (0.62, 0.52, 0.85), "machine")
    box(W + "PowerSupplyPanel", (-1.35, -0.95 + 0.26, 0.55), (0.5, 0.012, 0.34), "orange")
    box(W + "PowerSupplyDisplay", (-1.35, -0.95 + 0.268, 0.62), (0.22, 0.006, 0.08), "rubber")
    box(W + "WireFeeder", (-1.3, -0.95, 0.85 + 0.15), (0.5, 0.26, 0.3), "machine")
    spool = UsdGeom.Cylinder.Define(stage, W + "WireSpool")
    spool.CreateAxisAttr("Y")
    spool.CreateRadiusAttr(0.15)
    spool.CreateHeightAttr(0.1)
    spool.AddTranslateOp().Set(Gf.Vec3d(-1.3, -0.95 + 0.18, 1.0 + 0.16))
    UsdShade.MaterialBindingAPI.Apply(spool.GetPrim()).Bind(mats["rust"])
    cylinder(W + "GasCylinder", (-1.78, -0.78, 0.725), 0.115, 1.45, "cylinder")
    cylinder(W + "GasValve", (-1.78, -0.78, 1.5), 0.035, 0.1, "dark_steel")
    box(W + "CylinderCart", (-1.78, -0.78, 0.04), (0.4, 0.4, 0.08), "dark_steel")
    cables = {
        "Cable0": [(-1.05, -0.95, 0.35), (-0.7, -0.75, 0.012), (-0.35, -0.45, 0.012), (-0.05, -0.28, 0.012), (0.05, -0.1, 0.3), (0.06, 0.0, 0.55)],
        "Cable1": [(-1.05, -1.05, 0.3), (-0.5, -1.2, 0.012), (0.2, -1.1, 0.012), (0.8, -0.9, 0.012), (1.12, -0.7, 0.012), (1.15, -0.62, 0.08)],
        "Hose": [(-1.78, -0.78, 1.45), (-1.55, -0.7, 0.9), (-1.3, -0.55, 0.012), (-0.6, -0.3, 0.012), (-0.2, -0.05, 0.3), (-0.19, 0.05, 0.6)],
    }
    for name, points in cables.items():
        for i in range(len(points) - 1):
            segment(W + f"{name}_{i}", points[i], points[i + 1], 0.011 if name == "Hose" else 0.014, "blue" if name == "Hose" else "rubber")
    box(W + "EarthClamp", (xf - 0.05, -0.62, 0.11), (0.1, 0.05, 0.08), "dark_steel")
    box(W + "Toolbox", (-0.9, 1.3, 0.14), (0.55, 0.3, 0.28), "orange")
    box(W + "GrinderCase", (-0.95, 1.75, 0.08), (0.45, 0.25, 0.16), "rubber")

    lc = cfg["worklight"]
    lamp = UsdLux.RectLight.Define(stage, "/World/Lights/FixedWorklight")
    lamp.CreateWidthAttr(lc["width"])
    lamp.CreateHeightAttr(lc["height"])
    lamp.CreateIntensityAttr(lc["intensity"])
    lamp.CreateColorAttr(Gf.Vec3f(*lc["color"]))
    lamp.CreateNormalizeAttr(False)
    lamp.AddTranslateOp().Set(Gf.Vec3d(*lc["position"]))
    lamp.AddOrientOp().Set(Gf.Quatf(look_quat(lc["position"], lc["look_at"])))
    housing = UsdGeom.Cube.Define(stage, "/World/Lights/FixedWorklight/Housing")
    housing.CreateSizeAttr(1)
    housing.AddTranslateOp().Set(Gf.Vec3d(0, 0, 0.035))
    housing.AddScaleOp().Set(Gf.Vec3f(lc["width"] + 0.05, lc["height"] + 0.05, 0.06))
    UsdShade.MaterialBindingAPI.Apply(housing.GetPrim()).Bind(mats["lamp"])
    for i, sx in enumerate((-1, 1)):
        yoke = UsdGeom.Cube.Define(stage, f"/World/Lights/FixedWorklight/Yoke{i}")
        yoke.CreateSizeAttr(1)
        yoke.AddTranslateOp().Set(Gf.Vec3d(sx * (lc["width"] / 2 + 0.035), 0, 0.03))
        yoke.AddScaleOp().Set(Gf.Vec3f(0.015, 0.05, 0.09))
        UsdShade.MaterialBindingAPI.Apply(yoke.GetPrim()).Bind(mats["lamp_yellow"])
    sb = lc["stand_base"]
    # The mast stops 0.32 m below the emitter so it stays in the head's shadow instead of glowing like a tube.
    head = np.asarray(lc["position"], float) + np.array([0, 0, -0.32])
    hub = np.array([sb[0], sb[1], head[2] - 0.5])
    segment(W + "LampMast", hub, head, 0.018, "lamp")
    segment(W + "LampStem", head, np.asarray(lc["position"], float) + np.array([0, 0, -0.16]), 0.012, "lamp")
    hood = UsdGeom.Cube.Define(stage, "/World/Lights/FixedWorklight/Hood")
    hood.CreateSizeAttr(1)
    hood.AddTranslateOp().Set(Gf.Vec3d(0, -(lc["height"] / 2 + 0.03), 0.0))
    hood.AddScaleOp().Set(Gf.Vec3f(lc["width"] + 0.05, 0.01, 0.07))
    UsdShade.MaterialBindingAPI.Apply(hood.GetPrim()).Bind(mats["lamp"])
    for i in range(3):
        a = math.radians(30 + i * 120)  # feet at 30/150/270 deg keep the legs clear of the robot pedestal plate
        foot = np.array([sb[0] + 0.55 * math.cos(a), sb[1] + 0.55 * math.sin(a), 0.0])
        segment(W + f"LampLeg{i}", foot, hub, 0.014, "lamp_yellow")
    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/NightAmbient")
    dome.CreateIntensityAttr(cfg["ambient_intensity"])
    dome.CreateColorAttr(Gf.Vec3f(*cfg.get("ambient_color", [0.42, 0.51, 0.65])))
    fc = cfg["fill_light"]
    fill = UsdLux.RectLight.Define(stage, "/World/Lights/SoftShopFill")
    fill.CreateWidthAttr(fc["width"])
    fill.CreateHeightAttr(fc["height"])
    fill.CreateIntensityAttr(fc["intensity"])
    fill.CreateColorAttr(Gf.Vec3f(*fc["color"]))
    fill.CreateNormalizeAttr(False)
    fill.AddTranslateOp().Set(Gf.Vec3d(*fc["position"]))
    fill.AddOrientOp().Set(Gf.Quatf(look_quat(fc["position"], fc["look_at"])))
    for i, far in enumerate(cfg.get("far_lights", [])):
        sphere = UsdLux.SphereLight.Define(stage, f"/World/Lights/FarHallLight{i}")
        sphere.CreateRadiusAttr(far["radius"])
        sphere.CreateIntensityAttr(far["intensity"])
        sphere.CreateColorAttr(Gf.Vec3f(*far["color"]))
        sphere.CreateNormalizeAttr(False)
        sphere.AddTranslateOp().Set(Gf.Vec3d(*far["position"]))
        shade = UsdGeom.Cylinder.Define(stage, f"/World/Lights/FarHallLight{i}/Shade")
        shade.CreateRadiusAttr(far["radius"] * 1.6)
        shade.CreateHeightAttr(0.25)
        shade.AddTranslateOp().Set(Gf.Vec3d(0, 0, far["radius"] + 0.2))
        UsdShade.MaterialBindingAPI.Apply(shade.GetPrim()).Bind(mats["far"])
    print("WORKSHOP_CREATED", flush=True)

    robot = setup_robot(world, stage, cfg)
    # Extra end-effector visuals (behind the camera's optical plane, so never in its view): a larger camera
    # body behind the helper's housing and a torch cable running back along the wrist. Visual only.
    mount = np.asarray(cfg["robot"]["camera_mount_translation"], float)
    body = UsdGeom.Cube.Define(stage, robot.ee_prim_path + "/CameraBody")
    body.CreateSizeAttr(1)
    body.AddTranslateOp().Set(Gf.Vec3d(float(mount[0]), 0.0, float(mount[2]) + 0.095))
    body.AddScaleOp().Set(Gf.Vec3f(0.08, 0.06, 0.06))
    UsdShade.MaterialBindingAPI.Apply(body.GetPrim()).Bind(mats["machine"])
    cable_points = [(-0.08, 0.0, 0.07), (-0.10, 0.02, 0.16), (-0.07, 0.05, 0.26), (-0.02, 0.07, 0.36)]
    for i in range(len(cable_points) - 1):
        segment(robot.ee_prim_path + f"/TorchCable{i}", cable_points[i], cable_points[i + 1], 0.009, "rubber")
    print("ROBOT_LOADED", flush=True)
    overview = UsdGeom.Camera.Define(stage, "/World/OverviewCamera")
    overview.AddTranslateOp().Set(Gf.Vec3d(*cfg["overview"]["position"]))
    overview.AddOrientOp().Set(Gf.Quatf(look_quat(cfg["overview"]["position"], cfg["overview"]["look_at"])))
    camera_paths = {"wrist": robot.camera_prim_path, "overview": str(overview.GetPath())}
    sensors = {}
    for name, path in camera_paths.items():
        cam = UsdGeom.Camera(stage.GetPrimAtPath(path))
        focal = cfg["overview"].get("focal_length_mm", cfg["camera"]["focal_length_mm"]) if name == "overview" else cfg["camera"]["focal_length_mm"]
        cam.CreateFocalLengthAttr(focal)
        cam.CreateHorizontalApertureAttr(cfg["camera"]["horizontal_aperture_mm"])
        resolution_hw = cfg["overview"].get("resolution_hw", cfg["camera"]["resolution_hw"]) if name == "overview" else cfg["camera"]["resolution_hw"]
        height, width = resolution_hw
        cam.CreateVerticalApertureAttr(cfg["camera"]["horizontal_aperture_mm"] * height / width)
        cam.CreateClippingRangeAttr(Gf.Vec2f(0.015, 100))
        sensors[name] = CameraSensor(RtxCamera(path, tick_rate=cfg["camera"]["tick_rate"], reset_xform_op_properties=False),
                                     resolution=tuple(resolution_hw), annotators=["rgb"])
    print("CAMERAS_CREATED", flush=True)
    world.reset()
    robot.initialize()
    faulthandler.cancel_dump_traceback_later()
    print("SCENE_READY", flush=True)

    stream_ready = False
    phase = "initializing"
    rendered_steps = 0

    def save_rgb(sensor, target: Path):
        data, info = sensor.get_data("rgb")
        if data is None:
            raise RuntimeError("Camera has no fresh RGB: " + str(target))
        rgb = data.numpy()
        if rgb.ndim != 3 or rgb.shape[2] < 3:
            raise RuntimeError("Unexpected RGB shape " + str(rgb.shape))
        Image.fromarray(rgb[:, :, :3]).save(target)
        return rgb, info

    def export_stage():
        stage_text = stage.GetRootLayer().ExportToString()
        stage_text = stage_text.replace(str(out / "assets"), "./assets")
        (out / "scene.usda").write_text(stage_text)

    manifest = {
        "schema_version": "isaac-shipyard-capture.v1",
        "scene_schema_version": cfg["schema_version"],
        "scenario_id": cfg["scenario_id"],
        "capture_mode": "pre_captured",
        "recognition_feedback_enabled": False,
        "execution_authorized": False,
        "presentation": "scheduled A/B joint motion, not recognition feedback",
        "mode": "draft" if args.draft else ("live" if args.live else "pair"),
        "created_at_utc": utc_now(),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "simulator": "Isaac Sim 6.1",
        "renderer": cfg["render"]["renderer"],
        "kit_http_port": port,
        **run_meta,
        "marking": marking_meta,
        "asset_provenance": {
            "marking_textures": {name: {"path": "assets/" + name, "sha256": digest} for name, digest in marking_meta["files"].items()},
            "marking_generation": {"generator": marking_meta["generator"], "generator_sha256": marking_meta["generator_sha256"],
                                   "glyph_set_version": marking_meta["glyph_set_version"], "seed": marking_meta["seed"],
                                   "style": marking_meta["style"], "synthetic": True, "source": marking_meta["source"]},
            "external_assets": [{"name": "Universal Robots UR10", "kind": "USD reference", "path": robot.asset_path,
                                 "provider": "NVIDIA Isaac Sim 6.1 asset library", "copied_into_output": False}],
            "procedural_geometry": "all workshop geometry is USD primitives authored by scripts/isaac/run_isaac_shipyard_scene.py; no external meshes except the UR10",
        },
        "prediction": prediction,
        "camera_paths": camera_paths,
        "frames": {},
        "fixed_settings": {p: settings.get(p) for p in ["/rtx/post/histogram/enabled", "/rtx/post/tonemap/filmIso",
                                                        "/rtx/post/tonemap/cameraShutter", "/rtx/post/tonemap/fNumber"]},
    }
    def run_session():
        nonlocal stream_ready, phase
        def step(count):
            nonlocal rendered_steps
            for _ in range(count):
                if not running:
                    raise StopRequested()
                frame_started = time.monotonic()
                world.step(render=True)
                rendered_steps += 1
                if stream_ready and rendered_steps % cfg["presentation"]["stream_every_steps"] == 0:
                    capture(phase)
                if args.live:
                    time.sleep(max(0, 1 / 60 - (time.monotonic() - frame_started)))

        step(cfg["render"]["warmup_steps"])
        for name, sensor in sensors.items():
            rgb, _ = save_rgb(sensor, out / "frames" / f"initial-{name}.png")
            print("SENSOR_WARMUP", name, list(rgb.shape), flush=True)
        if args.draft:
            manifest["frames"]["draft"] = {"view": "draft", "captured_at_utc": utc_now(), "robot_pose": "seed pose, no scheduled motion",
                                           **{f"{n}_saved_image": f"frames/initial-{n}.png" for n in sensors},
                                           **{f"{n}_image_sha256": sha256_file(out / "frames" / f"initial-{n}.png") for n in sensors}}
            manifest["robot"] = robot.metadata()
            export_stage()
            manifest["stage"] = "scene.usda"
            manifest["stage_external_assets_required"] = True
            manifest["completed_at_utc"] = utc_now()
            atomic_json(out / "manifest.json", manifest)
            print("DRAFT_COMPLETE " + str(out), flush=True)
            return 0

        sequence = 0

        def capture(view, canonical=False):
            nonlocal sequence
            result = {"sequence": sequence, "view": view, "captured_at_utc": utc_now(), "simulation_time": world.current_time,
                      "capture_time_semantics": "host time reading latest RGB after rendered simulation steps",
                      "native_sensor_frame_id": None, "recognition_feedback_enabled": False, "capture_mode": "pre_captured",
                      "presentation_mode": "scheduled_pose_loop" if args.live else "saved_pair",
                      "scenario_id": cfg["scenario_id"], "scene_schema_version": cfg["schema_version"],
                      "execution_authorized": False}
            result.update(robot.snapshot())
            for name, sensor in sensors.items():
                data, info = sensor.get_data("rgb")
                if data is None:
                    raise RuntimeError("Camera has no fresh RGB: " + name)
                rgb = data.numpy()
                if rgb.ndim != 3 or rgb.shape[2] < 3:
                    raise RuntimeError("Unexpected RGB shape " + str(rgb.shape))
                # Encode once so the stream file, the canonical frame and the recorded hash are the same bytes.
                buffer = io.BytesIO()
                Image.fromarray(rgb[:, :, :3]).save(buffer, format="PNG")
                png_bytes = buffer.getvalue()
                target = out / "stream" / f"{name}.png"
                tmp = target.with_suffix(".tmp.png")
                tmp.write_bytes(png_bytes)
                tmp.replace(target)
                result[name + "_image"] = str(target.relative_to(out))
                result[name + "_sensor_info"] = {str(k): str(v) for k, v in info.items()} if isinstance(info, dict) else str(info)
                if canonical:
                    saved = out / "frames" / f"{view}-{name}.png"
                    saved.write_bytes(png_bytes)
                    result[name + "_saved_image"] = str(saved.relative_to(out))
                    result[name + "_image_sha256"] = hashlib.sha256(png_bytes).hexdigest()
            atomic_json(out / "stream/current.json", result)
            if canonical:
                atomic_json(out / "frames" / f"{view}-capture.json", result)
                manifest["frames"][view] = result
                atomic_json(out / "manifest.json", manifest)
            sequence += 1
            return result

        stream_ready = args.live
        for view in ["A", "B"]:
            phase = "moving_to_" + view
            robot.move_to_view(view, step, cfg["presentation"]["move_steps"])
            phase = view
            step(cfg["render"]["settle_steps"])
            capture(view, canonical=True)
            print("CAPTURED " + view, flush=True)
        export_stage()
        manifest["robot"] = robot.metadata()
        manifest["stage"] = "scene.usda"
        manifest["stage_external_assets_required"] = True
        manifest["completed_at_utc"] = utc_now()
        atomic_json(out / "manifest.json", manifest)
        print("PAIR_COMPLETE " + str(out), flush=True)
        if args.live:
            from itertools import cycle
            for view in cycle(["A", "B"]):
                if not running:
                    break
                phase = "moving_to_" + view
                robot.move_to_view(view, step, cfg["presentation"]["move_steps"])
                phase = view
                step(cfg["presentation"]["hold_steps"])
        return 0

    session_state = {"state": "running"}
    try:
        return run_session()
    except StopRequested:
        session_state = {"state": "stopped"}
        print("STOP_REQUESTED", flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001 - record the failure next to the partial output, then re-raise
        session_state = {"state": "failed", "error": f"{type(exc).__name__}: {exc}"}
        manifest["failed_at_utc"] = utc_now()
        manifest["error"] = session_state["error"]
        atomic_json(out / "manifest.json", manifest)
        print("RUN_FAILED " + session_state["error"], flush=True)
        raise
    finally:
        session_state["stopped_at_utc"] = utc_now()
        atomic_json(out / "stream/session.json", session_state)
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
