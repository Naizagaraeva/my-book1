from pathlib import Path
import json, re, shutil, zipfile
from pypdf import PdfReader, PdfWriter, Transformation
import fitz

ROOT=Path('/mnt/data/sitefix')
pdf=ROOT/'assets/book.pdf'
tmp=ROOT/'assets/book_shift_tmp.pdf'
reader=PdfReader(str(pdf)); writer=PdfWriter(); shifted=[]
# Move content upward only on pages where the first text is visibly too far down.
# Keep the cover, title page, preface and contents pages exactly as supplied.
fitz_doc=fitz.open(str(pdf))
for idx, page in enumerate(reader.pages):
    pno=idx+1
    delta=0
    if pno >= 5:
        fp=fitz_doc[idx]
        spans=[]
        for block in fp.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line.get('spans',[]):
                    if span.get('text','').strip() and span['bbox'][1] < 790:
                        spans.append(span)
        if spans:
            top=min(s['bbox'][1] for s in spans)
            bottom=max(s['bbox'][3] for s in spans)
            # Fix pages with excessive top whitespace, while retaining safe bottom clearance.
            if top > 100:
                delta=min(top-58, max(0, bottom-650))
                if delta > 0:
                    page.add_transformation(Transformation().translate(tx=0, ty=-delta))
                    shifted.append((pno, round(delta,1)))
    writer.add_page(page)
with open(tmp,'wb') as f: writer.write(f)
fitz_doc.close()
# Reposition footer page numbers after shifting and clear the old, shifted footer.
doc=fitz.open(str(tmp))
for pno,delta in shifted:
    page=doc[pno-1]
    page.draw_rect(fitz.Rect(0, 790, page.rect.width, page.rect.height), color=None, fill=(1,1,1), overlay=True)
    # Keep the physical PDF page number at the normal bottom-center location.
    label=str(pno)
    fontsize=9
    width=fitz.get_text_length(label, fontname='Times-Roman', fontsize=fontsize)
    page.insert_text(fitz.Point((page.rect.width-width)/2, 821), label, fontname='Times-Roman', fontsize=fontsize, color=(0,0,0), overlay=True)
doc.save(str(pdf), garbage=4, deflate=True)
doc.close(); tmp.unlink(missing_ok=True)

# Replace the static flat TOC with a grouped accordion, initially collapsed.
js=ROOT/'viewer.js'
s=js.read_text(encoding='utf-8')
start=s.index('  function buildToc() {')
end=s.index('\n  async function renderPdfLinks', start)
new_func=r'''  function buildToc() {
    const list = $('tocList');
    list.replaceChildren();
    const items = window.BOOK_CONTENTS || [];
    const groups = [];
    for (const item of items) {
      let group = groups.find(g => g.name === item.group);
      if (!group) { group = { name: item.group, items: [] }; groups.push(group); }
      // Group headings are represented by the accordion button, not repeated as child links.
      if (item.title.trim().toLocaleLowerCase('kk') !== item.group.trim().toLocaleLowerCase('kk')) group.items.push(item);
    }
    groups.forEach((group, groupIndex) => {
      const section = document.createElement('section');
      section.className = 'toc-accordion';
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'toc-group';
      button.setAttribute('aria-expanded', 'false');
      button.innerHTML = '<span class="toc-chevron" aria-hidden="true">▸</span><span class="toc-group-name"></span><span class="toc-group-count"></span>';
      button.querySelector('.toc-group-name').textContent = group.name;
      button.querySelector('.toc-group-count').textContent = group.items.length;
      const children = document.createElement('div');
      children.className = 'toc-children hidden';
      button.addEventListener('click', () => {
        const open = button.getAttribute('aria-expanded') !== 'true';
        button.setAttribute('aria-expanded', String(open));
        children.classList.toggle('hidden', !open);
        button.querySelector('.toc-chevron').textContent = open ? '▾' : '▸';
      });
      group.items.forEach(item => {
        const link = document.createElement('a');
        link.className = 'toc-link';
        link.href = '#page=' + item.page;
        link.dataset.page = String(item.page);
        link.setAttribute('aria-label', `${item.title}, ${item.page}-бет`);
        const title = document.createElement('span');
        title.className = 'toc-title';
        title.textContent = item.title;
        const pageNo = document.createElement('span');
        pageNo.className = 'toc-page';
        pageNo.textContent = item.page;
        link.append(title, pageNo);
        children.appendChild(link);
      });
      section.append(button, children);
      list.appendChild(section);
    });
  }
'''
s=s[:start]+new_func+s[end:]
# Search handlers updated to work with collapsed accordion children.
old="""    document.querySelectorAll('.toc-link').forEach(link => {
      const title = link.querySelector('.toc-title');
      link.classList.toggle('hidden', !!query && !title.textContent.toLocaleLowerCase('kk').includes(query));
    });
    document.querySelectorAll('.toc-group').forEach(group => {
      let node = group.nextElementSibling;
      let hasMatch = false;
      while (node && !node.classList.contains('toc-group')) {
        if (node.classList.contains('toc-link') && !node.classList.contains('hidden')) hasMatch = true;
        node = node.nextElementSibling;
      }
      group.classList.toggle('hidden', !!query && !hasMatch);
    });"""
new="""    document.querySelectorAll('.toc-link').forEach(link => {
      const title = link.querySelector('.toc-title');
      link.classList.toggle('hidden', !!query && !title.textContent.toLocaleLowerCase('kk').includes(query));
    });
    document.querySelectorAll('.toc-accordion').forEach(section => {
      const button = section.querySelector('.toc-group');
      const children = section.querySelector('.toc-children');
      const links = [...section.querySelectorAll('.toc-link')];
      const hasMatch = links.some(link => !link.classList.contains('hidden'));
      button.classList.toggle('hidden', !!query && !hasMatch);
      if (query && hasMatch) {
        children.classList.remove('hidden');
        button.setAttribute('aria-expanded', 'true');
        button.querySelector('.toc-chevron').textContent = '▾';
      } else if (!query) {
        children.classList.add('hidden');
        button.setAttribute('aria-expanded', 'false');
        button.querySelector('.toc-chevron').textContent = '▸';
      }
    });"""
if old not in s: raise SystemExit('Search handler pattern not found')
s=s.replace(old,new)
# Clicking the paper advances/rewinds by side; PDF hyperlinks remain above the canvas and keep working.
needle="""  $('tocList').addEventListener('click', event => {"""
insert="""  canvas.title = 'Беттің оң жағын басыңыз — келесі бет; сол жағын басыңыз — алдыңғы бет';
  canvas.style.cursor = 'ew-resize';
  canvas.addEventListener('click', event => {
    if (!pdfDoc) return;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    if (x < rect.width / 2) goTo(currentPage - 1);
    else goTo(currentPage + 1);
  });

  $('tocList').addEventListener('click', event => {"""
if needle not in s: raise SystemExit('TOC click insertion point not found')
s=s.replace(needle,insert)
js.write_text(s,encoding='utf-8')

# CSS for accordion sections and the click-turn affordance.
css=ROOT/'viewer.css'
c=css.read_text(encoding='utf-8')
c += r'''

/* Collapsible table-of-contents groups */
.toc-accordion{margin:0 0 5px}
.toc-group{width:100%;display:flex;align-items:center;gap:7px;text-align:left;border:1px solid transparent;border-radius:4px;background:transparent;cursor:pointer;padding:10px 8px 7px;color:#485362;font-weight:700;font-size:10px;text-transform:uppercase;letter-spacing:.25px}
.toc-group:hover{background:#e8f1fd;border-color:#c7dcf6;color:#153c75}
.toc-chevron{width:12px;flex:none;font-size:13px;color:#3979c3}
.toc-group-name{flex:1}
.toc-group-count{font-size:9px;font-weight:400;color:#748093;background:#e8edf4;border-radius:10px;padding:2px 6px}
.toc-children{padding-left:8px;border-left:1px solid #d8e0ea;margin-left:13px}
body.dark-theme .toc-group{color:#d3deeb}
body.dark-theme .toc-group:hover{background:#2b3b50;border-color:#405a7b;color:#fff}
body.dark-theme .toc-group-count{background:#303d50;color:#c3d1e4}
body.dark-theme .toc-children{border-left-color:#40516a}
#pdfCanvas{cursor:ew-resize}
'''
css.write_text(c,encoding='utf-8')

# Rebuild archive with fixed source tree, retaining all included source files.
zip_path=Path('/mnt/data/cpp_machine_oriented_ebook_github.zip')
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for f in sorted(ROOT.rglob('*')):
        if f.is_file() and f.name != 'fix_site.py':
            z.write(f, f.relative_to(ROOT).as_posix())
print('Shifted pages:', shifted)
print('Updated', zip_path, zip_path.stat().st_size)
