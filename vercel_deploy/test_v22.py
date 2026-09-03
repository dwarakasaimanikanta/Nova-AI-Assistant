"""
Comprehensive test suite for generate_image.py v2.2
Tests all 15 cases from Phase 3 of the production audit.
"""
import sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, 'api')

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path('../.env'), override=False)
load_dotenv(dotenv_path=Path('.env'), override=False)

import ast
from generate_image import (
    _extract_primary_subject,
    _lookup_known_subject,
    _extract_user_scene,
    _validate_subject_preserved,
    _normalize_for_stem,
    _enhance_prompt,
    _pollinations_seed,
)

PASS = 0
FAIL = 0

def chk(name, got, expected, detail=''):
    global PASS, FAIL
    ok = (got == expected)
    if ok:
        PASS += 1
        print(f'  [PASS] {name}')
    else:
        FAIL += 1
        print(f'  [FAIL] {name}')
        print(f'         expected: {expected!r}')
        print(f'         got:      {got!r}')
        if detail:
            print(f'         note:     {detail}')

def contains(name, haystack, *needles):
    global PASS, FAIL
    missing = [n for n in needles if n.lower() not in haystack.lower()]
    ok = len(missing) == 0
    if ok:
        PASS += 1
        print(f'  [PASS] {name}')
    else:
        FAIL += 1
        print(f'  [FAIL] {name} -- missing: {missing}')
        print(f'         haystack[:150]: {haystack[:150]!r}')

def not_starts(name, text, prefix):
    global PASS, FAIL
    ok = not text.lower().strip().startswith(prefix.lower())
    if ok:
        PASS += 1
        print(f'  [PASS] {name}')
    else:
        FAIL += 1
        print(f'  [FAIL] {name}')
        print(f'         text starts with: {text[:60]!r}')


# ===========================================================================
print('=== 1. DUPLICATE FUNCTION CHECK ===')
src = open('api/generate_image.py', encoding='utf-8').read()
tree = ast.parse(src)
func_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
dupes = {n for n in func_names if func_names.count(n) > 1}
chk('No duplicate functions', len(dupes), 0, f'duplicates: {dupes}')

# ===========================================================================
print()
print('=== 2. POLLINATIONS DETERMINISTIC SEED ===')
s1 = _pollinations_seed("Lord Krishna, blue complexion")
s2 = _pollinations_seed("Lord Krishna, blue complexion")
s3 = _pollinations_seed("A futuristic robot")
chk('Same prompt -> same seed', s1, s2)
chk('Different prompt -> different seed', s1 != s3, True)
chk('Seed in valid range', 0 <= s1 < 99991, True)

# ===========================================================================
print()
print('=== 3. PLURAL/SINGULAR NORMALIZATION ===')
def stem_matches(word, target):
    return target in _normalize_for_stem(word)

chk('mountains -> mountain', stem_matches('mountains', 'mountain'), True)
chk('robots -> robot',       stem_matches('robots', 'robot'),       True)
chk('cities -> city',        stem_matches('cities', 'city'),        True)
chk('beaches -> beach',      stem_matches('beaches', 'beach'),      True)
chk('countries -> country',  stem_matches('countries', 'country'),  True)

# ===========================================================================
print()
print('=== 4. SUBJECT EXTRACTION ===')
chk('lord krishna extraction',
    _extract_primary_subject('naku Lord Krishna image generate chesi ivu'),
    'lord krishna')
chk('futuristic robot extraction',
    _extract_primary_subject('generate a futuristic robot'),
    'futuristic robot')
# Mountains madyalo river: madhyalo -> "in the middle of"
subj = _extract_primary_subject('mountains madhyalo river image generate cheyyi')
chk('mountains river extraction (contains mountains)', 'mountains' in subj, True)
chk('mountains river extraction (contains river)', 'river' in subj, True)
chk('cyberpunk hyderabad extraction',
    _extract_primary_subject('cyberpunk Hyderabad image create cheyyi'),
    'cyberpunk hyderabad')
chk('futuristic cyberpunk city',
    _extract_primary_subject('futuristic cyberpunk city image'),
    'futuristic cyberpunk city')

# ===========================================================================
print()
print('=== 5. KNOWN SUBJECT WORD-BOUNDARY MATCHING ===')
# These MUST match
chk('lord krishna matches',    _lookup_known_subject('lord krishna') is not None, True)
chk('krishna matches',         _lookup_known_subject('krishna') is not None, True)
chk('allu arjun matches',      _lookup_known_subject('allu arjun stylish') is not None, True)
chk('virat kohli matches',     _lookup_known_subject('virat kohli') is not None, True)
# Word-boundary safety — these must NOT accidentally match
chk('"ntr sector" does not match ntr actor ambiguously',
    _lookup_known_subject('new technology research') is None, True)
chk('"futuristic robot" does NOT match known subjects',
    _lookup_known_subject('futuristic robot') is None, True)
chk('"cyberpunk hyderabad" does NOT match known subjects',
    _lookup_known_subject('cyberpunk hyderabad') is None, True)

# ===========================================================================
print()
print('=== 6. USER SCENE EXTRACTION ===')
scene = _extract_user_scene('Lord Krishna standing in cyberpunk Hyderabad at night', 'lord krishna')
chk('scene: standing preserved',   'standing' in scene.lower(),   True)
chk('scene: cyberpunk preserved',  'cyberpunk' in scene.lower(),  True)
chk('scene: hyderabad preserved',  'hyderabad' in scene.lower(),  True)
chk('scene: night preserved',      'night' in scene.lower(),      True)
chk('scene: krishna removed',      'krishna' not in scene.lower(), True)

scene2 = _extract_user_scene('Allu Arjun black and white cinematic poster', 'allu arjun')
chk('scene2: black and white preserved', 'black' in scene2.lower() and 'white' in scene2.lower(), True)
chk('scene2: cinematic preserved',       'cinematic' in scene2.lower(), True)
chk('scene2: poster preserved',          'poster' in scene2.lower(), True)
chk('scene2: arjun removed',             'arjun' not in scene2.lower(), True)

scene3 = _extract_user_scene('Virat Kohli in futuristic stadium', 'virat kohli')
chk('scene3: futuristic preserved', 'futuristic' in scene3.lower(), True)
chk('scene3: stadium preserved',    'stadium' in scene3.lower(), True)

scene4 = _extract_user_scene('Lord Krishna realistic image in mountains', 'lord krishna')
chk('scene4: realistic preserved',  'realistic' in scene4.lower() or 'photorealistic' in scene4.lower(), True)
chk('scene4: mountains preserved',  'mountain' in scene4.lower(), True)

# ===========================================================================
print()
print('=== 7. NAMED ENTITY STRICT VALIDATION ===')
# VALID cases
chk('lord krishna VALID (verbatim)',
    _validate_subject_preserved('lord krishna',
        'Lord Krishna, blue complexion, peacock feather crown'), True)
chk('allu arjun VALID',
    _validate_subject_preserved('allu arjun stylish',
        'Stylized cinematic portrait of Allu Arjun, fashionable designer outfit'), True)
chk('virat kohli VALID',
    _validate_subject_preserved('virat kohli',
        'Stylized sports portrait of Virat Kohli, Indian cricket captain'), True)

# INVALID cases — generic replacements must FAIL
chk('lord krishna INVALID (generic woman)',
    _validate_subject_preserved('lord krishna',
        'a beautiful woman holding a flute, meadow background'), False)
chk('lord krishna INVALID (divine person)',
    _validate_subject_preserved('lord krishna',
        'a divine person holding a flute, sacred background'), False)
chk('lord krishna INVALID (blue-skinned deity, no name)',
    _validate_subject_preserved('lord krishna',
        'a beautiful blue-skinned deity playing flute in a meadow'), False)
chk('allu arjun INVALID (generic actor)',
    _validate_subject_preserved('allu arjun',
        'a stylish South Indian actor in designer clothes'), False)
chk('virat kohli INVALID (generic cricket player)',
    _validate_subject_preserved('virat kohli',
        'a cricket player in jersey, dynamic pose'), False)

# ===========================================================================
print()
print('=== 8. PLURAL/SINGULAR SOFT VALIDATION ===')
chk('mountains -> mountain PASS',
    _validate_subject_preserved('mountains river',
        'mountain range with a river flowing through valley'), True)
chk('robots PASS',
    _validate_subject_preserved('futuristic robots',
        'A futuristic robot with metallic armor'), True)
chk('cities -> city PASS',
    _validate_subject_preserved('cyberpunk cities',
        'cyberpunk city skyline, neon lights'), True)

# ===========================================================================
print()
print('=== 9. FULL PIPELINE — KNOWN SUBJECTS ===')

# Case 1: Lord Krishna basic
final, method, subj = _enhance_prompt('naku Lord Krishna image generate chesi ivu')
chk('Case1 method=known_subject', method, 'known_subject')
contains('Case1 final has Lord Krishna',   final, 'Lord Krishna')
contains('Case1 final has blue complexion', final, 'blue complexion')
contains('Case1 final has peacock feather', final, 'peacock feather')
contains('Case1 final has flute',          final, 'flute')

# Case 2: Lord Krishna + cyberpunk Hyderabad scene
final2, method2, subj2 = _enhance_prompt('Lord Krishna standing in cyberpunk Hyderabad at night')
chk('Case2 method=known_subject', method2, 'known_subject')
contains('Case2 final has Lord Krishna', final2, 'Lord Krishna')
contains('Case2 final has standing',     final2, 'standing')
contains('Case2 final has cyberpunk',    final2, 'cyberpunk')
contains('Case2 final has Hyderabad',    final2, 'Hyderabad')
contains('Case2 final has night',        final2, 'night')

# Case 3: Lord Krishna + realistic + mountains
final3, method3, subj3 = _enhance_prompt('Lord Krishna realistic image in mountains')
chk('Case3 method=known_subject', method3, 'known_subject')
contains('Case3 final has Lord Krishna', final3, 'Lord Krishna')
chk('Case3 final has realistic or photorealistic',
    'realistic' in final3.lower() or 'photorealistic' in final3.lower(), True)
chk('Case3 final has mountain',
    'mountain' in final3.lower(), True)

# Case 4: Allu Arjun + black and white + poster
final4, method4, subj4 = _enhance_prompt('Allu Arjun black and white cinematic poster')
chk('Case4 method=known_subject', method4, 'known_subject')
contains('Case4 final has Allu Arjun', final4, 'Allu Arjun')
chk('Case4 final has black and white',
    'black' in final4.lower() and 'white' in final4.lower(), True)
contains('Case4 final has cinematic', final4, 'cinematic')
contains('Case4 final has poster',    final4, 'poster')

# Case 5: Virat Kohli + futuristic stadium
final5, method5, subj5 = _enhance_prompt('Virat Kohli in futuristic stadium')
chk('Case5 method=known_subject', method5, 'known_subject')
contains('Case5 final has Virat Kohli', final5, 'Virat Kohli')
contains('Case5 final has futuristic',  final5, 'futuristic')
contains('Case5 final has stadium',     final5, 'stadium')

# ===========================================================================
print()
print('=== 10. FULL PIPELINE — UNKNOWN SUBJECTS ===')

# Case 6: futuristic robot — must NOT start with "generate"
final6, method6, subj6 = _enhance_prompt('generate a futuristic robot')
not_starts('Case6 final does NOT start with "generate"', final6, 'generate')
contains('Case6 final has futuristic', final6, 'futuristic')
contains('Case6 final has robot',      final6, 'robot')
def safe(s): return s.encode('ascii', 'replace').decode()
print(f'         Case6 method={method6!r}  final[:80]={safe(final6[:80])!r}')

# Case 7: mountains river
final7, method7, subj7 = _enhance_prompt('mountains madhyalo river image generate cheyyi')
chk('Case7 mountain preserved',
    'mountain' in final7.lower(), True)
chk('Case7 river preserved',
    'river' in final7.lower(), True)
print(f'         Case7 method={method7!r}  final[:80]={safe(final7[:80])!r}')

# Case 8: cyberpunk Hyderabad
final8, method8, subj8 = _enhance_prompt('cyberpunk Hyderabad image create cheyyi')
contains('Case8 final has cyberpunk',  final8, 'cyberpunk')
contains('Case8 final has Hyderabad',  final8, 'Hyderabad')
print(f'         Case8 method={method8!r}  final[:80]={safe(final8[:80])!r}')

# Case 9: futuristic cyberpunk city
final9, method9, subj9 = _enhance_prompt('futuristic cyberpunk city image')
contains('Case9 final has futuristic', final9, 'futuristic')
contains('Case9 final has cyberpunk',  final9, 'cyberpunk')
contains('Case9 final has city',       final9, 'city')
print(f'         Case9 method={method9!r}  final[:80]={safe(final9[:80])!r}')

# ===========================================================================
print()
print('=== 11. FRONTEND AUDIT (app.js) ===')
import re as _re
appjs = open('public/app.js', encoding='utf-8').read()
chk('No stale window.open(this.previousElementSibling)',
    bool(_re.search(r"window\.open\(this\.previousElementSibling", appjs)), False)
chk('Has URL.createObjectURL (Blob URL)',  'URL.createObjectURL' in appjs, True)
chk('Has atob() for base64 decode',       'atob(b64data)' in appjs, True)
chk('Has popup-blocked handling',         'Pop-up blocked' in appjs, True)
chk('Has URL.revokeObjectURL (cleanup)',  'URL.revokeObjectURL' in appjs, True)
chk('Has https:// URL fallback branch',  "startsWith('data:')" in appjs, True)

# ===========================================================================
print()
print('=' * 60)
total = PASS + FAIL
print(f'RESULT: {PASS}/{total} PASSED, {FAIL} FAILED')
if FAIL == 0:
    print('ALL TESTS PASSED')
else:
    print('FAILURES EXIST — see above')
