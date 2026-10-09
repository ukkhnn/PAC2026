"""작은 자료집에서 정답 비참조 BM25 기준선을 계산한다."""

from collections import Counter
import math
import re

STOP = set('a an the is are was were be been in on of to for and or with by what where which does do under from our it its at as this that currently'.split())


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r'[a-z0-9]+',text.lower()) if t not in STOP]


def retrieve(query: str, corpus: list[dict], k: int = 2) -> list[dict]:
    documents=[tokens(d['title']+' '+d['text']) for d in corpus]
    mean=sum(map(len,documents))/len(documents)
    counts=[Counter(d) for d in documents]; ranked=[]
    for doc,tf in zip(corpus,counts):
        score=0.0
        for token in set(tokens(query)):
            freq=tf[token]
            if not freq: continue
            df=sum(token in c for c in counts)
            idf=math.log(1+(len(counts)-df+.5)/(df+.5))
            score+=idf*freq*2.5/(freq+1.5*(1-.75+.75*sum(tf.values())/mean))
        if score>0: ranked.append({'id':doc['id'],'score':score})
    return sorted(ranked,key=lambda x:(-x['score'],x['id']))[:k]
