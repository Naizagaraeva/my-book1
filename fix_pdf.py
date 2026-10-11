from pypdf import PdfReader, PdfWriter, Transformation
from pathlib import Path
import fitz
root=Path('/mnt/data/sitefix'); src=Path('/mnt/data/cpp_machine_oriented_site/assets/book.pdf'); out=root/'assets/book.pdf'; tmp=root/'assets/book_shift_tmp.pdf'
r=PdfReader(str(src)); w=PdfWriter(); shifted=[]; fd=fitz.open(str(src))
for idx,page in enumerate(r.pages):
 n=idx+1; delta=0
 if n>=5:
  fp=fd[idx]; spans=[]
  for b in fp.get_text('dict')['blocks']:
   for l in b.get('lines',[]):
    for s in l.get('spans',[]):
     if s.get('text','').strip() and s['bbox'][1]<790: spans.append(s)
  if spans:
   top=min(s['bbox'][1] for s in spans); bottom=max(s['bbox'][3] for s in spans)
   if top>100:
    delta=min(top-58,max(0,bottom-650))
    if delta>0:
     # PDF's transformation matrix uses bottom-left coordinates; negative ty moves up on the rendered page.
     page.add_transformation(Transformation().translate(tx=0,ty=-delta)); shifted.append((n,round(delta,1)))
 w.add_page(page)
with open(tmp,'wb') as f:w.write(f)
fd.close(); d=fitz.open(str(tmp))
for n,delta in shifted:
 p=d[n-1]
 p.draw_rect(fitz.Rect(0,790,p.rect.width,p.rect.height),color=None,fill=(1,1,1),overlay=True)
 label=str(n); fs=9; tw=fitz.get_text_length(label,fontname='Times-Roman',fontsize=fs)
 p.insert_text(fitz.Point((p.rect.width-tw)/2,821),label,fontname='Times-Roman',fontsize=fs,color=(0,0,0),overlay=True)
d.save(str(out),garbage=4,deflate=True);d.close();tmp.unlink(missing_ok=True)
print('shifted',shifted)
