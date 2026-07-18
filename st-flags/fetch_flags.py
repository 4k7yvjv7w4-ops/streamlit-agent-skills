"""
One-time asset fetcher for the flag_emoji package.

Run this ONCE on a machine WITH internet access (e.g. your personal laptop),
then copy the whole flag_emoji/ folder into your project. At runtime the
package reads these PNGs from disk and needs no network.

To add/remove flags: edit COUNTRIES below and re-run.
Assets: Twemoji (https://github.com/jdecked/twemoji), graphics licensed CC-BY 4.0.
"""
import urllib.request
from pathlib import Path

FLAG_DIR = Path(__file__).parent / "flags"
FLAG_DIR.mkdir(exist_ok=True)

# ISO 3166-1 alpha-2 codes. 'eu' is the special EU flag. Extend freely.
COUNTRIES = [
    # FX majors / financial centres
    "us","eu","gb","jp","ch","ca","au","nz","cn","hk","sg","tw","kr","in",
    # EU / wider Europe
    "de","fr","it","es","nl","be","at","pt","ie","fi","gr","lu","se","dk",
    "no","is","pl","cz","hu","ro","bg","hr","sk","si","ee","lv","lt","tr","ua","ru",
    # Asia-Pacific EM
    "id","th","my","ph","vn",
    # Middle East / Africa
    "za","ae","sa","qa","il","eg","ng","ke","ma",
    # Americas
    "mx","br","cl","co","ar","pe",
]

# Single-codepoint emoji saved under friendly names (filename == the value you
# put in your DataFrame). Region globes for a US / EU / Asia style split.
EMOJI = {
    "americas": "1f30e",   # globe: Americas
    "emea":     "1f30d",   # globe: Europe-Africa
    "asia":     "1f30f",   # globe: Asia-Australia
}

def ri(letter: str) -> str:
    # regional-indicator codepoint (hex) for a letter a-z
    return format(0x1F1E6 + (ord(letter.lower()) - ord("a")), "x")

def twemoji_filename(code: str) -> str:
    return f"{ri(code[0])}-{ri(code[1])}.png"

BASES = [
    "https://raw.githubusercontent.com/jdecked/twemoji/main/assets/72x72/",
    "https://raw.githubusercontent.com/jdecked/twemoji/master/assets/72x72/",
    "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/",
]

def pick_base() -> str:
    probe = twemoji_filename("us")
    for base in BASES:
        try:
            req = urllib.request.Request(base + probe, headers={"User-Agent": "flag-fetch"})
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status == 200 and r.read(8):
                    return base
        except Exception:
            continue
    raise SystemExit("Could not reach any Twemoji asset host.")

def main():
    base = pick_base()
    print(f"Using base: {base}")
    ok, fail = 0, []
    for code in COUNTRIES:
        url = base + twemoji_filename(code)
        dst = FLAG_DIR / f"{code.lower()}.png"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "flag-fetch"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = r.read()
            dst.write_bytes(data)
            ok += 1
        except Exception as e:
            fail.append((code, str(e)))
    for name, cp in EMOJI.items():
        try:
            req = urllib.request.Request(base + cp + ".png",
                                         headers={"User-Agent": "flag-fetch"})
            with urllib.request.urlopen(req, timeout=15) as r:
                (FLAG_DIR / f"{name}.png").write_bytes(r.read())
            ok += 1
        except Exception as e:
            fail.append((name, str(e)))
    print(f"Downloaded {ok}/{len(COUNTRIES) + len(EMOJI)} images -> {FLAG_DIR}")
    if fail:
        print("Failed:", ", ".join(c for c, _ in fail))

if __name__ == "__main__":
    main()
