#!/usr/bin/env python3
"""Render an actual Isaac Sim wrist-camera glare scene, optionally keep it live.

Run with the Isaac Sim 6.1 Python environment. A/B are scheduled presentation
poses, not recognition-triggered recapture. Generated RGB is never composited.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import time


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.tmp.json')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def make_marking(path, cfg):
    from PIL import Image, ImageDraw, ImageFont
    candidates = ['/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf',
                  '/usr/share/fonts/truetype/liberation2/LiberationMono-Bold.ttf']
    font_path = next((p for p in candidates if Path(p).exists()), None)
    if font_path is None:
        raise RuntimeError('A scalable monospace font is required for the synthetic marking')
    image = Image.new('RGB', (2048, 1024), (83, 92, 103))
    d = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 245)
    small = ImageFont.truetype(font_path, 125)
    text = cfg['marking']['text']
    box = d.textbbox((0, 0), text, font=font)
    d.text(((2048 - (box[2]-box[0]))/2, 365), text, font=font, fill=(240,242,229))
    d.text((650, 635), cfg['marking']['joint_label'], font=small, fill=(240,242,229))
    d.line([(940,725),(1770,725)],fill=(240,242,229),width=17)
    d.polygon([(1770,725),(1670,677),(1670,773)],fill=(240,242,229))
    image.save(path)
    return {'font': Path(font_path).name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'source': cfg['marking']['source'], 'size': list(image.size)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('configs/isaac_scene/night_welding.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--live', action='store_true', help='Leave scheduled A/B presentation running')
    parser.add_argument('--native-ros', action='store_true', help='Attach Isaac ROS image writers too')
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    out = args.output.resolve()
    if (out/'manifest.json').exists():
        raise RuntimeError('Use a new output directory; previous captures must be preserved')
    for folder in ['assets','frames','stream','source']:
        (out/folder).mkdir(parents=True, exist_ok=True)
    atomic_json(out/'config.json',cfg)
    source_hashes={}
    for script in [Path(__file__),Path(__file__).with_name('isaac_scene_robot.py')]:
        content=script.read_bytes()
        (out/'source'/script.name).write_bytes(content)
        source_hashes['source/'+script.name]=hashlib.sha256(content).hexdigest()
    import subprocess
    git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    git_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip())
    marking_meta = make_marking(out/'assets/marking.png',cfg)
    import faulthandler
    faulthandler.dump_traceback_later(90, repeat=True)
    from isaacsim import SimulationApp
    app = SimulationApp({'headless':True,'renderer':cfg['render']['renderer'],
                         'width':1280,'height':720,'anti_aliasing':3,'disable_viewport_updates':True,
                         'create_new_stage':False,'multi_gpu':False,
                         'samples_per_pixel_per_frame':cfg['render']['samples_per_pixel'],
                         'extra_args':['--/app/window/enabled=false','--/exts/omni.services.transport.server.http/port=8021']})
    print('APP_INITIALIZED',flush=True)
    # Isaac imports require the application to exist first.
    import carb
    import numpy as np
    import omni.usd
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade
    from PIL import Image
    import isaacsim.core.experimental.utils.app as app_utils
    try:
        from isaacsim.core.api import World
    except ModuleNotFoundError:
        app_utils.enable_extension('isaacsim.core.api')
        app.update()
        from isaacsim.core.api import World
    from isaacsim.sensors.experimental.rtx import RtxCamera, CameraSensor
    from isaac_scene_robot import setup_robot

    running = True
    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    settings = carb.settings.get_settings()
    fixed = cfg['render']['fixed_exposure']
    settings.set('/rtx/post/histogram/enabled',False)
    settings.set('/rtx/post/tonemap/filmIso',fixed['film_iso'])
    settings.set('/rtx/post/tonemap/cameraShutter',fixed['shutter'])
    settings.set('/rtx/post/tonemap/fNumber',fixed['f_number'])
    settings.set('/rtx/pathtracing/spp',cfg['render']['samples_per_pixel'])
    print('MODULES_IMPORTED',flush=True)
    world = World(stage_units_in_meters=1.0, physics_dt=1/60, rendering_dt=1/60)
    print('WORLD_CREATED',flush=True)
    stage = omni.usd.get_context().get_stage()
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage,1.0)
    UsdGeom.Xform.Define(stage,'/World')
    stage.SetDefaultPrim(stage.GetPrimAtPath('/World'))

    def material(name,color,metal=0,rough=.5,coat=0,coat_rough=.1,texture=None):
        m = UsdShade.Material.Define(stage,'/World/Materials/'+name)
        s = UsdShade.Shader.Define(stage,m.GetPath().AppendChild('Surface'))
        s.CreateIdAttr('UsdPreviewSurface')
        for key,val in [('metallic',metal),('roughness',rough),('clearcoat',coat),('clearcoatRoughness',coat_rough)]:
            s.CreateInput(key,Sdf.ValueTypeNames.Float).Set(float(val))
        s.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
        if texture:
            uv=UsdShade.Shader.Define(stage,m.GetPath().AppendChild('UV'))
            uv.CreateIdAttr('UsdPrimvarReader_float2')
            uv.CreateInput('varname',Sdf.ValueTypeNames.Token).Set('st')
            tex=UsdShade.Shader.Define(stage,m.GetPath().AppendChild('Texture'))
            tex.CreateIdAttr('UsdUVTexture')
            tex.CreateInput('file',Sdf.ValueTypeNames.Asset).Set(str(texture))
            tex.CreateInput('sourceColorSpace',Sdf.ValueTypeNames.Token).Set('sRGB')
            tex.CreateInput('st',Sdf.ValueTypeNames.Float2).ConnectToSource(uv.ConnectableAPI(),'result')
            tex.CreateOutput('rgb',Sdf.ValueTypeNames.Float3)
            s.GetInput('diffuseColor').ConnectToSource(tex.ConnectableAPI(),'rgb')
        m.CreateSurfaceOutput().ConnectToSource(s.ConnectableAPI(),'surface')
        return m

    mats={
      'floor':material('Concrete',(.085,.10,.12),rough=.9),
      'table':material('TableSteel',(.12,.15,.18),metal=.75,rough=.35),
      'steel':material('Steel',(.27,.32,.36),metal=.8,rough=.2),
      'yellow':material('SafetyYellow',(.7,.37,.018),rough=.5),
      'red':material('WeldingCurtain',(.14,.021,.018),rough=.9),
      'blue':material('MachineBlue',(.018,.12,.20),metal=.25,rough=.4),
      'dark':material('Rubber',(.012,.014,.018),rough=.7)}
    metal=cfg['metal']
    mats['mark']=material('MarkedMetal',(.3,.35,.4),metal=metal['metallic'],rough=metal['roughness'],
                          coat=metal['clearcoat'],coat_rough=metal['clearcoat_roughness'],texture=out/'assets/marking.png')

    def box(name,pos,size,mat):
        p=UsdGeom.Cube.Define(stage,'/World/Workshop/'+name)
        p.CreateSizeAttr(1)
        p.AddTranslateOp().Set(Gf.Vec3d(*pos))
        p.AddScaleOp().Set(Gf.Vec3f(*size))
        UsdShade.MaterialBindingAPI.Apply(p.GetPrim()).Bind(mats[mat])
        return p
    box('Floor',(0,0,-.06),(7,6,.12),'floor')
    box('BackWall',(.5,1.65,1.2),(6,.08,2.4),'floor')
    box('LeftWall',(-2.5,0,1.2),(.08,3.3,2.4),'floor')
    box('Table',(.73,0,.585),(1.00,.78,.10),'table')
    for i,(x,y) in enumerate([(0.28,-.32),(1.17,-.32),(.28,.32),(1.17,.32)]):
        box('TableLeg'+str(i),(x,y,.28),(.055,.055,.56),'table')
    # Two physical plate pieces meet at an actual narrow seam beside the marking.
    pc=np.array(cfg['plate_center']); sx,sy=cfg['plate_size']
    box('MarkedPlateBody',(pc[0],pc[1],pc[2]-.009),(sx,sy,.016),'steel')
    seam_x=pc[0]+sx/2+.003
    box('SecondPlate',(seam_x+.072,0,pc[2]-.009),(.14,sy,.016),'steel')
    mesh=UsdGeom.Mesh.Define(stage,'/World/Workshop/MarkingSurface')
    mesh.CreatePointsAttr([Gf.Vec3f(pc[0]-sx/2,-sy/2,pc[2]),Gf.Vec3f(pc[0]+sx/2,-sy/2,pc[2]),
                          Gf.Vec3f(pc[0]+sx/2,sy/2,pc[2]),Gf.Vec3f(pc[0]-sx/2,sy/2,pc[2])])
    mesh.CreateFaceVertexCountsAttr([4]);mesh.CreateFaceVertexIndicesAttr([0,1,2,3])
    mesh.CreateSubdivisionSchemeAttr('none')
    mesh.CreateNormalsAttr([Gf.Vec3f(0,0,1)]*4);mesh.SetNormalsInterpolation('vertex')
    uv=UsdGeom.PrimvarsAPI(mesh).CreatePrimvar('st',Sdf.ValueTypeNames.TexCoord2fArray,UsdGeom.Tokens.vertex)
    uv.Set([(0,0),(1,0),(1,1),(0,1)])
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(mats['mark'])
    # Presentation surroundings: inert equipment, rack stock, fixed curtain and floor boundary.
    box('PowerSupply',(-.7,.6,.33),(.45,.42,.66),'blue')
    box('PowerSupplyDisplay',(-.7,.383,.46),(.23,.015,.11),'dark')
    box('Curtain',(-.7,1.0,.9),(1.6,.025,1.6),'red')
    for i,x in enumerate([-1.52,.12]):box('CurtainPost'+str(i),(x,1.,.9),(.035,.035,1.8),'table')
    for i in range(4):box('Stock'+str(i),(1.8,.80,.18+i*.11),(.7,.13,.065),'steel')
    for i,x in enumerate([-.35,1.5]):box('FloorLine'+str(i),(x,-.2,.002),(.035,1.7,.003),'yellow')
    box('FloorLineFront',(.575,-1.05,.002),(1.885,.035,.003),'yellow')

    def look_quat(position,target):
        matrix=Gf.Matrix4d().SetLookAt(Gf.Vec3d(*position),Gf.Vec3d(*target),Gf.Vec3d(0,0,1)).GetInverse()
        return matrix.ExtractRotationQuat()
    def light(name,pos,target,intensity,width,height,color):
        l=UsdLux.RectLight.Define(stage,'/World/Lights/'+name)
        l.CreateWidthAttr(width);l.CreateHeightAttr(height);l.CreateIntensityAttr(intensity)
        l.CreateColorAttr(Gf.Vec3f(*color));l.CreateNormalizeAttr(False)
        l.AddTranslateOp().Set(Gf.Vec3d(*pos));l.AddOrientOp().Set(Gf.Quatf(look_quat(pos,target)))
        return l
    lc=cfg['worklight']
    lamp=light('FixedWorklight',lc['position'],lc['look_at'],lc['intensity'],lc['width'],lc['height'],lc['color'])
    housing=UsdGeom.Cube.Define(stage,str(lamp.GetPath())+'/Housing')
    housing.CreateSizeAttr(1)
    housing.AddTranslateOp().Set(Gf.Vec3d(0,0,.025))
    housing.AddScaleOp().Set(Gf.Vec3f(lc['width']+.035,lc['height']+.035,.04))
    UsdShade.MaterialBindingAPI.Apply(housing.GetPrim()).Bind(mats['dark'])
    box('LampStand',(lc['position'][0],lc['position'][1]+.09,.52),(.032,.032,1.04),'yellow')
    box('LampFoot',(lc['position'][0],lc['position'][1]+.09,.035),(.26,.18,.07),'dark')
    dome=UsdLux.DomeLight.Define(stage,'/World/Lights/NightAmbient')
    dome.CreateIntensityAttr(cfg['ambient_intensity']);dome.CreateColorAttr(Gf.Vec3f(.42,.51,.65))
    light('SoftShopFill',(.3,-1.0,2.5),(.7,0,.65),cfg.get('fill_intensity',1800),1.5,1.0,(.65,.78,1.0))

    print('WORKSHOP_CREATED',flush=True)
    base=cfg['robot']['base_position']
    if base[2]>0:
        box('RobotPedestal',(base[0],base[1],base[2]/2),(.32,.32,base[2]),'table')
    robot=setup_robot(world,stage,cfg)
    print('ROBOT_LOADED',flush=True)
    overview=UsdGeom.Camera.Define(stage,'/World/OverviewCamera')
    overview.AddTranslateOp().Set(Gf.Vec3d(*cfg['overview']['position']))
    overview.AddOrientOp().Set(Gf.Quatf(look_quat(cfg['overview']['position'],cfg['overview']['look_at'])))
    camera_paths={'wrist':robot.camera_prim_path,'overview':str(overview.GetPath())}
    sensors={}
    for name,path in camera_paths.items():
        cam=UsdGeom.Camera(stage.GetPrimAtPath(path))
        focal=cfg['overview'].get('focal_length_mm',cfg['camera']['focal_length_mm']) if name=='overview' else cfg['camera']['focal_length_mm']
        cam.CreateFocalLengthAttr(focal)
        cam.CreateHorizontalApertureAttr(cfg['camera']['horizontal_aperture_mm'])
        height,width=cfg['camera']['resolution_hw']
        cam.CreateVerticalApertureAttr(cfg['camera']['horizontal_aperture_mm']*height/width)
        cam.CreateClippingRangeAttr(Gf.Vec2f(.015,100))
        sensors[name]=CameraSensor(RtxCamera(path,tick_rate=cfg['camera']['tick_rate'],reset_xform_op_properties=False),
                                   resolution=tuple(cfg['camera']['resolution_hw']),annotators=['rgb'])
    if args.native_ros:
        app_utils.enable_extension('isaacsim.ros2.bridge');app.update()
        import omni.syntheticdata
        import omni.syntheticdata._syntheticdata as sd
        render_var=omni.syntheticdata.SyntheticData.convert_sensor_type_to_rendervar(sd.SensorType.Rgb.name)
        for name,sensor in sensors.items():
            sensor.attach_writer(render_var+'ROS2PublishImage',frameId='contextweld_'+name+'_camera',
                                 nodeNamespace='',queueSize=1,topicName='/contextweld/'+name+'/rgb')
    print('CAMERAS_CREATED',flush=True)
    world.reset()
    robot.initialize()
    faulthandler.cancel_dump_traceback_later()
    print('SCENE_READY',flush=True)
    stream_ready=False
    phase='initializing'
    rendered_steps=0
    def step(count):
        nonlocal rendered_steps
        for _ in range(count):
            if not running:break
            frame_started=time.monotonic()
            world.step(render=True)
            rendered_steps+=1
            if stream_ready and rendered_steps%cfg['presentation']['stream_every_steps']==0:
                capture(phase)
            if args.live:
                time.sleep(max(0,1/60-(time.monotonic()-frame_started)))
    step(cfg['render']['warmup_steps'])
    for name,sensor in sensors.items():
        first,info=sensor.get_data('rgb')
        print('SENSOR_WARMUP',name, None if first is None else list(first.shape),flush=True)
        if first is not None:
            Image.fromarray(first.numpy()[:,:,:3]).save(out/'frames'/('initial-'+name+'.png'))
    manifest={'schema_version':'isaac-scene-capture.v1','scenario_id':cfg['scenario_id'],
      'capture_mode':'pre_captured','presentation':'scheduled A/B joint motion, not recognition feedback',
      'created_at_utc':utc_now(),'git_commit':git_commit,'git_dirty':git_dirty,'simulator':'Isaac Sim 6.1','config_sha256':hashlib.sha256((out/'config.json').read_bytes()).hexdigest(),
      'source_hashes':source_hashes,'marking':marking_meta,'camera_paths':camera_paths,'frames':{},'execution_authorized':False,
      'fixed_settings':{p:settings.get(p) for p in ['/rtx/post/histogram/enabled','/rtx/post/tonemap/filmIso','/rtx/post/tonemap/cameraShutter','/rtx/post/tonemap/fNumber']}}
    sequence=0
    def capture(view,canonical=False):
        nonlocal sequence
        result={'sequence':sequence,'view':view,'captured_at_utc':utc_now(),'simulation_time':world.current_time,
                'capture_time_semantics':'host time reading latest RGB after rendered simulation steps',
                'native_sensor_frame_id':None,'recognition_feedback_enabled':False,
                'capture_mode':'pre_captured','presentation_mode':'scheduled_pose_loop' if args.live else 'saved_pair'}
        result.update(robot.snapshot())
        for name,sensor in sensors.items():
            data,info=sensor.get_data('rgb')
            if data is None:raise RuntimeError('Camera has no fresh RGB: '+name)
            rgb=data.numpy()
            if rgb.ndim!=3 or rgb.shape[2]<3:raise RuntimeError('Unexpected RGB shape '+str(rgb.shape))
            target=out/'stream'/f'{name}.png'
            tmp=target.with_suffix('.tmp.png');Image.fromarray(rgb[:,:,:3]).save(tmp);tmp.replace(target)
            result[name+'_image']=str(target.relative_to(out))
            result[name+'_sensor_info']={str(k):str(v) for k,v in info.items()} if isinstance(info,dict) else str(info)
            if canonical:
                target=out/'frames'/f'{view}-{name}.png'
                Image.fromarray(rgb[:,:,:3]).save(target)
                result[name+'_saved_image']=str(target.relative_to(out))
                result[name+'_image_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
        atomic_json(out/'stream/current.json',result)
        if canonical:
            atomic_json(out/'frames'/f'{view}-capture.json',result)
            manifest['frames'][view]=result
            atomic_json(out/'manifest.json',manifest)
        sequence+=1
        return result
    stream_ready=args.live
    for view in ['A','B']:
        phase='moving_to_'+view
        robot.move_to_view(view,step,cfg['presentation']['move_steps'])
        phase=view
        step(cfg['render']['settle_steps'])
        capture(view,canonical=True)
        print('CAPTURED '+view,flush=True)
    stage_text=stage.GetRootLayer().ExportToString()
    stage_text=stage_text.replace(str(out/'assets/marking.png'),'./assets/marking.png')
    (out/'scene.usda').write_text(stage_text)
    manifest['robot']=robot.metadata()
    manifest['stage']='scene.usda'
    manifest['stage_external_assets_required']=True
    manifest['completed_at_utc']=utc_now()
    atomic_json(out/'manifest.json',manifest)
    print('PAIR_COMPLETE '+str(out),flush=True)
    if args.live:
        from itertools import cycle
        for view in cycle(['A','B']):
            if not running:break
            phase='moving_to_'+view
            robot.move_to_view(view,step,cfg['presentation']['move_steps'])
            phase=view
            step(cfg['presentation']['hold_steps'])
    atomic_json(out/'stream/session.json',{'state':'stopped','stopped_at_utc':utc_now()})
    app.close()

if __name__=='__main__':
    main()
