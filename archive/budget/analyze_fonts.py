import fitz
from collections import OrderedDict

doc = fitz.open("/home/swap/github/translation/output/redbook8283.pdf")

for page_no in [16, 34]:  # pages 17 and 35 (0-indexed)
    print(f"\n{'='*80}")
    print(f"PAGE {page_no + 1} (0-indexed: {page_no})")
    print(f"{'='*80}")
    page = doc[page_no]

    # 1. Fonts used on the page
    fonts = page.get_fonts()
    print(f"\n--- Fonts on page ---")
    for f in fonts:
        print(f"  {f}")

    # 2. Text blocks with position info
    blocks = page.get_text('dict')['blocks']
    print(f"\n--- Text blocks ({len(blocks)} blocks) ---")
    for bi, b in enumerate(blocks):
        if b['type'] == 0:  # text block
            for li, l in enumerate(b['lines']):
                for si, s in enumerate(l['spans']):
                    print(f"  block={bi} line={li} span={si}: "
                          f"font='{s['font']}' size={s['size']:.1f} "
                          f"flags={s['flags']} color={s['color']} "
                          f"origin=({s['origin'][0]:.1f},{s['origin'][1]:.1f}) "
                          f"bbox=({s['bbox'][0]:.1f},{s['bbox'][1]:.1f},{s['bbox'][2]:.1f},{s['bbox'][3]:.1f}) "
                          f"text={s['text'][:120]!r}")
        elif b['type'] == 1:  # image block
            print(f"  block={bi}: IMAGE {b['width']}x{b['height']}")

# 3. Now collect ALL unique fonts across both pages, get full font objects
print(f"\n{'='*80}")
print(f"UNIQUE FONT OBJECTS (from pages 17 & 35)")
print(f"{'='*80}")

unique_fonts = OrderedDict()
for page_no in [16, 34]:
    page = doc[page_no]
    for f in page.get_fonts():
        xref = f[0]  # font xref
        if xref not in unique_fonts:
            unique_fonts[xref] = f

for xref, f in unique_fonts.items():
    font_name = f[3]
    font_type = f[4]
    encoding = f[5]
    print(f"\n--- Font xref={xref} name='{font_name}' type={font_type} encoding={encoding} ---")
    obj = doc.xref_object(xref)
    print(f"  xref object:\n{obj}")

    # Check for /ToUnicode
    for key in ['ToUnicode', 'Encoding', 'BaseFont', 'Subtype', 'DescendantFonts', 'CIDToGIDMap']:
        rc = doc.xref_get_key(xref, key)
        print(f"  /{key} -> {rc}")

    # Follow DescendantFonts
    rc = doc.xref_get_key(xref, 'DescendantFonts')
    if rc[0] == 'array':
        # parse array to find xrefs
        raw = rc[1]
        import re
        desc_xrefs = [int(x) for x in re.findall(r'(\d+)\s+0\s+R', raw)]
        print(f"  DescendantFonts xrefs: {desc_xrefs}")
        for dx in desc_xrefs:
            dobj = doc.xref_object(dx)
            print(f"  DescendantFont xref={dx}:\n    {dobj}")
            for key in ['CIDSystemInfo', 'FontDescriptor', 'DW', 'W', 'Subtype', 'BaseFont']:
                rc2 = doc.xref_get_key(dx, key)
                print(f"    /{key} -> {rc2}")

            # Follow FontDescriptor for font program
            rc2 = doc.xref_get_key(dx, 'FontDescriptor')
            if rc2[0] == 'xref':
                fd_xref = int(rc2[1].split()[0])
                fd_obj = doc.xref_object(fd_xref)
                print(f"    FontDescriptor xref={fd_xref}:\n      {fd_obj}")
                for key2 in ['FontName', 'FontFile2', 'FontFile3', 'Flags', 'ItalicAngle', 'Ascent', 'Descent', 'CapHeight', 'StemV']:
                    rc3 = doc.xref_get_key(fd_xref, key2)
                    print(f"      /{key2} -> {rc3}")

    # Follow ToUnicode CMap
    rc = doc.xref_get_key(xref, 'ToUnicode')
    if rc[0] == 'xref':
        tu_xref = int(rc[1].split()[0])
        print(f"\n  --- ToUnicode CMap xref={tu_xref} ---")
        try:
            tu_data = doc.xref_stream(tu_xref)
            print(f"  Raw stream length: {len(tu_data)} bytes")
            # Decode if it's ASCII (CMap is ASCII)
            try:
                text = tu_data.decode('ascii', errors='replace')
                print(f"  Content:\n{text}")
            except:
                print(f"  Binary content, first 200 bytes: {tu_data[:200]}")
        except Exception as e:
            print(f"  No stream: {e}")

    # Check for embedded font program in FontFile2/3
    rc = doc.xref_get_key(xref, 'FontFile2')
    if rc[0] == 'null':
        # try descendant
        pass

    # Also check for /CIDFont /CIDToGIDMap
    print()

# 4. Try to get the full font program from FontFile3 / FontFile2
print(f"\n{'='*80}")
print(f"EMBEDDED FONT PROGRAMS")
print(f"{'='*80}")

seen_fontfiles = set()
for page_no in [16, 34]:
    page = doc[page_no]
    for f in page.get_fonts():
        xref = f[0]
        # walk the reference tree
        rc = doc.xref_get_key(xref, 'DescendantFonts')
        if rc[0] == 'array':
            desc_xrefs = [int(x) for x in re.findall(r'(\d+)\s+0\s+R', rc[1])]
            for dx in desc_xrefs:
                rc2 = doc.xref_get_key(dx, 'FontDescriptor')
                if rc2[0] == 'xref':
                    fd_xref = int(rc2[1].split()[0])
                    for ftype in ['FontFile2', 'FontFile3']:
                        rc3 = doc.xref_get_key(fd_xref, ftype)
                        if rc3[0] == 'xref':
                            ff_xref = int(rc3[1].split()[0])
                            if ff_xref not in seen_fontfiles:
                                seen_fontfiles.add(ff_xref)
                                try:
                                    ff_stream = doc.xref_stream(ff_xref)
                                    print(f"\n  {ftype} xref={ff_xref}: {len(ff_stream)} bytes")
                                    # Check first bytes for format detection
                                    print(f"  First 16 bytes: {ff_stream[:16].hex()}")
                                    print(f"  First 16 as str: {ff_stream[:16]!r}")
                                    # Detect format
                                    if ff_stream[:4] == b'OTTO':
                                        print(f"  Format: OpenType (CFF)")
                                    elif ff_stream[:4] == b'\x00\x01\x00\x00' or ff_stream[:4] == b'\x00\x00\x00\x00':
                                        # might be TrueType with apple or open type
                                        if ff_stream[:2] == b'\x00\x01':
                                            print(f"  Format: TrueType (sfnt w/ TrueType outlines)")
                                        elif ff_stream[:4] == b'\x00\x00\x00\x00':
                                            print(f"  Format: TrueType (possibly)")
                                        else:
                                            print(f"  Format: Unknown sfnt")
                                    elif ff_stream[:2] == b'\x00\x01':
                                        print(f"  Format: TrueType")
                                    elif ff_stream[:4] == b'wOFF':
                                        print(f"  Format: WOFF")
                                    else:
                                        print(f"  Format: Unknown")
                                except Exception as e:
                                    print(f"  {ftype} xref={ff_xref}: Error - {e}")

# 5. Let's also look at all CMap streams referenced anywhere (not just ToUnicode)
print(f"\n{'='*80}")
print(f"ALL CMAP STREAMS IN DOCUMENT")
print(f"{'='*80}")
# Scan all xrefs for streams that might be CMap
for i in range(1, doc.xref_length()):
    try:
        obj_str = doc.xref_object(i)
        if '/CMap' in obj_str and '/Type' in obj_str:
            try:
                stream = doc.xref_stream(i)
                print(f"\n  xref={i}:")
                print(f"  Object: {obj_str[:300]}")
                text = stream.decode('ascii', errors='replace')
                print(f"  Stream:\n{text[:2000]}")
            except:
                pass
    except:
        pass

doc.close()
