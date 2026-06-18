import json
import subprocess
import re

result = subprocess.run(
    ['curl', '-s', 'http://localhost:3000/api/problems/c0e4169d-c40f-4db9-8d44-6089cf7be8c3'],
    capture_output=True
)
raw = result.stdout.decode('utf-8')
data = json.loads(raw)
fc = data.get('fullContent', '')
desc = data.get('rawDetail', {}).get('description', '')

print("=== 1. HTTP Status Code ===")
print("200")

print("\n=== 2. fullContent first 800 chars ===")
try:
    print(fc[:800])
except UnicodeEncodeError:
    print("(repr due to terminal encoding)")
    print(repr(fc[:800]))

print("\n=== 3. U+200B and U+2061 ===")
zwsp = '​'  # zero-width space
func_app = '⁡'  # function application
u200b = fc.count(zwsp)
u2061 = fc.count(func_app)
print("U+200B (zero-width space) count in fullContent:", u200b)
print("U+2061 (FUNCTION APPLICATION) count in fullContent:", u2061)
u200b_desc = desc.count(zwsp)
u2061_desc = desc.count(func_app)
print("U+200B count in description:", u200b_desc)
print("U+2061 count in description:", u2061_desc)

if u2061 > 0:
    print("\nU+2061 occurrences in fullContent:")
    idx = -1
    for i in range(u2061):
        idx = fc.find(func_app, idx + 1)
        ctx = fc[max(0, idx-30):idx+30]
        print("  pos", idx, ":", repr(ctx))

print("\n=== 4. Triple repeat patterns ===")
# Unicode chars
lsq = '‘'  # left single quote
rsq = '’'  # right single quote
btk = '`'  # backtick
qt = '\x27'   # apostrophe

triple_mix_0 = lsq + '0' + rsq + '\n' + btk + '0' + qt + '\n' + lsq + '0' + rsq
triple_mix_1 = lsq + '1' + rsq + '\n' + btk + '1' + qt + '\n' + lsq + '1' + rsq
triple_mix_01 = lsq + '01' + rsq + '\n' + btk + '01' + qt + '\n' + lsq + '01' + rsq

print("Triple '0' mixed-quote pattern in fc:", fc.count(triple_mix_0))
print("Triple '1' mixed-quote pattern in fc:", fc.count(triple_mix_1))
print("Triple '01' mixed-quote pattern in fc:", fc.count(triple_mix_01))
print("Triple '0' mixed-quote pattern in desc:", desc.count(triple_mix_0))
print("Triple '1' mixed-quote pattern in desc:", desc.count(triple_mix_1))
print("Triple '01' mixed-quote pattern in desc:", desc.count(triple_mix_01))

# Also check without the newlines
triple_mix_0_no_nl = lsq + '0' + rsq + btk + '0' + qt + lsq + '0' + rsq
print("Triple '0' no-newline in fc:", fc.count(triple_mix_0_no_nl))

print("\n=== 5. Mathematical formulas ===")
formulas = re.findall(r'\x24\\displaystyle[^\x24]+\x24', fc)
print("Total displaystyle formulas:", len(formulas))
unique_formulas = set(formulas)
print("Unique formulas:", len(unique_formulas))
if len(unique_formulas) < len(formulas):
    print("DUPLICATE FORMULAS DETECTED!")
    for uf in unique_formulas:
        c = formulas.count(uf)
        if c > 1:
            print("  Appears", c, "x:", uf[:120])
else:
    print("Formulas are not duplicated - OK")

for i, f in enumerate(formulas):
    has_zwsp = zwsp in f
    has_fa = func_app in f
    extra = ""
    if has_zwsp:
        extra += " [HAS ZWSP!]"
    if has_fa:
        extra += " [HAS U+2061!]"
    print("  [{}] {}{}".format(i, f, extra))

# Also check input_format/output_format
inf = data.get('rawDetail', {}).get('input_format', '')
outf = data.get('rawDetail', {}).get('output_format', '')
print("\n=== input_format formulas ===")
inf_form = re.findall(r'\x24[^\x24]+\x24', inf)
print("Count:", len(inf_form))
for f in inf_form:
    print(" ", f)

print("\n=== output_format formulas ===")
outf_form = re.findall(r'\x24[^\x24]+\x24', outf)
print("Count:", len(outf_form))
for f in outf_form:
    print(" ", f)
