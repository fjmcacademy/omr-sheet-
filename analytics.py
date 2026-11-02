from collections import defaultdict
def exam_analytics(results, question_count):
    n=len(results)
    if not n: return {"attempts":0,"average":0,"highest":0,"lowest":0,"question_stats":[]}
    scores=[r.score for r in results]
    stats=[]
    for q in range(1,question_count+1):
        vals=[str((r.answers or {}).get(str(q),"")).upper() for r in results]
        attempted=sum(v not in ("","?","MULTI") for v in vals)
        stats.append({"question":q,"attempted":attempted,"blank":n-attempted})
    return {"attempts":n,"average":round(sum(scores)/n,2),"highest":max(scores),"lowest":min(scores),
            "question_stats":stats}
