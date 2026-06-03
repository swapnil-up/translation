import fitz
import struct

doc = fitz.open("/home/swap/github/translation/output/redbook8283.pdf")

# ============================================================
# PART 1: Show text extracted from pages 17 and 35
# ============================================================
for page_no, label in [(16, "PAGE 17"), (34, "PAGE 35")]:
    print(f"\n{'='*80}")
    print(f"{label}")
    print(f"{'='*80}")
    page = doc[page_no]
    # raw text
    text = page.get_text('text')
    print(f"\nRaw text ({len(text)} chars):")
    print(text[:3000])

    # dict with positions
    blocks = page.get_text('dict')['blocks']
    print(f"\n\nText blocks detail:")
    cid_info = []
    for bi, b in enumerate(blocks):
        if b['type'] == 0:
            for li, l in enumerate(b['lines']):
                for si, s in enumerate(l['spans']):
                    cid_info.append({
                        'block': bi, 'line': li, 'span': si,
                        'font': s['font'], 'size': s['size'],
                        'origin': s['origin'], 'text': s['text'],
                        'bbox': s['bbox']
                    })
                    print(f"  [{bi}:{li}:{si}] font={s['font']:20s} size={s['size']:5.1f} "
                          f"origin=({s['origin'][0]:7.1f},{s['origin'][1]:7.1f}) "
                          f"text={s['text'][:100]!r}")

    print(f"\nTotal spans: {len(cid_info)}")

# ============================================================
# PART 2: Build complete CID→Unicode map by collecting all ToUnicode CMaps
# ============================================================
print(f"\n{'='*80}")
print(f"COMPLETE CID→UNICODE MAP FROM ALL ToUnicode CMaps")
print(f"{'='*80}")

import re

all_cid_mappings = {}  # CID -> Unicode

# Scan through entire document for Kalimati ToUnicode CMaps
for i in range(1, doc.xref_length()):
    try:
        obj_str = doc.xref_object(i)
        if '/CMap' in obj_str and '/Type' in obj_str:
            stream = doc.xref_stream(i)
            text = stream.decode('ascii', errors='replace')
            # Parse bfrange
            blocks = re.findall(r'beginbfrange\n(.*?)\nendbfrange', text, re.DOTALL)
            for block in blocks:
                lines = block.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) < 3:
                        continue
                    src_start = int(parts[0].strip('<>'), 16)
                    src_end = int(parts[1].strip('<>'), 16)
                    dst_part = ' '.join(parts[2:])
                    
                    if dst_part.startswith('['):
                        dst_codes = [int(x.strip('<>'), 16) for x in re.findall(r'<([0-9A-Fa-f]+)>', dst_part)]
                        for j, dst in enumerate(dst_codes):
                            cid = src_start + j
                            if cid <= src_end:
                                all_cid_mappings[cid] = dst
                    else:
                        dst = int(dst_part.strip('<>'), 16)
                        for j in range(src_end - src_start + 1):
                            all_cid_mappings[src_start + j] = dst + j
    except:
        pass

print(f"Total CID→Unicode mappings found across all CMaps: {len(all_cid_mappings)}")

# Check for conflicts
from collections import defaultdict
cid_to_ucs = defaultdict(list)
for cid, uc in all_cid_mappings.items():
    cid_to_ucs[cid].append(uc)

conflicts = {cid: ucs for cid, ucs in cid_to_ucs.items() if len(ucs) > 1}
if conflicts:
    print(f"\nConflicts (CID mapped to multiple Unicode values): {len(conflicts)}")
    for cid in sorted(conflicts.keys())[:20]:
        print(f"  CID {cid:4d} -> {[f'U+{uc:04X}' for uc in conflicts[cid]]}")

# Print final mapping
print(f"\nFinal CID→Unicode mapping ({len(cid_to_ucs)} unique CIDs):")
for cid in sorted(cid_to_ucs.keys()):
    uc = cid_to_ucs[cid][0]  # take first if multiple
    ch = chr(uc) if uc < 0x110000 else '?'
    print(f"  CID {cid:4d} (0x{cid:04X}) → U+{uc:04X} {ch}")

# ============================================================
# PART 3: Extract raw CID values from page content streams
# ============================================================
print(f"\n{'='*80}")
print(f"RAW OPERATORS FROM PAGE CONTENT STREAMS")
print(f"{'='*80}")

for page_no, label in [(16, "PAGE 17"), (34, "PAGE 35")]:
    page = doc[page_no]
    print(f"\n--- {label} ---")
    
    # Get the raw content stream and decode CIDs
    ops = page.get_text('rawdict')
    blocks = ops['blocks']
    for bi, b in enumerate(blocks):
        if b['type'] == 0:
            for li, l in enumerate(b['lines']):
                for si, s in enumerate(l['spans']):
                    # s['text'] has been decoded by fitz using ToUnicode
                    # To get the raw CIDs, we need to look at the content stream
                    pass

# Let's also look at what text is actually produced for these pages
# by examining each character
print(f"\n{'='*80}")
print(f"CHARACTER-LEVEL DETAILS (from 'rawdict')")
print(f"{'='*80}")

for page_no, label in [(16, "PAGE 17"), (34, "PAGE 35")]:
    page = doc[page_no]
    print(f"\n--- {label} ---")
    blocks = page.get_text('rawdict')['blocks']
    char_count = 0
    for b in blocks:
        if b['type'] == 0:
            for l in b['lines']:
                for s in l['spans']:
                    text = s['text']
                    # Print text with character details
                    for i, ch in enumerate(text):
                        uc = ord(ch)
                        # Get the font used for this char
                        if char_count < 200:
                            print(f"  char[{char_count}] = {ch!r} U+{uc:04X} "
                                  f"font={s['font']}")
                        char_count += 1
    print(f"  Total characters: {char_count}")

doc.close()
