from pathlib import Path
import sys,tempfile
sys.path.insert(0,str(Path(__file__).parent/'src'))
import pipeline_context as ctx
with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as stage:
    ctx.configure(Path(sys.argv[1]),Path(stage))
    import soulstruct_local_config
    sys.modules['soulstruct.config']=soulstruct_local_config
    from generate_navigation_maps import msb,Binder
    from probe_location_names import place_names
    assert msb(ctx.GAME_DATA/'map/mapstudio/m21_00_00_00.msb.dcx')
    names,entry,path=place_names();assert names and path.exists()
    assert not (Path(__file__).parent/'soulstruct_config.json').exists()
print('ATLAS_READONLY_SOULSTRUCT_ADAPTER_PASS')
