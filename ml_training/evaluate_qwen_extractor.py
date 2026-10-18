"""Small held-out benchmark for adapter JSON, field/value exact match and evidence support."""
from __future__ import annotations
import argparse, json, os, re
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

SYSTEM = '''You are a medical-document information extraction component for a personal-record organizer, not a clinician. Extract only facts explicitly stated in the supplied OCR text. Never diagnose, interpret whether a result is normal, recommend treatment, or infer an unclear medicine, dose, unit, or date. Return only valid JSON: {"candidates":[{"field":string,"value":string,"unit":string,"source_page":integer,"source_line":integer,"source_excerpt":string}]}. Each source_excerpt must be copied verbatim from the page and contain the exact value. Omit unclear or unsupported facts. No confidence scores.'''

def parse_json(text):
    start,end=text.find('{'),text.rfind('}')
    if start < 0 or end <= start:
        raise ValueError("No JSON object in model output")
    return json.loads(text[start:end+1])

def norm(v): return re.sub(r'\s+',' ',str(v or '').casefold()).strip()

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',default=os.getenv('QWEN_BASE_MODEL_ID','Qwen/Qwen3-4B'));p.add_argument('--adapter',default='ml_training/output/healthsync-qwen3-extractor');p.add_argument('--data',default='ml_training/data/validation.jsonl');p.add_argument('--output',default='ml_training/output/evaluation.json');a=p.parse_args()
    device='cuda' if torch.cuda.is_available() else ('mps' if getattr(torch.backends,'mps',None) and torch.backends.mps.is_available() else 'cpu')
    dtype=torch.float16 if device in {'cuda','mps'} else torch.float32
    tok=AutoTokenizer.from_pretrained(a.model);base=AutoModelForCausalLM.from_pretrained(a.model,torch_dtype=dtype,low_cpu_mem_usage=True);model=PeftModel.from_pretrained(base,a.adapter);model.to(device);model.eval()
    total_gold=total_pred=exact=valid_json=source_supported=pred_count=0;rows=[]
    for line in Path(a.data).read_text().splitlines():
        if not line.strip():continue
        sample=json.loads(line); messages=sample['messages'];user=messages[-2]['content'];gold=json.loads(messages[-1]['content']).get('candidates',[]);prompt_messages=[m for m in messages if m['role']!='assistant']
        
        try: prompt=tok.apply_chat_template(prompt_messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
        except TypeError: prompt=tok.apply_chat_template(prompt_messages,tokenize=False,add_generation_prompt=True)
        inputs=tok(prompt,return_tensors='pt');inputs={k:v.to(device) for k,v in inputs.items()}
        with torch.inference_mode():out=model.generate(**inputs,max_new_tokens=1800,do_sample=False)
        text=tok.decode(out[0][inputs['input_ids'].shape[1]:],skip_special_tokens=True)
        try:pred=parse_json(text).get('candidates',[]);valid_json+=1
        except Exception:pred=[]
        gold_pairs={(norm(x.get('field')),norm(x.get('value'))) for x in gold};pred_pairs={(norm(x.get('field')),norm(x.get('value'))) for x in pred}
        total_gold+=len(gold_pairs);total_pred+=len(pred_pairs);exact+=len(gold_pairs & pred_pairs)
        for item in pred:
            pred_count+=1
            evidence=norm(item.get('source_excerpt'))
            if evidence and evidence in norm(user) and norm(item.get('value')) in evidence:source_supported+=1
        rows.append({'gold_fields':len(gold),'predicted_fields':len(pred),'exact_field_value_matches':len(gold_pairs & pred_pairs),'raw_output':text[:6000]})
    precision=exact/total_pred if total_pred else 0;recall=exact/total_gold if total_gold else 0
    result={'model':a.model,'adapter':str(Path(a.adapter).resolve()),'samples':len(rows),'valid_json_rate':valid_json/max(1,len(rows)),'field_value_precision':precision,'field_value_recall':recall,'field_value_f1':(2*precision*recall/(precision+recall)) if precision+recall else 0,'source_support_rate':source_supported/max(1,pred_count),'rows':rows,'caution':'Small validation sets are not reliable clinical validation. Replace examples with a large reviewed held-out dataset.'}
    Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2));print(f"Full report: {Path(a.output).resolve()}")
if __name__=='__main__':main()
