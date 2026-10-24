"""과거 통합 묶음의 알려진 목록 누락을 새 사본에서만 보충한다."""
from pathlib import Path
import shutil
from contextweld.recognition import safe_path, sha256, write_json
from contextweld.workflow import read_json
from contextweld.weld_pipeline import verify_pipeline

KNOWN_NESTED = {'inputs/document-run/checksums.json',
                'inputs/document-run/inputs/recognition/checksums.json'}


def prepare_weld_copy(source: Path, output: Path, report_path: Path) -> dict:
    source, output, report_path = source.resolve(), output.resolve(), report_path.resolve()
    if (source == output or source in output.parents or output in source.parents
            or report_path == source or source in report_path.parents
            or report_path == output or output in report_path.parents):
        raise ValueError('원본·사본·보충 기록 경로는 분리해야 함')
    if output.exists() or report_path.exists():
        raise FileExistsError('새 사본·기록 경로 필요')
    if any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('symlink가 있는 묶음은 보충하지 않음')
    sums = read_json(source/'checksums.json')
    for ref, digest in sums.items():
        if sha256(safe_path(source, ref)) != digest:
            raise ValueError('원본 기록 해시 불일치: '+ref)
    actual = {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}
    extra = actual - set(sums) - {'checksums.json'}
    allowed = set(KNOWN_NESTED)
    if (source/'inputs/capture/capture.json').exists():
        for frame in read_json(source/'inputs/capture/capture.json')['frames']:
            ref = 'frames/'+frame['frame_id'].removeprefix('frame-')+'-wrist.png'
            if ref in extra:
                if sha256(safe_path(source, ref)) != frame['image_sha256']:
                    raise ValueError('촬영 기록과 보충 이미지 해시 불일치')
                allowed.add(ref)
    if extra - allowed:
        raise ValueError('알려진 목록 누락 외 추가 파일: '+', '.join(sorted(extra-allowed)))
    for ref in extra & KNOWN_NESTED:
        nested = read_json(source/ref)
        for relative, digest in nested.items():
            if sha256(safe_path((source/ref).parent,relative)) != digest:
                raise ValueError('중첩 해시 목록 불일치')
    before = {ref:sha256(source/ref) for ref in actual}
    shutil.copytree(source, output)
    additions = {ref: sha256(output/ref) for ref in sorted(extra)}
    write_json(output/'checksums.json', {**sums, **additions})
    verification = verify_pipeline(output)
    if before != {ref:sha256(source/ref) for ref in actual}:
        raise ValueError('작업 중 원본 변경 감지')
    report = {'operation':'inventory_supplement_in_new_copy', 'originals_unchanged':True,
              'source':str(source), 'output':str(output),
              'source_checksums_sha256':before['checksums.json'],
              'copy_checksums_sha256':sha256(output/'checksums.json'),
              'added_entries':additions, 'verification':verification,
              'note':'누락 항목은 현재 사본 파일의 해시로 보충했다. 생성 당시 목록에 있었다는 뜻이 아니다.'}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(report_path,report)
    return report
