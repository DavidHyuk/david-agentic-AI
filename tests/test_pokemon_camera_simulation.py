# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Verify pixel/area constraints, deterministic damage, label isolation and resume."""
import json
from pathlib import Path

import pytest
from PIL import Image

import pokemon_card_benchmark as b
import pokemon_benchmark_dataset as d

RECT = [[0,0],[1,0],[1,1],[0,1]]


@pytest.mark.parametrize('count',[1,4,26,30])
@pytest.mark.parametrize('proportion',[0,1])
def test_wilson_boundary_does_not_make_negative_plot_errors(count,proportion):
    lower,upper=b.wilson(count*proportion,count)
    assert 0 <= lower <= proportion <= upper <= 1
    if proportion == 0:
        assert lower == 0
    else:
        assert upper == 1


def test_selection_covers_types_and_excludes_trainers_and_dual_types():
    cards = [{'id':str(i), 'name':t+str(i), 'supertype':'Pokémon', 'hp':'100',
              'types':[t], 'number':str(i+1)} for i,t in enumerate(list(d.TYPES)*3)]
    invalid = [dict(cards[0], name='trainer', supertype='Trainer'),
               dict(cards[0], name='dual', types=['Water','Metal'])]
    selected = d.select_cards({'swsh1':invalid+cards})
    assert len(selected) == 26
    assert {c['types'][0] for _,c in selected} == set(d.TYPES)
    assert len({c['name'] for _,c in selected}) == 26
    assert selected == d.select_cards({'swsh1':invalid+cards})


def test_source_numbering_retains_printed_zeros_and_set_total():
    assert d.printed_number('swsh1',{'number':'1'},{'printedTotal':202}) == '001/202'
    assert d.printed_number('sm12',{'number':'143'},{'printedTotal':236}) == '143/236'
    with pytest.raises(ValueError,match='Unreviewed'):
        d.printed_number('unknown',{'number':'1'},{'printedTotal':100})


@pytest.mark.parametrize('occupancy',[.3,.5,.8])
def test_area_is_not_a_linear_fraction_and_never_upscales(occupancy):
    geometry = b.simulation_geometry((734,1024),RECT,2_000_000,occupancy)
    assert geometry['card_scale'] <= 1
    assert geometry['capped'] is (occupancy > .3)
    assert abs(geometry['actual_occupancy']-occupancy) < .003
    assert geometry['card_size'][0] <= 734 and geometry['card_size'][1] <= 1024
    assert geometry['frame'][0]*geometry['frame'][1] <= 2_000_000


@pytest.mark.parametrize('polygon', [RECT[:-1], [[0,0]]*4, [[0,0],[1,0],[2,1],[0,1]]])
def test_invalid_card_geometry_is_not_silently_accepted(polygon):
    with pytest.raises(ValueError):
        b.simulation_geometry((700,1000),polygon,300_000,.5)


def test_no_upscale_preserves_clean_native_pixel_bytes():
    image = Image.effect_noise((73,102),80).convert('RGB')
    before = image.tobytes()
    result,geometry = b.make_simulated_image(image,RECT,2_000_000,None,'clean',42)
    assert result.size == image.size and result.tobytes() == before
    assert image.tobytes() == before and geometry['capped']


@pytest.mark.parametrize('condition',['blur','noise','jpeg','combined'])
def test_damage_is_reproducible_and_source_is_unchanged(condition):
    image = Image.effect_noise((73,102),80).convert('RGB'); before=image.tobytes()
    first = b.corrupt_image(image,condition,42)
    second = b.corrupt_image(image,condition,42)
    assert first.tobytes() == second.tobytes() != before
    assert image.tobytes() == before
    assert first.mode == 'RGB' and first.size == image.size


def test_common_noise_seed_and_different_seeds():
    image = Image.new('RGB',(100,100),(127,127,127))
    assert b.corrupt_image(image,'noise',1).tobytes() != b.corrupt_image(image,'noise',2).tobytes()
    # No source detail is fabricated under a clean condition.
    assert b.corrupt_image(image,'clean',1).tobytes() == image.tobytes()


def test_plan_preserves_two_new_baselines_and_has_960_requests_for_30_cards():
    plan=b.simulation_plan(['0.3MP','2MP'],[.3,.5,.8],list(b.CORRUPTIONS))
    assert len(plan)*30 == 960
    assert {p['resolution'] for p in plan if p['requested_occupancy'] is None} == {'0.3MP','2MP'}
    with pytest.raises(ValueError,match='Duplicate'):
        b.simulation_plan(['0.3MP'],[.3,.3],['clean'])


def make_manifest(tmp_path):
    root=tmp_path/'workspace'; root.mkdir()
    image=root/'card.png';Image.new('RGB',(300,400),'red').save(image)
    card={'filename':'card.png','image_path':str(image),'source_sha256':b.sha256(image),
          'source_group':'smartphone_ko','language':'ko','card_polygon':RECT,
          'ground_truth':{'pokemon_name':'피카츄','pokemon_type':'Lightning','hp':'60','card_number':'025/100'}}
    manifest=root/'manifest.json';manifest.write_text(json.dumps({'cards':[card]}))
    return root,manifest,image


def simulation_args(root,manifest):
    return ['--root',str(root),'simulate','--manifest',str(manifest),'--resolutions','0.3MP',
            '--occupancies','.3','--corruptions','clean','jpeg','--gap','0',
            '--min-available-gib','0','--min-free-gib','0']


def test_prepare_only_never_contacts_model_and_preserves_source(tmp_path,monkeypatch):
    root,manifest,image=make_manifest(tmp_path);before=image.read_bytes()
    monkeypatch.setattr(b,'inspect_server',lambda *a:pytest.fail('No server inspection for preparation'))
    monkeypatch.setattr(b,'infer',lambda *a,**k:pytest.fail('No preparation inference'))
    assert b.main(simulation_args(root,manifest)+['--prepare-only']) == 0
    run=next((root/'runs').iterdir())
    assert json.loads((run/'metadata.json').read_text())['status'] == 'prepared'
    assert (run/'results.jsonl').read_text() == ''
    assert len(list((run/'images').rglob('*.png'))) == 3
    assert image.read_bytes() == before


def test_resume_skips_durable_rows_and_keeps_truth_out_of_prompt(tmp_path,monkeypatch):
    root,manifest,image=make_manifest(tmp_path);before=image.read_bytes();calls=[]
    monkeypatch.setattr(b,'inspect_server',lambda *a:{})
    monkeypatch.setattr(b,'wait_for_idle',lambda *a:None)
    monkeypatch.setattr(b,'check_memory',lambda *a:{})
    monkeypatch.setattr(b,'make_plots',lambda *a:None)
    monkeypatch.setattr(b,'make_simulation_plots',lambda *a:None)
    def infer(*args,**kwargs):
        calls.append(str(args[3]))
        if len(calls)==2:
            raise RuntimeError('Simulated interruption after one durable result')
        assert 'ground_truth' not in kwargs and '피카츄' not in b.PROMPT
        return {'pokemon_name':'피카츄','pokemon_type':'Lightning','hp':'60','card_number':'025/100',
                'api_error':False,'parse_error':False,'image_error':False,'error':'',
                'http_status':200,'latency_seconds':1.,'raw_model_response':'actual response',
                'raw_api_response':'{}','finish_reason':'stop'}
    monkeypatch.setattr(b,'infer',infer)
    args=simulation_args(root,manifest)
    assert b.main(args) == 1
    run=next((root/'runs').iterdir());raw=(run/'results.jsonl').read_bytes()
    assert len(raw.splitlines()) == 1
    assert json.loads((run/'metadata.json').read_text())['status']=='interrupted'
    assert b.main(args+['--resume-run',str(run)]) == 0
    assert (run/'results.jsonl').read_bytes().startswith(raw)
    assert len((run/'results.jsonl').read_text().splitlines()) == 3
    assert len(calls)==4 and image.read_bytes()==before
    assert json.loads((run/'metadata.json').read_text())['status']=='completed'
    rows=json.loads((run/'simulation_summary.json').read_text())
    assert all(r['pokemon_name_accuracy']==1 for r in rows)
    # A simulation report keeps its 30-card truth instead of unrelated root labels.
    b.write_csv(root/'pokebot_ground_truth.csv',
                [{'filename':'card.png','pokemon_name':'wrong root label'}],('filename',*b.FIELDS))
    (run/'simulation_summary.json').unlink()
    assert b.main(['--root',str(root),'report',str(run)]) == 0
    rows=json.loads((run/'simulation_summary.json').read_text())
    assert all(r['pokemon_name_accuracy']==1 for r in rows)
    assert len(calls)==4 and image.read_bytes()==before


def test_cached_dataset_checks_source_hash_before_reusing_labels(tmp_path):
    root,manifest,image=make_manifest(tmp_path)
    out=tmp_path/'dataset';out.mkdir();(out/'manifest.json').write_bytes(manifest.read_bytes())
    assert d.build_dataset(root,out)==out/'manifest.json'
    image.write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):
        d.build_dataset(root,out)


@pytest.mark.parametrize('difference',[None,'image','simulation','missing'])
def test_fine_tuning_comparison_checks_simulation_pixels_config_and_coverage(tmp_path,difference):
    directories=[tmp_path/'before',tmp_path/'after']
    for index,directory in enumerate(directories):
        directory.mkdir()
        config={'seed':43 if index and difference=='simulation' else 42}
        b.write_json(directory/'metadata.json',{'status':'completed','model':str(index),
            'evaluation_mode':'synthetic_camera_stress','simulation':config,
            'inputs':[{'filename':'card.png','source_sha256':'source'}],
            'resolutions':['0.3MP'],'prompt':'same prompt','parameters':{'temperature':0},
            'preprocessing':'same pixels'})
        rows=[{'filename':'card.png','resolution':'0.3MP','source_sha256':'source',
               'image_sha256':'different' if index and difference=='image' else 'pixels'}]
        b.write_json(directory/'results.json',[] if index and difference=='missing' else rows)
        b.write_json(directory/'ground_truth.snapshot.json',{'card.png':{'hp':'60'}})
        summary={'resolution':'0.3MP','average_latency_seconds':1.,'unknown_response_rate':0.,
                 **{f+'_accuracy':1. for f in b.FIELDS}}
        b.write_json(directory/'summary.json',{'resolutions':[summary]})
    output=tmp_path/'comparison'
    if difference:
        with pytest.raises(ValueError,match='Cannot make a controlled comparison'):
            b.compare_runs(*directories,output)
    else:
        b.compare_runs(*directories,output)
    result=json.loads((output/'comparison.json').read_text())
    assert result['comparable'] is (difference is None)
