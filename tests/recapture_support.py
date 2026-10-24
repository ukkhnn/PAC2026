"""모델을 호출하지 않는 재촬영→문서 연결용 관측 fixture."""
from copy import deepcopy
from unittest.mock import patch
from test_dashboard_recapture import _make_bundle
from test_recapture_loop import FixtureObserver


class BindingObserver(FixtureObserver):
    part = 'BISB30N-15'
    joint = 'J01'
    duplicate = False
    detached_joint = False

    def observe(self, bundle, frame):
        # 기존 fixture의 사건·판단 생성기를 쓰되 저장 직전 관측과 관계를 구체화한다.
        original = bundle.result

        def result(stage, fid, fields, **kwargs):
            fields = deepcopy(fields)
            if stage == 'observation':
                fields['text_observations'][0]['raw_text'] = self.part
                fields['visual_objects'][0].update(kind='joint', visible_text=self.joint,
                                                   description='fixture plate joint')
                if self.detached_joint:
                    fields['visual_objects'][0]['visible_text'] = None
                    fields['text_observations'].append({'observation_id': fid + '-unrelated', 'raw_text': self.joint})
            if stage == 'relation' and self.duplicate:
                other = deepcopy(fields['relations'][0])
                other['relation_id'] += '-duplicate'
                fields['relations'].append(other)
            if stage == 'capture_assessment' and self.duplicate:
                fields['field_checks'][1]['relation_ids'].append(fid + '-relation-1-duplicate')
            return original(stage, fid, fields, **kwargs)

        with patch.object(bundle, 'result', side_effect=result):
            return super().observe(bundle, frame)


def make_bundle(root, states=('retry', 'observed'), *, part='BISB30N-15', joint='J01',
                duplicate=False, detached_joint=False, fail=False):
    class Observer(BindingObserver):
        pass
    Observer.part, Observer.joint = part, joint
    Observer.duplicate, Observer.detached_joint = duplicate, detached_joint
    with patch('test_dashboard_recapture.FixtureObserver', Observer):
        return _make_bundle(root, list(states), 'binding-fixture', fail=fail)
