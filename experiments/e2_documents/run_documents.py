"""고정 자료집으로 생성을 비교하고 채점 정답을 읽지 않은 채 모든 입력·출력을 보존한다."""

from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import time
import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer
from retrieve import retrieve

ROOT=Path(__file__).resolve().parent
SYSTEM='Answer the question briefly in English. Use supplied reference notes when relevant and cite their IDs. If the answer cannot be determined, answer UNKNOWN. Never invent project-specific settings, approvals or work-order status. Return one JSON object with keys "answer" (string) and "sources" (array of note IDs). Do not add other text.'


def main() -> None:
    run_id=sys.argv[1]
    if not run_id.replace('-','').replace('_','').isalnum(): raise ValueError('잘못된 실행 ID')
    out=ROOT/'runs'/run_id;out.mkdir(parents=True,exist_ok=False)
    corpus=json.loads((ROOT/'corpus.json').read_text());questions=json.loads((ROOT/'questions.json').read_text())
    model_path=ROOT/'inputs/model'
    torch.set_num_threads(4);torch.manual_seed(0)
    tokenizer=AutoTokenizer.from_pretrained(model_path,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(model_path,local_files_only=True,trust_remote_code=False,torch_dtype=torch.float32).eval()
    metadata={'started_at':datetime.now().astimezone().isoformat(),'model':'Qwen/Qwen2.5-0.5B-Instruct','revision':'7ae557604adf67be50417f59c2c2f167def9a775','torch':torch.__version__,'transformers':transformers.__version__,'device':'cpu','dtype':'float32','threads':4,'do_sample':False,'max_new_tokens':128,
        'sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in ['corpus.json','questions.json','PROTOCOL.md','run_documents.py','retrieve.py']}}
    (out/'environment.json').write_text(json.dumps(metadata,indent=2)+'\n')
    with (out/'outputs.jsonl').open('w') as f:
        for condition in ['none','full','bm25']:
            for question in questions:
                ranking=retrieve(question['question'],corpus) if condition=='bm25' else []
                ids=[r['id'] for r in ranking] if condition=='bm25' else [d['id'] for d in corpus] if condition=='full' else []
                selected=[next(d for d in corpus if d['id']==i) for i in ids]
                notes='\n'.join(f"[{d['id']}] {d['title']}: {d['text']}" for d in selected) or '(No reference notes supplied.)'
                messages=[{'role':'system','content':SYSTEM},{'role':'user','content':f"Reference notes:\n{notes}\n\nQuestion: {question['question']}"}]
                rendered=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
                inputs=tokenizer(rendered,return_tensors='pt');start=time.perf_counter()
                with torch.inference_mode():
                    output=model.generate(**inputs,max_new_tokens=128,do_sample=False,pad_token_id=tokenizer.eos_token_id)
                elapsed=time.perf_counter()-start;generated=output[0][inputs['input_ids'].shape[-1]:]
                text=tokenizer.decode(generated,skip_special_tokens=True)
                row={'condition':condition,'question_id':question['id'],'question':question['question'],'messages':messages,'retrieved':ranking,'provided_ids':ids,'input_tokens':inputs['input_ids'].shape[-1],'output_tokens':len(generated),'seconds':elapsed,'output':text,'reached_limit':len(generated)==128}
                f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
                print(condition,question['id'],len(generated),round(elapsed,2),flush=True)


if __name__=='__main__':main()
