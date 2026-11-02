"""Template-based OMR reader. Coordinates are normalized to the rectified page."""
import cv2, numpy as np

def enhance_document(image):
    if image is None: raise ValueError("Image could not be decoded")
    h,w = image.shape[:2]
    if max(h,w) > 2400:
        scale = 2400/max(h,w); image=cv2.resize(image, None, fx=scale, fy=scale)
    gray=cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # illumination normalization + adaptive thresholding
    background=cv2.GaussianBlur(gray,(0,0),25)
    normalized=cv2.divide(gray, background, scale=255)
    denoised=cv2.bilateralFilter(normalized, 7, 45, 45)
    return denoised

def order_points(pts):
    rect=np.zeros((4,2),dtype="float32")
    s=pts.sum(axis=1); d=np.diff(pts,axis=1)
    rect[0]=pts[np.argmin(s)]; rect[2]=pts[np.argmax(s)]
    rect[1]=pts[np.argmin(d)]; rect[3]=pts[np.argmax(d)]
    return rect

def rectify_page(image):
    proc=enhance_document(image)
    edges=cv2.Canny(proc, 50, 150)
    contours,_=cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    contours=sorted(contours,key=cv2.contourArea,reverse=True)[:15]
    quad=None
    for c in contours:
        peri=cv2.arcLength(c,True); approx=cv2.approxPolyDP(c,0.02*peri,True)
        if len(approx)==4 and cv2.contourArea(approx)>0.15*image.shape[0]*image.shape[1]:
            quad=approx.reshape(4,2).astype("float32"); break
    if quad is None: return image, 0.55, "page boundary not confidently detected; using full image"
    pts=order_points(quad); (tl,tr,br,bl)=pts
    width=max(int(np.linalg.norm(br-bl)),int(np.linalg.norm(tr-tl)))
    height=max(int(np.linalg.norm(tr-br)),int(np.linalg.norm(tl-bl)))
    dst=np.array([[0,0],[width-1,0],[width-1,height-1],[0,height-1]],dtype="float32")
    warped=cv2.warpPerspective(image,cv2.getPerspectiveTransform(pts,dst),(width,height))
    return warped, 0.95, "page boundary detected"

def read_bubbles(image, questions=100, options="ABCD", rows_per_column=25, threshold=0.22):
    """Default A4 template: two columns; each column has rows_per_column rows.
    Bubble centers are normalized coordinates and must match generated template."""
    page, page_conf, note=rectify_page(image)
    gray=enhance_document(page)
    h,w=gray.shape
    # template geometry: question rows start at 18% page height; two columns
    answers={}; confidences=[]; review=[]
    for q in range(questions):
        col=q//rows_per_column
        row=q%rows_per_column
        if col>1:
            review.append(q+1); answers[str(q+1)]="?"
            continue
        x0=(0.105 if col==0 else 0.555)*w
        y0=0.18*h + row*(0.72*h/max(rows_per_column-1,1))
        vals=[]
        for oi,opt in enumerate(options):
            cx=x0 + oi*0.065*w
            cy=y0
            radius=max(3,int(min(w,h)*0.009))
            mask=np.zeros_like(gray)
            cv2.circle(mask,(int(cx),int(cy)),radius,255,-1)
            roi=gray[mask>0]
            darkness=float(np.mean(255-roi)/255) if roi.size else 0
            vals.append(darkness)
        order=np.argsort(vals)[::-1]
        top=float(vals[order[0]]); second=float(vals[order[1]]) if len(vals)>1 else 0
        conf=max(0,min(1,(top-second)*2.5))
        confidences.append(conf)
        if top < threshold:
            answers[str(q+1)]=""
        elif top-second < 0.045:
            answers[str(q+1)]="MULTI"; review.append(q+1)
        else:
            answers[str(q+1)]=options[int(order[0])]
            if conf < 0.25: review.append(q+1)
    mean=float(np.mean(confidences)) if confidences else 0
    return {"answers":answers,"confidence":round(mean*page_conf,3),"review_questions":review,
            "page_confidence":page_conf,"note":note,"image":page}

def evaluate(answers, key, positive=4, negative=1):
    correct=wrong=blank=0; score=0.0
    for q, right in key.items():
        got=str(answers.get(str(q),"")).upper()
        if got in ("", "?", "MULTI"): blank+=1
        elif got==str(right).upper(): correct+=1; score+=positive
        else: wrong+=1; score-=negative
    return {"score":round(score,2),"correct":correct,"wrong":wrong,"blank":blank}
