from pathlib import Path
import json, re, zipfile
import fitz
from pypdf import PdfReader, PdfWriter, Transformation

ROOT=Path('/mnt/data/sitefix')
SOURCE=Path('/mnt/data/cpp_machine_oriented_site/assets/book.pdf')
PDF=ROOT/'assets/book.pdf'
PREP=ROOT/'assets/book_footer_clean.pdf'
SHIFTED=ROOT/'assets/book_shifted_tmp.pdf'

# 1) Start from the unmodified base PDF. Remove only the old printed footer number
# from pages 5 onward so it can be placed correctly after moving the page content.
source_doc=fitz.open(SOURCE)
page_deltas={}
for i,page in enumerate(source_doc):
    pno=i+1
    if pno < 5:
        continue
    spans=[]
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            for span in line.get('spans',[]):
                text=span.get('text','').strip()
                y0=span['bbox'][1]
                if not text or y0 >= 790:
                    continue
                if text.isdigit() and y0 < 90 and len(text) <= 3:
                    continue
                spans.append(span)
    if spans:
        top=min(s['bbox'][1] for s in spans)
        # Target a consistent 50-point top margin on pages that start too low.
        if top > 60:
            page_deltas[pno]=round(top-50,2)
    # The original physical page number is centered in this narrow footer zone.
    # Redact it before transforming so no duplicate number remains halfway up.
    footer=fitz.Rect(page.rect.width/2-22, 802, page.rect.width/2+22, 833)
    page.add_redact_annot(footer, fill=(1,1,1))
    page.apply_redactions(images=0, graphics=0)
source_doc.save(PREP,garbage=4,deflate=True)
source_doc.close()

# 2) Translate all content on pages that have excessive top whitespace.
reader=PdfReader(str(PREP)); writer=PdfWriter()
for i,page in enumerate(reader.pages):
    pno=i+1
    delta=page_deltas.get(pno,0)
    if delta:
        # Positive ty moves content upward on the rendered page.
        page.add_transformation(Transformation().translate(tx=0,ty=delta))
    writer.add_page(page)
with open(SHIFTED,'wb') as f:
    writer.write(f)

# 3) Restore clean bottom-center physical page numbers and add active links to every
# visible row in the contents page (PDF page 4). First three pages stay untouched.
doc=fitz.open(SHIFTED)
for pno in page_deltas:
    page=doc[pno-1]
    label=str(pno)
    fs=9
    width=fitz.get_text_length(label,fontname='Times-Roman',fontsize=fs)
    page.insert_text(fitz.Point((page.rect.width-width)/2,821),label,fontname='Times-Roman',fontsize=fs,color=(0,0,0),overlay=True)

contents=ROOT/'contents-data.js'
js_text=contents.read_text(encoding='utf-8')
match=re.search(r'window\.BOOK_CONTENTS\s*=\s*(\[.*?\]);',js_text,re.S)
if not match:
    raise RuntimeError('Could not parse contents-data.js')
items=json.loads(match.group(1))
toc=doc[3]
for link in list(toc.get_links()):
    toc.delete_link(link)

def norm(s):
    s=s.replace('С++','C++').replace('Си++','C++')
    return re.sub(r'\s+',' ',s).strip().casefold()
lines=[]
for block in toc.get_text('dict')['blocks']:
    for line in block.get('lines',[]):
        text=''.join(span['text'] for span in line.get('spans',[])).strip()
        if text:
            lines.append((text,fitz.Rect(line['bbox'])))
used=set(); added=[]; skipped=[]
for item in items:
    title=item['title'].strip()
    if item['page'] <= 2 or title in ('Мұқаба','Титулдық бет','Мазмұны','Қосымша бөлімдер'):
        continue
    target=norm(title)
    found=None
    for idx,(line_text,rect) in enumerate(lines):
        if idx in used:
            continue
        line_norm=norm(line_text)
        if line_norm == target or line_norm.startswith(target+' ') or line_norm.startswith(target+' ·') or line_norm.startswith(target+'...'):
            # Keep the section heading distinct from the detailed 100-question row.
            if target == norm('Тест тапсырмалары') and line_norm.startswith(norm('Тест тапсырмалары — 100 сұрақ')):
                continue
            found=(idx,rect,line_text)
            break
    if not found:
        skipped.append(title)
        continue
    idx,rect,line_text=found
    used.add(idx)
    link_rect=fitz.Rect(max(25,rect.x0-4),max(20,rect.y0-1),min(toc.rect.width-20,rect.x1+5),min(790,rect.y1+1))
    toc.insert_link({'kind':fitz.LINK_GOTO,'from':link_rect,'page':int(item['page'])-1,'to':fitz.Point(0,0)})
    added.append((title,int(item['page'])))

final_temp=ROOT/'assets/book_final_tmp.pdf'
doc.save(final_temp,garbage=4,deflate=True)
doc.close()
final_temp.replace(PDF)
PREP.unlink(missing_ok=True); SHIFTED.unlink(missing_ok=True)

# 4) Rebuild the deployable archive.
zip_path=Path('/mnt/data/cpp_machine_oriented_ebook_github.zip')
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for f in sorted(ROOT.rglob('*')):
        if f.is_file() and f.name not in {'fix_site.py','fix_pdf.py','apply_two_fixes.py'}:
            z.write(f,f.relative_to(ROOT).as_posix())

# Validation and preview renders.
check=fitz.open(PDF)
print('pages:',len(check))
print('pages moved up:',len(page_deltas),sorted(page_deltas.items()))
print('contents links:',len(check[3].get_links()),'added:',len(added),'skipped:',skipped)
print('page 105 top after fix:',round(min(s['bbox'][1] for b in check[104].get_text('dict')['blocks'] for l in b.get('lines',[]) for s in l.get('spans',[]) if s.get('text','').strip() and s['bbox'][1]<790),1))
print('sample link targets:',[x['page']+1 for x in check[3].get_links()[:10]])
check[104].get_pixmap(matrix=fitz.Matrix(1,1),alpha=False).save('/mnt/data/final_page105.png')
check[3].get_pixmap(matrix=fitz.Matrix(1,1),alpha=False).save('/mnt/data/final_toc_page4.png')
check.close()
print('zip bytes:',zip_path.stat().st_size)
