import fitz
import struct

doc = fitz.open("/home/swap/github/translation/output/redbook8283.pdf")

# ============================================================
# PART 1: Extract one Kalimati TTF and parse its cmap table
# ============================================================

# Use Kalimati xref 2277 (QWAAAA+Kalimati, page 16/17)
kalimati_tt_xref = 2277  # QRAAAA+Kalimati - one instance from page 16
# Actually let's get ALL unique Kalimati font programs
seen_kalimati = set()
kalimati_tts = []
for page_no in [16, 34]:
    page = doc[page_no]
    for f in page.get_fonts():
        if f[3] == 'Kalimati':
            xref = f[0]
            rc = doc.xref_get_key(xref, 'DescendantFonts')
            if rc[0] == 'array':
                import re
                desc_xrefs = [int(x) for x in re.findall(r'(\d+)\s+0\s+R', rc[1])]
                for dx in desc_xrefs:
                    rc2 = doc.xref_get_key(dx, 'FontDescriptor')
                    if rc2[0] == 'xref':
                        fd_xref = int(rc2[1].split()[0])
                        rc3 = doc.xref_get_key(fd_xref, 'FontFile2')
                        if rc3[0] == 'xref':
                            ff_xref = int(rc3[1].split()[0])
                            fontname = doc.xref_get_key(fd_xref, 'FontName')[1]
                            if ff_xref not in seen_kalimati:
                                seen_kalimati.add(ff_xref)
                                kalimati_tts.append((ff_xref, fontname, f[0]))

print("=" * 80)
print("UNIQUE KALIMATI FONT PROGRAMS")
print("=" * 80)
for ff_xref, fontname, font_xref in kalimati_tts:
    sz = len(doc.xref_stream(ff_xref))
    print(f"  FontFile2 xref={ff_xref}: fontname={fontname} size={sz} bytes")

# Parse the largest one
largest = max(kalimati_tts, key=lambda x: len(doc.xref_stream(x[0])))
ff_xref = largest[0]
fontname = largest[1]
print(f"\nAnalyzing largest: xref={ff_xref} fontname={fontname}")

tt_data = doc.xref_stream(ff_xref)

def parse_sfnt_cmap(data):
    """Parse TrueType/OpenType cmap table to get Unicode mappings."""
    if len(data) < 12:
        return {}
    
    # Parse offset table
    sfversion = struct.unpack('>I', data[0:4])[0]
    num_tables = struct.unpack('>H', data[4:6])[0]
    
    print(f"\n  sfVersion=0x{sfversion:08X} numTables={num_tables}")
    
    # Find cmap table
    cmap_offset = None
    cmap_length = None
    for i in range(num_tables):
        offset = 12 + i * 16
        tag = data[offset:offset+4]
        checksum, toffset, tlength = struct.unpack('>III', data[offset+4:offset+16])
        if tag == b'cmap':
            cmap_offset = toffset
            cmap_length = tlength
            print(f"  Found cmap table: offset={cmap_offset} length={cmap_length}")
            break
    
    if cmap_offset is None:
        print("  No cmap table found!")
        return {}
    
    cmap_data = data[cmap_offset:cmap_offset+cmap_length]
    
    # Parse cmap header
    version = struct.unpack('>H', cmap_data[0:2])[0]
    num_tables = struct.unpack('>H', cmap_data[2:4])[0]
    print(f"  cmap version={version} numSubtables={num_tables}")
    
    results = {}
    
    for i in range(num_tables):
        entry_off = 4 + i * 8
        platform_id = struct.unpack('>H', cmap_data[entry_off:entry_off+2])[0]
        encoding_id = struct.unpack('>H', cmap_data[entry_off+2:entry_off+4])[0]
        subtable_offset = struct.unpack('>I', cmap_data[entry_off+4:entry_off+8])[0]
        
        print(f"\n    Subtable {i}: platform={platform_id} encoding={encoding_id} offset={subtable_offset}")
        
        sub_data = cmap_data[subtable_offset:]
        format_type = struct.unpack('>H', sub_data[0:2])[0]
        print(f"    Format: {format_type}")
        
        if format_type == 0:  # Byte encoding table
            length = struct.unpack('>H', sub_data[2:4])[0]
            language = struct.unpack('>H', sub_data[4:6])[0]
            print(f"    Format 0: length={length} language={language}")
            for j in range(256):
                glyph = sub_data[6 + j]
                if glyph != 0:
                    results[j] = glyph
            print(f"    => {len(results)} non-zero mappings")
            
        elif format_type == 4:  # Segment-to-delta
            length = struct.unpack('>H', sub_data[2:4])[0]
            language = struct.unpack('>H', sub_data[4:6])[0]
            seg_count = struct.unpack('>H', sub_data[6:8])[0] // 2
            print(f"    Format 4: length={length} language={language} segCount={seg_count}")
            
            # Parse end codes
            end_codes = []
            for j in range(seg_count):
                ec = struct.unpack('>H', sub_data[14 + j*2:14 + j*2 + 2])[0]
                end_codes.append(ec)
            
            start_codes_offset = 14 + seg_count * 2 + 2  # skip reserved
            start_codes = []
            for j in range(seg_count):
                sc = struct.unpack('>H', sub_data[start_codes_offset + j*2:start_codes_offset + j*2 + 2])[0]
                start_codes.append(sc)
            
            id_deltas_offset = start_codes_offset + seg_count * 2
            id_deltas = []
            for j in range(seg_count):
                d = struct.unpack('>h', sub_data[id_deltas_offset + j*2:id_deltas_offset + j*2 + 2])[0]
                id_deltas.append(d)
            
            id_range_offsets_offset = id_deltas_offset + seg_count * 2
            id_range_offsets = []
            for j in range(seg_count):
                ro = struct.unpack('>h', sub_data[id_range_offsets_offset + j*2:id_range_offsets_offset + j*2 + 2])[0]
                id_range_offsets.append(ro)
            
            mappings = {}
            for seg in range(seg_count):
                if start_codes[seg] == 0xFFFF:
                    continue
                for cid in range(start_codes[seg], end_codes[seg] + 1):
                    if id_range_offsets[seg] == 0:
                        glyph_id = (cid + id_deltas[seg]) & 0xFFFF
                    else:
                        # Range offset method: need to read from the range offset table
                        range_offset_location = id_range_offsets_offset + seg * 2
                        actual_offset = range_offset_location + id_range_offsets[seg] + (cid - start_codes[seg]) * 2
                        if actual_offset + 2 <= len(sub_data):
                            glyph_id = struct.unpack('>H', sub_data[actual_offset:actual_offset+2])[0]
                            if glyph_id != 0:
                                glyph_id = (glyph_id + id_deltas[seg]) & 0xFFFF
                        else:
                            glyph_id = 0
                    if glyph_id != 0:
                        mappings[cid] = glyph_id
            
            results.update(mappings)
            print(f"    Format 4 => {len(mappings)} mappings")
            
        elif format_type == 6:  # Trimmed table
            length = struct.unpack('>H', sub_data[2:4])[0]
            language = struct.unpack('>H', sub_data[4:6])[0]
            first_code = struct.unpack('>H', sub_data[6:8])[0]
            entry_count = struct.unpack('>H', sub_data[8:10])[0]
            print(f"    Format 6: length={length} language={language} firstCode={first_code} entryCount={entry_count}")
            for j in range(entry_count):
                glyph = struct.unpack('>H', sub_data[10 + j*2:10 + j*2 + 2])[0]
                if glyph != 0:
                    results[first_code + j] = glyph
            print(f"    Format 6 => {entry_count} entries")

        elif format_type == 12:  # Segmented coverage (32-bit)
            length = struct.unpack('>I', sub_data[4:8])[0]
            language = struct.unpack('>I', sub_data[8:12])[0]
            n_groups = struct.unpack('>I', sub_data[12:16])[0]
            print(f"    Format 12: length={length} language={language} nGroups={n_groups}")
            for g in range(n_groups):
                goff = 16 + g * 12
                start_char = struct.unpack('>I', sub_data[goff:goff+4])[0]
                end_char = struct.unpack('>I', sub_data[goff+4:goff+8])[0]
                start_glyph = struct.unpack('>I', sub_data[goff+8:goff+12])[0]
                for c in range(start_char, end_char + 1):
                    results[c] = start_glyph + (c - start_char)
            print(f"    Format 12 => {sum([(struct.unpack('>I', sub_data[16+g*12+4:16+g*12+8])[0] - struct.unpack('>I', sub_data[16+g*12:16+g*12+4])[0] + 1) for g in range(n_groups)])} entries")
            
        else:
            print(f"    Unsupported format: {format_type}")
    
    return results

print(f"\n{'='*80}")
print(f"PARSING SFNT CMAP TABLE")
print(f"{'='*80}")
unicode_to_gid = parse_sfnt_cmap(tt_data)

# Build reverse mapping: GID -> Unicode
gid_to_unicode = {}
for uc, gid in unicode_to_gid.items():
    if gid not in gid_to_unicode:
        gid_to_unicode[gid] = []
    gid_to_unicode[gid].append(uc)

print(f"\n\nTotal Unicode→GID mappings: {len(unicode_to_gid)}")
print(f"Total GID→Unicode mappings: {len(gid_to_unicode)}")

# Print full mapping sorted by GID
print(f"\n{'='*80}")
print(f"FULL GID → UNICODE MAPPING (first 200 glyphs)")
print(f"{'='*80}")
for gid in sorted(gid_to_unicode.keys())[:200]:
    ucs = gid_to_unicode[gid]
    chars = ''.join(chr(uc) if uc < 0x110000 else '?' for uc in ucs)
    print(f"  GID {gid:4d} (0x{gid:04X}) → U+{ucs[0]:04X} {chars}")

# Now let's also show which CIDs appear in ToUnicode CMaps for pages 17 and 35
# vs what the actual cmap says
print(f"\n{'='*80}")
print(f"PAGE 17 vs 35 - COMPARISON WITH ACTUAL CMAP")
print(f"{'='*80}")

import re

def parse_tounicode_cmap(cmap_text):
    """Parse bfrange entries from CMap text."""
    mappings = {}
    # Parse beginbfrange...endbfrange blocks
    blocks = re.findall(r'beginbfrange\n(.*?)\nendbfrange', cmap_text, re.DOTALL)
    for block in blocks:
        # Remove comments
        lines = block.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Format: <src_start> <src_end> <dst>
            parts = line.split()
            if len(parts) < 3:
                continue
            src_start = int(parts[0].strip('<>'), 16)
            src_end = int(parts[1].strip('<>'), 16)
            dst_part = ' '.join(parts[2:])
            
            if dst_part.startswith('['):
                # Array mapping: [ <unicode> <unicode> ... ]
                dst_codes = [int(x.strip('<>'), 16) for x in re.findall(r'<([0-9A-Fa-f]+)>', dst_part)]
                for i, dst in enumerate(dst_codes):
                    if src_start + i <= src_end:
                        mappings[src_start + i] = dst
            else:
                # Single value
                dst = int(dst_part.strip('<>'), 16)
                for i in range(src_end - src_start + 1):
                    mappings[src_start + i] = dst + i
    return mappings

# Parse all Kalimati ToUnicode CMaps
for page_no, label in [(16, "Page 17"), (34, "Page 35")]:
    page = doc[page_no]
    print(f"\n--- {label} ---")
    for f in page.get_fonts():
        if f[3] == 'Kalimati':
            xref = f[0]
            rc = doc.xref_get_key(xref, 'ToUnicode')
            if rc[0] == 'xref':
                tu_xref = int(rc[1].split()[0])
                cmap_data = doc.xref_stream(tu_xref)
                cmap_text = cmap_data.decode('ascii')
                page_mappings = parse_tounicode_cmap(cmap_text)
                print(f"  ToUnicode xref={tu_xref}: {len(page_mappings)} mappings")
                for cid in sorted(page_mappings.keys()):
                    uc = page_mappings[cid]
                    # Check if this matches the TrueType cmap
                    if cid in gid_to_unicode:
                        actual_ucs = gid_to_unicode[cid]
                        actual_uc = actual_ucs[0]
                        match = "✓" if actual_uc == uc else f"✗ (cmap says U+{actual_uc:04X})"
                    else:
                        match = "❓ (not in cmap)"
                    print(f"    CID {cid:4d} (0x{cid:04X}) → U+{uc:04X} ({chr(uc) if uc < 0x110000 else '?'}) {match}")

# Also print all GIDs sorted
print(f"\n{'='*80}")
print(f"ALL GLYPHS IN CMAP SORTED BY CODE POINT")
print(f"{'='*80}")
for uc in sorted(unicode_to_gid.keys()):
    gid = unicode_to_gid[uc]
    ch = chr(uc) if uc < 0x110000 else '?'
    print(f"  U+{uc:04X} {ch} → GID {gid} (0x{gid:04X})")

doc.close()
