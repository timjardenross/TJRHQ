def lum(hexv):
    hexv = hexv.lstrip('#')
    r, g, b = [int(hexv[i:i+2], 16) / 255 for i in (0, 2, 4)]
    def f(c): return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = f(r), f(g), f(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def contrast(a, b):
    la, lb = lum(a), lum(b)
    l1, l2 = max(la, lb), min(la, lb)
    return round((l1 + 0.05) / (l2 + 0.05), 2)

BGS = {'space': '#dce8f4', 'panel': '#eaf1f8', 'card': '#ccd8ec'}

# name: (hex, threshold, role)
TOKENS = {
    'command DEFAULT':      ('#FFB81C', 3.0),
    'command light/on':     ('#7A4D00', 4.5),
    'engineering DEFAULT':  ('#FF9800', 3.0),
    'engineering light/on': ('#8A3C00', 4.5),
    'ops DEFAULT':          ('#F44336', 3.0),
    'ops light/on':         ('#B71C1C', 4.5),
    'nav DEFAULT':          ('#CC88FF', 3.0),
    'nav light/on':         ('#5B2AAA', 4.5),
    'science DEFAULT (re-shaded)': ('#06768D', 3.0),
    'science light/on':     ('#0B4A57', 4.5),
    'accent (new)':         ('#0C5A82', 4.5),
    'status ok':            ('#278A44', 3.0),
    'status ok text':       ('#1B5E20', 4.5),
    'status warn':          ('#9C5D10', 3.0),
    'status warn text':     ('#7A4610', 4.5),
    'status crit':          ('#C43030', 3.0),
    'status crit text':     ('#7A1616', 4.5),
    'text-primary':         ('#0d1f33', 4.5),
    'text-secondary':       ('#3a5a78', 4.5),
}

print(f"{'token':<28} {'space':>7} {'panel':>7} {'card':>7}  threshold  verdict")
all_pass = True
for name, (hexv, threshold) in TOKENS.items():
    ratios = {bg: contrast(hexv, bgc) for bg, bgc in BGS.items()}
    worst = min(ratios.values())
    verdict = 'PASS' if worst >= threshold else 'FAIL'
    if verdict == 'FAIL':
        all_pass = False
    print(f"{name:<28} {ratios['space']:>7} {ratios['panel']:>7} {ratios['card']:>7}  >={threshold:<7} {verdict}")

print()
print("ALL PASS" if all_pass else "SOME FAIL — see above")
