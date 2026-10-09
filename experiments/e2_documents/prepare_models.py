"""공개 모델의 고정 파일만 내려받고 스트리밍 해시를 기록한다."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parent
MODELS={
    'small':('Qwen/Qwen2.5-0.5B-Instruct','7ae557604adf67be50417f59c2c2f167def9a775','model'),
    'large':('Qwen/Qwen2.5-1.5B-Instruct','989aa7980e4cf806f80c7fef2b1adb7bc71aa306','model-large'),
}
FILES=['README.md','LICENSE','config.json','generation_config.json','merges.txt','model.safetensors','tokenizer.json','tokenizer_config.json','vocab.json']


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as source:
        while block:=source.read(1024*1024):h.update(block)
    return h.hexdigest()


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument('size',choices=MODELS);args=parser.parse_args()
    repo,revision,directory=MODELS[args.size];root=ROOT/'inputs'/directory;root.mkdir(parents=True,exist_ok=True)
    info={'repo':repo,'revision':revision,'license':'Apache-2.0','retrieved_date':datetime.now().astimezone().date().isoformat(),'files':{}}
    for name in FILES:
        path=root/name;url=f'https://huggingface.co/{repo}/resolve/{revision}/{name}'
        if not path.exists():
            temporary=root/(name+'.part')
            with urlopen(url,timeout=120) as source,temporary.open('wb') as target:
                while block:=source.read(1024*1024):target.write(block)
            temporary.rename(path)
        info['files'][name]={'bytes':path.stat().st_size,'sha256':digest(path),'url':url}
        print(name,path.stat().st_size,flush=True)
    dest=ROOT/f'model-{args.size}-manifest.json'
    if dest.exists():
        old=json.loads(dest.read_text())
        if old['files']!=info['files']:raise ValueError('기존 모델 manifest와 다릅니다.')
    else:dest.write_text(json.dumps(info,indent=2)+'\n')


if __name__=='__main__':main()
